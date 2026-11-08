"""Orchestration: ingest -> plan -> generate A/B -> QA/critic/repair loop -> review -> revise -> export."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

from ..assemble import DeckInput, DeckSlide, assemble
from ..config import Role, settings
from .. import facts, usage
from ..events import bus
from ..ingest.pptx_parse import ImageRef, Paragraph, SlideContent, TextBlock, parse_pptx
from ..ingest.render import render_slides
from ..llm import client as llm
from ..qa.charts import chart_findings
from ..qa.render_check import check_spec, ledger_findings
from ..skillpack import criteria
from ..spec import SlideSpec, extract_json, parse_spec, to_tagged
from ..store import db
from ..store.db import Project, Slide, Version
from . import mock, prompts, reference

log = logging.getLogger(__name__)
# The criterion list now comes from skill/critic.md itself (skillpack.criteria()) instead of being copied here,
# so the rubric has one home. _critic() still compares the keys the model actually returned against it and
# records a loud warning on any divergence — a model that invents a key is a different problem from drift.
CRITERIA = criteria()  # snapshot at import, for callers that want a plain tuple; prefer criteria() in new code

# Critic outcome, recorded in the version's qa dict as `critic_status`:
CRITIC_OK = "ok"            # the critic ran and returned scores
CRITIC_SKIPPED = "skipped"  # deliberately not run (vision off, unrenderable slide, DOM errors already forcing a repair)
CRITIC_FAILED = "failed"    # the critic was meant to run and could not — never a pass, never a 10
CRITIC_FAILED_SCORE = 6.0   # below critic_min_score: an unreviewed slide must not outrank a reviewed one

# ------------------------------------------------------------------ planning limits
PLAN_BATCH = 15             # slides per planning call, before the context budget shrinks it further
# vLLM refuses a request carrying more images than --limit-mm-per-prompt, and that 400 is not a
# context-length error, so it would fail the batch outright. Keep a batch's thumbnails under the
# limit the server is actually launched with (see deploy/gb300/serve_qwen.sh).
PLAN_MAX_IMAGES = 16
PLAN_REPLY_TOKENS = 12000   # room reserved for the plan JSON (plus thinking) of one batch
PLAN_SLACK_TOKENS = 1500
PLAN_FALLBACK_CONTEXT = 32768  # assumed window when the server never reported max_model_len
HEURISTIC_KEY = "planner"   # written into Slide.plan: "llm" or "heuristic"
PART_KEY = "part_of"        # written into Slide.plan: [part index, total parts] of its source slide
# Slide.plan keys the user's slide management writes (app/pipeline/deckops.py). A re-plan rewrites the plan,
# so these are carried across it: they record what the user did, not what the planner decided.
ADDED_KEY = "added"                  # a slide the user added to a converted deck
REMOVED_KEY = "removed"              # "deleted" | "merged": out of the deck, restorable
MERGED_FROM_KEY = "merged_from"      # [slide ids] this slide was merged from
MERGED_INTO_KEY = "merged_into"      # the slide this one was merged into
MERGED_LABELS_KEY = "merged_labels"  # what those slides were called, for the label ("8+17")
NO_SPLIT_KEY = "no_split"            # the user undid a split, or merged: plan it as one slide
DOC_SOURCES_KEY = "doc_sources"      # ["Whitepaper.pdf, p. 4"]: where this slide's document figures come from
DOC_REFS_KEY = "doc_refs"            # ["<doc id>:<section>"]: the document sections the planner tied this slide to
# {"at", "doc", "figures"}: a document this slide took figures from was removed after the slide was designed
# (reference.forget_doc). The readiness checklist holds it against any design older than `at`.
DOC_STALE_KEY = "doc_stale"
APPENDIX_KEY = "appendix"            # a backup slide after the main deck (condense); an "Appendix" divider precedes them
# A slide inserted from the slide library (library/reuse.py): {lib_slide_id, deck_id, project, deck_title, index,
# origin, label}. Its content and fact ledger are copies of the library slide's; `label` is what the generator is
# told to cite in `sources` (see library_citation), and a PowerPoint-born one lends its render (library_render).
LIBRARY_SOURCE_KEY = "library_source"
# A slide merged from slides that came from the library cites every one of them: a list of `library_source` dicts.
# A separate key, so `library_source` keeps meaning "this slide IS that library slide" (its picture, its badge).
LIBRARY_SOURCES_KEY = "library_sources"
STICKY_PLAN_KEYS = (ADDED_KEY, REMOVED_KEY, MERGED_FROM_KEY, MERGED_INTO_KEY, MERGED_LABELS_KEY, NO_SPLIT_KEY,
                    APPENDIX_KEY, LIBRARY_SOURCE_KEY, LIBRARY_SOURCES_KEY, DOC_STALE_KEY)
MAX_SLIDE_PARTS = 3         # skill/deck_plan.md tells the planner the same number

# A and B are generated concurrently (sequencing B behind A would double the wall-clock cost of every slide, on
# the slowest stage of the pipeline). Instead they are compared afterwards, and B alone is rebuilt when the two
# came out structurally the same — which costs one extra call on the minority of slides that need it.
AB_SIMILARITY_MAX = 0.80

# Pairwise A-vs-B judging (see prompts.ab_messages). Recorded in each version's qa dict as `ab`.
AB_OK = "ok"
AB_SKIPPED = "skipped"
AB_FAILED = "failed"
# How close two pointwise scores have to be before the pairwise verdict is allowed to decide between them. The
# critic's absolute scores are noisy to roughly this much; a larger gap than this is signal, not noise.
AB_SCORE_BAND = 0.5

# Best-of-n sampling for variant A (item 6). Off by default: n samples cost n generations and n renders.
BEST_OF_A_DEFAULT = 1
BEST_OF_A_MAX = 5


def best_of_a() -> int:
    """How many variant-A drafts to sample before picking one. 1 (the default) is today's behaviour.

    `settings()` is lru_cached, so a caller that changes the environment must clear it; the raw env var is
    still read as a fallback for the case where the field is somehow absent.
    """
    v = getattr(settings(), "generate_best_of_a", None)
    if v is None:
        v = os.getenv("GENERATE_BEST_OF_A")
    try:
        return max(1, min(BEST_OF_A_MAX, int(v)))
    except (TypeError, ValueError):
        return BEST_OF_A_DEFAULT


# ------------------------------------------------------------------ task registry
class Jobs:
    def __init__(self) -> None:
        self.tasks: dict[str, set[asyncio.Task]] = defaultdict(set)

    def spawn(self, project_id: str, coro) -> asyncio.Task:
        # the task copies the current context, so every model call it (and its children) makes is billed to
        # this deck in the usage ledger
        if sum(len(tasks) for tasks in self.tasks.values()) >= 32:
            from fastapi import HTTPException
            coro.close()
            raise HTTPException(429, 'Presentation queue full; retry shortly')
        token = usage.current_project.set(project_id)
        try:
            t = asyncio.create_task(coro)
        finally:
            usage.current_project.reset(token)
        self.tasks[project_id].add(t)

        def done(task: asyncio.Task) -> None:
            live = self.tasks.get(project_id)
            if live is not None:
                live.discard(task)
                if not live:
                    # the registry is keyed by project and was never pruned: one key per project uploaded since
                    # the server started, kept alive for the lifetime of the process
                    self.tasks.pop(project_id, None)
            if not task.cancelled() and task.exception():
                log.error("job failed: %s", task.exception(), exc_info=task.exception())

        t.add_done_callback(done)
        return t

    def busy(self, project_id: str) -> bool:
        return any(not t.done() for t in self.tasks.get(project_id, ()))

    async def cancel(self, project_id: str) -> int:
        ts = [t for t in self.tasks.get(project_id, ()) if not t.done()]
        for t in ts:
            t.cancel()
        await asyncio.gather(*ts, return_exceptions=True)
        return len(ts)


jobs = Jobs()


def emit(project_id: str, kind: str, **data) -> None:
    bus.publish(project_id, {"type": kind, **data})


def set_project(pid: str, **fields) -> None:
    db.update(Project, pid, **fields)
    emit(pid, "project", **{k: v for k, v in fields.items() if isinstance(v, (str, int, float, bool, type(None)))})


def set_slide(slide_id: str, **fields) -> Slide | None:
    s = db.update(Slide, slide_id, **fields)
    if s:
        emit(s.project_id, "slide", slide_id=slide_id, **{k: v for k, v in fields.items() if k in ("status", "error", "approved_version_id", "included")})
    return s


def set_version(vid: str, **fields) -> Version | None:
    v = db.update(Version, vid, **fields)
    if v:
        emit(v.project_id, "version", version_id=vid, slide_id=v.slide_id, lineage=v.lineage, status=v.status,
             stage_note=v.stage_note, score=v.score)
    return v


# ------------------------------------------------------------------ the DB boundary for coroutines
# store/db.py is synchronous: every helper opens a session and blocks on SQLite. Called straight from an
# `async def`, that runs on the event loop, so a run's ~240 status writes (each a SELECT + UPDATE + SELECT, on a
# WAL database that fsyncs) serialize against SSE delivery and every HTTP handler in the process.
#
# The wrappers below are the only place the pipeline touches the database from a coroutine. They push the query
# onto a worker thread and then publish the event *back on the event loop* — the split matters: bus.publish()
# ends in asyncio.Queue.put_nowait, which is not thread-safe and would corrupt a subscriber's waiter if it were
# called from the worker. The sync set_* functions above stay exactly as they are, because main.py calls them.
async def _db(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def aset_project(pid: str, **fields) -> None:
    await _db(db.update, Project, pid, **fields)
    emit(pid, "project", **{k: v for k, v in fields.items() if isinstance(v, (str, int, float, bool, type(None)))})


async def aset_slide(slide_id: str, **fields) -> Slide | None:
    s = await _db(db.update, Slide, slide_id, **fields)
    if s:
        emit(s.project_id, "slide", slide_id=slide_id,
             **{k: v for k, v in fields.items() if k in ("status", "error", "approved_version_id", "included")})
    return s


async def aset_version(vid: str, **fields) -> Version | None:
    v = await _db(db.update, Version, vid, **fields)
    if v:
        emit(v.project_id, "version", version_id=vid, slide_id=v.slide_id, lineage=v.lineage, status=v.status,
             stage_note=v.stage_note, score=v.score)
    return v


# ------------------------------------------------------------------ ingest + plan
async def ingest(project_id: str) -> None:
    pdir = db.project_dir(project_id)
    src = pdir / "source.pptx"
    try:
        # Render first: parse_pptx crops shapes it cannot read (EMF/WMF, OLE, failed charts) out of
        # the reference render, so the PNGs have to exist before parsing or that content is lost.
        await aset_project(project_id, status="ingesting", stage_note="Rendering slide previews", error="")
        renderer = await asyncio.to_thread(render_slides, src, pdir / "renders", settings().renderer)
        await aset_project(project_id, renderer=renderer, stage_note="Reading slides")
        deck = await asyncio.to_thread(parse_pptx, src, pdir / "assets", pdir / "renders")

        def _replace_slides() -> list[str]:
            with db.session() as s:
                for old in s.exec(db.select(Slide).where(Slide.project_id == project_id)):
                    s.delete(old)
                s.commit()
            out = []
            for sc in deck.slides:
                # The ledger is extracted here, from the parse, and never from a render: table cells and
                # chart series arrive out of python-pptx exactly, so those facts involve no reading at all.
                content = sc.model_dump()
                db.save(Slide(project_id=project_id, index=sc.index, position=sc.index, content=content,
                              facts=facts.dump(facts.extract(sc.for_prompt(), prefix=f"s{sc.index}f"))))
                out += [f"Slide {sc.index}: {w}" for w in sc.warnings]
            return out

        warnings = await _db(_replace_slides)
        await aset_project(project_id, deck_title=deck.title)
        before = (await _db(db.get, Project, project_id)).warnings or []  # e.g. a reference doc that couldn't be read
        await _db(db.update, Project, project_id, warnings=before + warnings)
        emit(project_id, "slides")
        # Reference documents added with the upload are summarised before the first plan, so it uses them.
        pending = [d for d in await _db(db.docs_of, project_id) if d.status == "digesting"]
        for i, d in enumerate(pending, 1):
            await aset_project(project_id, stage_note=f"Reading {d.name}" + (f" ({i} of {len(pending)})" if len(pending) > 1 else ""))
            await reference.digest_doc(d.id)
        await plan(project_id)
    except asyncio.CancelledError:
        set_project(project_id, status="error", error="Cancelled during import")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("ingest failed")
        set_project(project_id, status="error", error=f"Import failed: {e}")


# ------------------------------------------------------------------ composed decks
async def draft_outline(project_id: str, count: int, about: str = "", source_text: str = "", angle: str = "") -> None:
    """Fill a composed project's slides from its brief. Replaces whatever is there.

    Content only — the design plan is still `plan()`'s job, and runs after the user has read this. The two
    are deliberately separate calls: letting one model decide the facts and the design in one pass is how a
    layout decision quietly becomes an invented statistic.
    """
    from .. import compose

    p = await _db(db.get, Project, project_id)
    if p is None:
        return
    await aset_project(project_id, status="composing", stage_note="Drafting the deck", error="")
    try:
        brief = {"deck_title": p.deck_title or p.name, **(p.brief or {}), "about": about, "angle": angle}
        count = max(1, min(count or compose.DEFAULT_SLIDES, compose.MAX_SLIDES))
        if settings().llm_mock:
            await asyncio.sleep(0.2)
            data = mock.outline(brief, count)
        else:
            msgs = compose.outline_messages(brief, count, source_text)
            r = await llm.chat(msgs, temperature=0.6, thinking=settings().thinking_plan,
                               max_tokens=PLAN_REPLY_TOKENS, guided_json=compose.OUTLINE_SCHEMA, stage="outline")
            data = extract_json(r.text)
            if not isinstance(data, dict):
                raise ValueError("the outline reply was not a JSON object")
        slides = compose.slides_from_outline(data, compose.MAX_SLIDES)
        if not slides:
            raise ValueError("the outline came back with no usable slides")
        await _db(replace_slides, project_id, slides)
        drafted = compose.brief_from_outline(data)
        await aset_project(project_id, status="ready", stage_note="",
                           deck_title=drafted.get("deck_title") or p.deck_title or p.name,
                           brief={**(p.brief or {}), **{k: v for k, v in drafted.items() if v and k != "deck_title"}})
        emit(project_id, "slides")
    except asyncio.CancelledError:
        set_project(project_id, status="ready", stage_note="", error="Cancelled while drafting")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("outline failed")
        set_project(project_id, status="ready", stage_note="",
                    error=f"Could not draft the deck: {e}. The slides you had are unchanged — write them by hand, or try again.")
        emit(project_id, "slides")


def replace_slides(project_id: str, contents: list) -> list[str]:
    """Swap a project's slides for `contents`, extracting each one's fact ledger. Returns the new ids."""
    with db.session() as s:
        for old in s.exec(db.select(Slide).where(Slide.project_id == project_id)):
            s.delete(old)
        s.commit()
    out = []
    for i, sc in enumerate(contents, 1):
        sc = sc.model_copy(update={"index": i, "source_index": i})
        row = db.save(Slide(project_id=project_id, index=i, position=i, content=sc.model_dump(),
                            facts=facts.dump(facts.extract(sc.for_prompt(), prefix=f"s{i}f"))))
        out.append(row.id)
    return out


def add_slide(project_id: str, after: int | None = None) -> Slide:
    """One blank slide, inserted after `after` (a position) or at the end. Positions stay contiguous.

    In a converted deck the new slide is the user's own, typed like a composed one. It takes an `index`
    past every source slide — `index` names the PowerPoint render, and this slide has none — and the
    source slides keep theirs."""
    from .. import compose

    rows = db.slides_of(project_id)
    at = len(rows) if after is None else max(0, min(after, len(rows)))
    p = db.get(Project, project_id)
    if p is not None and (p.source or "pptx") != "composed":
        idx = next_index(project_id)
        new = db.save(Slide(project_id=project_id, index=idx, position=at + 1, content=compose.blank(idx).model_dump(),
                            facts=[], plan={ADDED_KEY: True}))
        reposition(rows[:at] + [new] + rows[at:])
        return db.get(Slide, new.id)
    content = compose.blank(at + 1)
    new = db.save(Slide(project_id=project_id, index=at + 1, position=at + 1, content=content.model_dump(),
                        facts=[]))
    order = rows[:at] + [new] + rows[at:]
    _renumber(order)
    return db.get(Slide, new.id)


def next_index(project_id: str) -> int:
    """An `index` no source slide uses, for a slide made here (added, or merged from others)."""
    return max((s.index for s in db.slides_of(project_id)), default=0) + 1


def reposition(order: list[Slide]) -> None:
    """Renumber positions only. A converted deck's `index` names its source render and never moves."""
    p = db.get(Project, order[0].project_id) if order else None
    if p is not None and (p.source or "pptx") == "composed":
        _renumber(order)
        return
    for i, row in enumerate(order, 1):
        if row.position != i:
            db.update(Slide, row.id, position=i)


def remove_slide(slide_id: str) -> None:
    s = db.get(Slide, slide_id)
    if s is None:
        return
    rest = [x for x in db.slides_of(s.project_id) if x.id != slide_id]
    db.delete_slide(slide_id)
    if rest:
        reposition(rest)


def move_slide(slide_id: str, to: int) -> None:
    """Move to 0-based position `to` among its siblings."""
    s = db.get(Slide, slide_id)
    if s is None:
        return
    rows = [x for x in db.slides_of(s.project_id) if x.id != slide_id]
    to = max(0, min(to, len(rows)))
    reposition(rows[:to] + [s] + rows[to:])


def _renumber(order: list[Slide]) -> None:
    """`position` orders the deck; `index` names the source slide and, for a composed deck, is the same
    thing. Kept in step so the two never disagree about what slide 4 is."""
    for i, row in enumerate(order, 1):
        if row.position != i or row.index != i:
            db.update(Slide, row.id, position=i, index=i)


def write_slide(slide_id: str, *, title: str | None = None, body: str | None = None, notes: str | None = None) -> Slide:
    """Type into a composed slide. The typed content IS the source, so it is written to `content`, not to
    the `content_edit` overlay the converter uses to keep the PowerPoint recoverable."""
    from .. import compose

    s = db.get(Slide, slide_id)
    if s is None:
        raise ValueError(f"no slide {slide_id}")
    cur = SlideContent.model_validate(s.content or {})
    cur_body = "\n".join(p.text for b in cur.texts for p in b.paragraphs)
    content = compose.content_from(
        cur.title if title is None else title,
        cur_body if body is None else body,
        cur.notes if notes is None else notes,
        s.index)
    content.images = cur.images  # typing never touches the pictures the user put on the slide
    # ...nor tables and charts, which the typing form cannot show. Only a slide inserted from the slide library
    # has any; dropping them would also drop their facts from the ledger re-extracted below.
    content.tables, content.charts = cur.tables, cur.charts
    # Tiers are the planner's and the user's work; carry them across what the retyped copy still asserts.
    tiers = {f.raw.lower(): f.tier for f in slide_facts(s)}
    fresh = facts.extract(content.for_prompt(), prefix=f"s{s.index}f")
    for f in fresh:
        f.tier = tiers.get(f.raw.lower(), f.tier)
    return db.update(Slide, slide_id, content=content.model_dump(), facts=facts.dump(fresh), facts_edit=None)


# ------------------------------------------------------------------ slide content
# `Slide.content` is the PPTX parse and is only ever written by ingest(). What the user approves in the
# plan view lives in `Slide.content_edit` and is laid over it here, so every consumer of _content()
# — planning, generation, repair, revision and the QA fidelity check — sees the approved copy.
_BOLD = re.compile(r"^\*\*(.+)\*\*$", re.S)


def attach_image(slide_id: str, key: str, *, alt: str = "", detach: bool = False) -> Slide | None:
    """Add (or remove) a deck image on a slide's content. The next generation or revision sees it in the
    prompt's `images`, exactly like a picture the PowerPoint carried.

    A converted slide keeps its parse untouched and gets the change in `content_edit`, like any other copy
    edit, so "reset to PowerPoint" still means what it says. A composed slide has no parse to protect."""
    s = db.get(Slide, slide_id)
    if s is None:
        return None
    cur = merged_content(s)
    imgs = [i for i in cur.images if i.key != key]
    if not detach:
        w = h = 0
        f = db.asset_files(s.project_id).get(key)
        if f is not None and f.suffix != ".svg":
            try:
                with Image.open(f) as im:
                    w, h = im.size
            except OSError:
                pass
        imgs.append(ImageRef(key=key, alt=alt.strip()[:200], width=w, height=h, source="upload"))
    dumped = [i.model_dump() for i in imgs]
    if composed(s):
        return set_slide(slide_id, content={**(s.content or {}), "images": dumped})
    return set_slide(slide_id, content_edit={**(s.content_edit or {}), "images": dumped})


def composed(slide: Slide) -> bool:
    p = db.get(Project, slide.project_id)
    return p is not None and (p.source or "pptx") == "composed"


def parsed_content(slide: Slide) -> SlideContent:
    """The untouched PowerPoint parse."""
    return SlideContent.model_validate(slide.content)


def merged_content(slide: Slide) -> SlideContent:
    """The parse with the user's approved copy laid over it, field by field."""
    return SlideContent.model_validate({**(slide.content or {}), **(slide.content_edit or {})})


def content_for_prompt(slide: Slide) -> dict:
    """What every prompt sees for this slide: the parse with the user's approved copy laid over it."""
    return merged_content(slide).for_prompt()


_content = content_for_prompt  # pre-existing private name, kept for callers outside this module


def slide_facts(slide: Slide) -> list[facts.Fact]:
    """The ledger this slide is held to: the user's corrected list if there is one, else the extracted one.

    Whole-list rather than field-by-field like `content_edit`, because striking a fact out is a real
    edit — a source slide can carry a figure that genuinely does not belong on the designed one — and an
    overlay cannot express a deletion.
    """
    return facts.load(slide.facts_edit if slide.facts_edit is not None else slide.facts)


def refresh_facts(slide: Slide) -> list[facts.Fact]:
    """Re-extract from the approved copy, keeping the tier of any fact that survives the edit.

    Editing the copy in the plan view changes what the slide claims, so the ledger has to follow it or
    it would hold the design to figures the user has removed. Tiers are the planner's and the user's
    work, so they are carried across rather than recomputed.
    """
    tiers = {f.raw.lower(): f.tier for f in slide_facts(slide)}
    fresh = facts.extract(content_for_prompt(slide), prefix=f"s{slide.index}f")
    for f in fresh:
        f.tier = tiers.get(f.raw.lower(), f.tier)
    return fresh


def _paragraph(line: str) -> Paragraph | None:
    text = line.strip()
    if not text:
        return None
    m = _BOLD.match(text)
    return Paragraph(text=m.group(1).strip() if m else text, bold=bool(m),
                     level=min(4, (len(line) - len(line.lstrip(" "))) // 2))


def content_edit(slide: Slide, *, title: str | None = None, blocks: list[str] | None = None) -> dict:
    """Build the override from the plain text the plan view shows.

    `blocks` is one string per body block in the order `for_prompt()` lists them, one line per
    paragraph, two spaces per indent level and `**bold**` — exactly the shape it writes out, so what
    the user reads is what the model gets. Kind and position are carried over from the block being
    replaced; an emptied block is dropped, extra blocks land as body text.
    """
    edit = dict(slide.content_edit or {})
    if title is not None:
        edit["title"] = " ".join(title.split())
    if blocks is not None:
        current = merged_content(slide).texts
        body = [t for t in current if t.kind != "title"]
        out = []
        for i, raw in enumerate(blocks):
            paras = [p for p in (_paragraph(line) for line in raw.splitlines()) if p]
            if not paras:
                continue
            src = body[i] if i < len(body) else None
            out.append(TextBlock(kind=src.kind if src else "body", paragraphs=paras, box=list(src.box) if src else []))
        # title blocks never reach the prompt (for_prompt reads `title`); keep them so a revert is a clean swap
        edit["texts"] = [t.model_dump() for t in [x for x in current if x.kind == "title"] + out]
    return edit


def _thumbs(project_id: str, indexes: list[int]) -> dict[int, Path]:
    """The 480px thumbnails make_thumbs() writes next to the full renders, by slide index."""
    rdir = db.project_dir(project_id) / "renders"
    out = {}
    for i in indexes:
        t = rdir / f"{i:03d}_thumb.jpg"
        if t.exists():
            out[i] = t
    return out


async def _plan_batches(items: list[dict], thumbs: dict[int, Path], reference: str = "") -> list[list[dict]]:
    """Split the deck into planning calls that actually fit.

    One message holding every slide of a 60-slide deck is how the planner used to die: vLLM answers 400, the
    client treats 4xx as fatal, and the whole deck silently falls back to keyword heuristics. The budget is the
    served max_model_len (reported by /v1/models, cached on the client) minus the static system prefix and the
    room the reply needs — and the reference documents' digests, which ride in every batch.
    """
    limit = await llm.context_limit() or PLAN_FALLBACK_CONTEXT
    overhead = llm.estimate_tokens(prompts.plan_messages([], thumbs=None, reference=reference))
    budget = max(2000, limit - overhead - PLAN_REPLY_TOKENS - PLAN_SLACK_TOKENS)
    batches: list[list[dict]] = []
    cur: list[dict] = []
    used = 0
    images = 0
    for it in items:
        cost = llm.estimate_tokens([{"role": "user", "content": prompts._dump(it["content"])}])
        has_image = it["index"] in thumbs
        if has_image:
            cost += llm.IMAGE_TOKENS
        # An over-limit image count is a hard 400 from vLLM, not a context error, so split on it too.
        if cur and (len(cur) >= PLAN_BATCH or used + cost > budget or images + has_image > PLAN_MAX_IMAGES):
            batches.append(cur)
            cur, used, images = [], 0, 0
        cur.append(it)
        used += cost
        images += has_image
    if cur:
        batches.append(cur)
    return batches


async def _plan_call(batch: list[dict], *, thumbs: dict[int, Path], summary: str, note: str,
                     reference: str = "") -> dict | None:
    """One planning batch, with a trim-and-retry for a context-length refusal. None = this batch failed."""
    thumbs_in = {i: p for i, p in thumbs.items() if i in {b["index"] for b in batch}}
    msgs = prompts.plan_messages(batch, thumbs=thumbs_in or None, deck_summary=summary, batch_note=note,
                                 reference=reference)
    for attempt in range(3):
        try:
            r = await llm.chat(msgs, temperature=0.3, thinking=settings().thinking_plan, max_tokens=PLAN_REPLY_TOKENS,
                               guided_json=prompts.PLAN_SCHEMA, stage="plan")
            # still parsed leniently: guided decoding may be off (unsupported server, or GUIDED_JSON=false), and
            # a thinking model's reply legitimately starts with a reasoning block that the constraint skips.
            data = extract_json(r.text)
            if not isinstance(data, dict) or not isinstance(data.get("slides"), list):
                raise ValueError("reply had no slides array")
            return data
        except asyncio.CancelledError:
            raise
        except llm.ContextLengthError as e:
            # The batch was already sized to the window, so something in it is far bigger than estimated.
            # Drop the pictures first (cheapest to lose), then squeeze the text harder. Retrying unchanged
            # could only fail again.
            log.warning("plan batch did not fit the context window: %s", e)
            if thumbs_in:
                thumbs_in = {}
            else:
                batch = [{**b, "content": prompts.trim_content(b["content"], max_lines=4, max_rows=2, max_notes=120,
                                                               drop_charts=True)} for b in batch]
            msgs = prompts.plan_messages(batch, thumbs=thumbs_in or None, deck_summary=summary, batch_note=note,
                                         reference=reference)
        except Exception as e:  # noqa: BLE001
            log.warning("plan attempt %d failed: %s", attempt + 1, e)
    return None


def _split_facts(ledger: list[facts.Fact], parts: list[dict]) -> list[list[facts.Fact]]:
    """Divide one source slide's ledger between the designed slides it was split into.

    Every part must be checkable on its own, so a fact belongs to exactly one of them: sharing the whole
    ledger would fail each part for the facts its sibling is showing, which is the opposite of what
    splitting is for.

    A fact goes to the part that names it in `key_facts`. What nobody claims goes to the part whose
    headline and key message talk about it, and to the first part when nothing does — losing a fact
    because the planner forgot to claim it would give the split the exact failure it exists to prevent.
    """
    if len(parts) < 2:
        return [_tier_facts(ledger, parts[0].get("key_facts") or []) if parts else ledger]
    out: list[list[facts.Fact]] = [[] for _ in parts]
    claimed: set[str] = set()
    for i, part in enumerate(parts):
        for f in _tier_facts([f.model_copy(deep=True) for f in ledger], part.get("key_facts") or []):
            if f.tier == "key" and f.id not in claimed:
                claimed.add(f.id)
                out[i].append(f)
    for f in ledger:
        if f.id in claimed:
            continue
        words = {w for w in re.findall(r"[a-z0-9]{3,}", f"{f.raw} {f.label}".lower())}
        scores = [len(words & {w for w in re.findall(r"[a-z0-9]{3,}",
                                                     f"{p.get('headline', '')} {p.get('key_message', '')}".lower())})
                  for p in parts]
        best = max(range(len(parts)), key=lambda i: scores[i])
        home = best if scores[best] else 0
        out[home].append(f.model_copy(deep=True, update={"tier": "supporting"}))
    return out


def _tier_facts(ledger: list[facts.Fact], key_facts: list) -> list[facts.Fact]:
    """Mark the facts the planner named as this slide's message.

    The planner writes `key_facts` as free strings copied from the source, so they are matched against the
    ledger rather than trusted as entries: a figure the planner paraphrased or mistyped simply fails to
    match and stays supporting. That is the safe direction — the LLM can promote a fact the deterministic
    pass already found, and cannot invent a requirement out of nothing.

    A key fact must be *on* the finished slide; a supporting one may live in the speaker notes.
    """
    wanted = [str(k).strip() for k in key_facts if str(k).strip()]
    if not wanted:
        return ledger
    for f in ledger:
        f.tier = "supporting"
    for want in wanted:
        hit = next((f for f in ledger if f.raw.lower() == want.lower()), None)
        if hit is None:
            # "$4.2M in revenue" naming the fact "$4.2M": match on the figure the planner meant.
            nums = facts.parse_numbers(want)
            if nums:
                n = nums[0]
                hit = next((f for f in ledger
                            if f.kind == "number" and f.unit == n.unit and f.value is not None
                            and abs(f.value - n.value) < 1e-9), None)
            else:
                hit = next((f for f in ledger if f.kind == "name" and facts.has_name(f.raw, want)), None)
        if hit is not None:
            hit.tier = "key"
    return ledger


def is_removed(s: Slide) -> bool:
    return bool((s.plan or {}).get(REMOVED_KEY))


NO_SPLIT_NOTE = ("The user has switched splitting off for this deck: return exactly ONE entry per input slide. "
                 "Tighten a dense slide and move detail to the speaker notes instead of splitting it.")


async def plan(project_id: str) -> None:
    await aset_project(project_id, status="planning", stage_note="Planning the deck", error="")
    # One entry per *source* slide. A previous plan may have split one into parts; those extra rows are
    # that slide's, not slides in their own right, and planning them again would split the split.
    # Slides the user deleted or merged away are out of the deck and stay exactly as they are.
    every = [s for s in await _db(db.slides_of, project_id) if not is_removed(s)]
    slides = [s for s in every if s.part == 0]
    proj = await _db(db.get, Project, project_id)
    allow_split = not proj or (proj.brief or {}).get("allow_split", True) is not False
    ref_text = await _db(reference.planner_reference, project_id)  # the whole of it: what batches are sized against
    by_source: dict[int, list[Slide]] = {}
    for x in every:
        by_source.setdefault(x.index, []).append(x)
    for group in by_source.values():
        group.sort(key=lambda x: x.part)
    full = [{"index": s.index, "content": _content(s)} for s in slides]
    fallback = mock.plan(full)
    planned: list[dict] = []
    brief_from_llm: dict = {}
    heuristic: list[int] = []
    if settings().llm_mock:
        await asyncio.sleep(0.3)
        planned = list(fallback["slides"])
        brief_from_llm = {k: fallback[k] for k in ("deck_title", "audience", "tone", "narrative")}
    else:
        # The planner reads a trimmed copy: it chooses a pattern and two ideas, and never needs 40 table rows.
        items = [{"index": s["index"], "content": prompts.plan_content(s["content"])} for s in full]
        thumbs = _thumbs(project_id, [s["index"] for s in items]) if await llm.vision_enabled() else {}
        batches = await _plan_batches(items, thumbs, ref_text)
        for bi, batch in enumerate(batches):
            if len(batches) > 1:
                await aset_project(project_id, stage_note=f"Planning slides {batch[0]['index']}–{batch[-1]['index']} "
                                                          f"(batch {bi + 1} of {len(batches)})")
            note = "" if len(batches) == 1 else (
                f"This is batch {bi + 1} of {len(batches)} for one deck. Plan ONLY the slides listed below, and keep "
                f"them consistent with what earlier batches already decided (see 'Deck so far'). "
                + ("Set the deck title, audience, tone and narrative for the whole deck." if bi == 0 else
                   "Repeat the deck title, audience, tone and narrative you are given — do not invent new ones."))
            if not allow_split:
                note = (note + "\n\n" if note else "") + NO_SPLIT_NOTE
            # One batch: everything. Several: each reads in full only the sections its own slides bear on.
            ref = ref_text if len(batches) == 1 or not ref_text else await _db(
                reference.planner_reference, project_id, " ".join(prompts._dump(b["content"]) for b in batch))
            data = await _plan_call(batch, thumbs=thumbs, summary=prompts.deck_summary(brief_from_llm, planned) if bi else "",
                                    note=note, reference=ref)
            if data is None:
                heuristic += [b["index"] for b in batch]
                continue
            if not brief_from_llm:
                brief_from_llm = {k: v for k, v in ((k, data.get(k)) for k in ("deck_title", "audience", "tone", "narrative")) if v}
            planned += [p for p in data["slides"] if isinstance(p, dict)]

    # The planner may return more than one entry for a source slide: see "Splitting a dense slide" in
    # skill/deck_plan.md. Entries keep their order, so `by_index[3] == [part 0, part 1]`.
    by_index: dict[int, list[dict]] = {}
    for p in planned:
        try:
            by_index.setdefault(int(p.get("index", -1)), []).append(p)
        except (TypeError, ValueError):
            continue
    fb_index = {p["index"]: p for p in fallback["slides"]}

    not_in_docs: list[str] = []  # figures the planner attributed to a reference document that no document contains
    reworded: list[str] = []     # ones a document states in other words: the ledger took the document's wording

    def _write_plans() -> None:
        pos = 0
        for s in slides:
            entries = by_index.get(s.index) or []
            parts = [{k: v for k, v in e.items() if v not in (None, "")} for e in entries[:MAX_SLIDE_PARTS]]
            if not allow_split or (s.plan or {}).get(NO_SPLIT_KEY):
                parts = parts[:1]  # the user said one slide; the planner does not get to overrule that
            if not parts:
                parts = [{}]
                if s.index not in heuristic:
                    heuristic.append(s.index)
            # Split the ledger before writing any part, so each one is checked only against the facts it
            # claims. Sharing the whole ledger would fail every part for the facts its sibling is showing.
            # Figures a previous plan brought in from a reference document are re-derived from this plan's
            # `doc_facts`, never carried over: the planner (or the documents) may have changed its mind.
            base = [f for f in facts.load(s.facts) if f.origin != "doc"]
            ledgers = _split_facts(base, parts) if s.facts_edit is None else [None] * len(parts)
            existing = by_source.get(s.index) or [s]
            for i, (got, sub_facts) in enumerate(zip(parts, ledgers)):
                p = fb_index[s.index] | got
                if i == 0:
                    p.update({k: v for k, v in (s.plan or {}).items() if k in STICKY_PLAN_KEYS})
                elif (s.plan or {}).get(LIBRARY_SOURCE_KEY):
                    # every part of a library slide shows its figures, so every part cites it
                    p[LIBRARY_SOURCE_KEY] = s.plan[LIBRARY_SOURCE_KEY]
                p[HEURISTIC_KEY] = "llm" if got else "heuristic"
                p[PART_KEY] = [i, len(parts)]
                pos += 1
                # Only plan fields and the ledger's tiers are written here: `content` and the user's approved
                # `content_edit` both survive a re-plan (the planner above already read the edited copy through
                # _content()), and so does a ledger the user has corrected by hand.
                fields = {"plan": p, "included": bool(p.get("include", True)), "status": "pending",
                          "position": pos, "part": i}
                extra, cites = reference.doc_facts(s.project_id, got.get("doc_facts") or [], f"s{s.index}d{i}_",
                                                   rejected=not_in_docs, adopted=reworded)
                p.pop("doc_facts", None)
                if cites:
                    p[DOC_SOURCES_KEY] = cites
                refs = reference.resolve_refs(s.project_id, got.get(DOC_REFS_KEY))
                p.pop(DOC_REFS_KEY, None)
                if refs:
                    p[DOC_REFS_KEY] = refs
                if sub_facts is not None:
                    fields["facts"] = facts.dump(sub_facts + extra)
                if i < len(existing):
                    db.update(Slide, existing[i].id, **fields)
                else:
                    # A part the previous plan did not have. It shares the source slide's index — and so its
                    # render, its parsed content and its approved copy — and differs only in which facts it
                    # is responsible for.
                    db.save(Slide(project_id=s.project_id, index=s.index, content=s.content,
                                  content_edit=s.content_edit, **fields))
            # A re-plan that splits less than the last one leaves orphans; they are this source slide's
            # parts and nothing else refers to them.
            for extra in existing[len(parts):]:
                db.delete_slide(extra.id)
        # Out-of-deck slides go after the live ones, so two rows never share a position.
        for gone in (x for x in db.slides_of(project_id) if is_removed(x)):
            pos += 1
            db.update(Slide, gone.id, touch=False, position=pos)

    await _db(_write_plans)
    brief = {k: brief_from_llm.get(k) or fallback[k] for k in ("deck_title", "audience", "tone", "narrative")}
    # The user's own settings (allow_split) live in the brief too, and a re-plan must not reset them.
    brief = {**{k: v for k, v in ((proj.brief or {}) if proj else {}).items() if k not in brief}, **brief}

    # Degrading to mock.plan() is not a detail: its idea_a/idea_b are the same two constant strings for every
    # slide, so an entire deck would be generated from identical creative direction. Say so where the user reads.
    warning = ""
    if heuristic and not settings().llm_mock:
        which = ", ".join(str(i) for i in sorted(heuristic)[:12]) + ("…" if len(heuristic) > 12 else "")
        warning = (f"Planner unavailable for {len(heuristic)} of {len(slides)} slide(s) (slides {which}). Those were "
                   "planned by the offline heuristic, which gives every slide the same creative direction — "
                   "pattern, headline and both variant ideas are guesses from keywords. Check the model connection "
                   "and re-plan before generating, or edit the plan by hand.")
        log.error("%s", warning)
    # A figure dropped at the gate is the system working, but silently it reads as the planner ignoring the
    # document. Say which ones, so the user can add the figure by hand if the document does state it another way.
    doc_note = ""
    if not_in_docs:
        shown = "; ".join(f"“{q[:60]}”" for q in dict.fromkeys(not_in_docs))[:400]
        doc_note = (f"{len(set(not_in_docs))} figure(s) the planner took from the reference documents were not found "
                    f"in them word for word and were left out: {shown}.")
    if reworded:
        shown = "; ".join(dict.fromkeys(reworded))[:400]
        doc_note = (doc_note + " " if doc_note else "") + (
            f"{len(set(reworded))} figure(s) were quoted in other words than the document's and are held to the "
            f"document's own: {shown}.")
    existing = await _db(db.get, Project, project_id)
    keep = [w for w in (existing.warnings or [])
            if "planned by the offline heuristic" not in w and "were not found in them word for word" not in w
            and "held to the document's own" not in w]
    await _db(db.update, Project, project_id, warnings=keep + [w for w in (warning, doc_note) if w])
    await aset_project(project_id, status="ready", stage_note=warning, error="", brief=brief,
                       deck_title=brief["deck_title"])
    emit(project_id, "slides")


# ------------------------------------------------------------------ deck design memory
_CLASS_ATTR = re.compile(r'class="([^"]*)"')
# Runtime classes worth reporting across slides: the ones that define the deck's visual conventions.
_LOG_CLASSES = {
    "card": "bordered cards", "tint": "soft tinted panels", "callout": "blue callout blocks",
    "big-num": "96px hero numbers", "mega-num": "196px mega numbers", "num": "mono tabular numbers",
    "table": "data tables", "list": "bulleted lists", "nlist": "numbered lists", "figure": "framed images",
    "split": "split layouts", "grid-2": "two-column grids", "grid-3": "three-column grids",
    "grid-4": "four-column grids", "plot": "charts", "chip": "chips", "rule-bar": "accent rules",
    "quote": "pull quotes", "timeline": "timelines", "kpi": "KPI rows",
}


def _classes(html: str) -> list[str]:
    out = []
    for m in _CLASS_ATTR.finditer(html or ""):
        out += m.group(1).split()
    return out


def _built_specs(project_id: str, skip_slide_id: str | None = None) -> list[tuple[Slide, SlideSpec]]:
    out = []
    for s in db.slides_of(project_id):
        if not s.included or s.id == skip_slide_id:
            continue
        v = best_version(s)
        if v and v.spec:
            try:
                out.append((s, SlideSpec.model_validate(v.spec)))
            except Exception:  # noqa: BLE001, PERF203
                continue
    return out


def design_log(project_id: str, skip_slide_id: str | None = None, limit: int = 10) -> str:
    """A compact running record of what this deck's finished slides actually do.

    Each slide otherwise sees only the previous and next headline, so a 15-slide deck is 15 independent designs
    that happen to share a palette. This is derived from the promoted specs rather than stored, so it is always
    in step with what the user can see and survives a re-generation of any slide.
    """
    rows = _built_specs(project_id, skip_slide_id)[-limit:]
    if not rows:
        return ""
    lines = [f"{len(rows)} slide(s) of this deck are already designed."]
    lines.append("- Patterns so far, in order: " + " → ".join((sp.meta.pattern or "?") for _, sp in rows))
    counts: dict[str, int] = {}
    for _, sp in rows:
        for c in set(_classes(sp.html)):
            if c in _LOG_CLASSES:
                counts[c] = counts.get(c, 0) + 1
    common = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    if common:
        lines.append("- Established components: " + ", ".join(f"{_LOG_CLASSES[c]} ({n}/{len(rows)} slides)" for c, n in common))
    stats = [c for c in ("mega-num", "big-num", "num") if counts.get(c)]
    lines.append("- Numbers are rendered with: " + (", ".join(f".{c}" for c in stats) if stats else
                                                    "no hero-number treatment yet — you may establish one"))
    themes: dict[str, int] = {}
    for _, sp in rows:
        themes[sp.meta.theme or "light"] = themes.get(sp.meta.theme or "light", 0) + 1
    lines.append("- Themes used: " + ", ".join(f"{t} ×{n}" for t, n in sorted(themes.items(), key=lambda kv: -kv[1]))
                 + " (keep non-light slides at roughly 20% of the deck)")
    steps = [sp.meta.steps for _, sp in rows if sp.meta.steps]
    if steps:
        lines.append(f"- Step counts so far: {', '.join(str(x) for x in steps)} — vary the interaction, not the vocabulary")
    return "\n".join(lines)


def structure_signature(spec: SlideSpec) -> dict[str, int]:
    """A bag of structural features: runtime classes plus block-level tags. Two slides with the same signature
    are the same design whatever their words are."""
    sig: dict[str, int] = {}
    for c in _classes(spec.html):
        sig["c:" + c] = sig.get("c:" + c, 0) + 1
    for tag in re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)\b", spec.html or ""):
        t = tag.lower()
        if t in ("div", "span", "br", "i", "b", "em", "strong"):
            continue  # carry no structure on their own
        sig["t:" + t] = sig.get("t:" + t, 0) + 1
    return sig


def ab_similarity(a: SlideSpec, b: SlideSpec) -> float:
    """0..1 structural overlap of two variants of the same slide (weighted Jaccard over their signatures,
    nudged up when they also share a pattern and a step budget)."""
    sa, sb = structure_signature(a), structure_signature(b)
    keys = set(sa) | set(sb)
    if not keys:
        return 1.0
    inter = sum(min(sa.get(k, 0), sb.get(k, 0)) for k in keys)
    union = sum(max(sa.get(k, 0), sb.get(k, 0)) for k in keys)
    score = inter / union if union else 1.0
    if (a.meta.pattern or "") == (b.meta.pattern or ""):
        score = min(1.0, score + 0.08)
    if abs((a.meta.steps or 0) - (b.meta.steps or 0)) <= 1:
        score = min(1.0, score + 0.04)
    return round(score, 3)


def structure_brief(spec: SlideSpec) -> str:
    """A few lines describing a spec's composition — cheap enough to paste into the other variant's prompt
    without sending the whole HTML back through the model."""
    counts: dict[str, int] = {}
    for c in _classes(spec.html):
        counts[c] = counts.get(c, 0) + 1
    named = sorted(((c, n) for c, n in counts.items() if c in _LOG_CLASSES), key=lambda kv: (-kv[1], kv[0]))[:8]
    return (f"- pattern: {spec.meta.pattern or '?'} · theme: {spec.meta.theme or 'light'} · steps: {spec.meta.steps}\n"
            f"- built from: {', '.join(f'{c}×{n}' for c, n in named) or 'custom markup'}\n"
            f"- headline: \"{spec.meta.title}\"")


# ------------------------------------------------------------------ generation
_LIB_ID = re.compile(r"^[A-Za-z0-9]+$")


def library_sources(plan: dict) -> list[dict]:
    """Every library slide this slide's content came from: the one it was inserted as, or all of them after a merge."""
    plan = plan or {}
    one = plan.get(LIBRARY_SOURCE_KEY)
    many = plan.get(LIBRARY_SOURCES_KEY)
    out = ([one] if isinstance(one, dict) else []) + [s for s in (many if isinstance(many, list) else []) if isinstance(s, dict)]
    seen: set = set()
    return [s for s in out if not (s.get("lib_slide_id") in seen or seen.add(s.get("lib_slide_id")))]


def library_citation(plan: dict) -> str:
    """What a slide made from slide-library slides cites in `sources` ("Q3 review, slide 4 (slide library)"; several
    joined with "; " after a merge). Its figures came from those decks, not from this one's PowerPoint or documents —
    prompts.reference_block says so."""
    labels = [str(s.get("label") or "").strip() for s in library_sources(plan)]
    return "; ".join(dict.fromkeys(x for x in labels if x))


def library_render(plan: dict) -> Path | None:
    """The original render of a library slide born in a PowerPoint (uploaded or converted), to stand in for the
    source render a slide inserted from the library does not have in this project. Read in place from the library
    (same path as library.common.render_path, without its mkdir), so nothing is copied under `renders/` where a
    later slide reusing the index would pick it up. A generated library slide's picture is already an HP design —
    not an "original slide" — and gets none. Every consumer `.exists()`-guards it anyway."""
    src = (plan or {}).get(LIBRARY_SOURCE_KEY)
    if not isinstance(src, dict) or src.get("origin") == "generated" or not _LIB_ID.match(str(src.get("deck_id") or "")):
        return None
    try:
        index = int(src.get("index") or 0)
    except (TypeError, ValueError):
        return None
    png = settings().data_dir / "library" / src["deck_id"] / "renders" / f"{index:03d}.png"
    return png if index > 0 and png.exists() else None


class Ctx:
    """Everything a generation/revision needs about one slide.

    Built ONCE per slide and shared by the A and B tasks (and by a rebuilt B): it is four-plus synchronous
    queries — project, all slides, assets — that return the same answer for both variants, and it was previously
    constructed inside each `generate_version`, so every slide paid for it twice. Nothing in it changes while the
    slide is being generated. Construct it off the event loop (`await _db(Ctx, slide)`).
    """

    def __init__(self, slide: Slide):
        self.slide = slide
        self.design_log: str | None = None  # filled once per slide by generate_slide; None = not computed yet
        self.project = db.get(Project, slide.project_id)
        all_slides = [s for s in db.slides_of(slide.project_id) if s.included]
        pos = next((i for i, s in enumerate(all_slides) if s.id == slide.id), 0)
        self.position, self.total = pos + 1, len(all_slides)
        self.prev_plan = all_slides[pos - 1].plan if pos > 0 else None
        self.next_plan = all_slides[pos + 1].plan if pos + 1 < len(all_slides) else None
        self.content = _content(slide)
        # The ledger this slide is held to. Extracted at ingest from the parse, tiered by the planner,
        # correctable by the user. It is what QA checks the render against and what the generator is
        # shown as "these values are not yours to change" — the design is free, the figures are not.
        self.facts = slide_facts(slide)
        # The copy was approved by hand: lay it out, never reword it. An attached image is not a copy edit.
        self.verbatim = bool({k for k in (slide.content_edit or {}) if k != "images"})
        self.plan = slide.plan or {}
        self.brief = {"deck_title": self.project.deck_title, **(self.project.brief or {})}
        # Passages from the user's reference documents that bear on this slide (empty when there are none).
        self.reference = reference.slide_reference(slide.project_id, self.plan, self.content)
        self.redesign = ""  # set by a redesign-with-a-reason: why the user threw the last designs away
        png = db.project_dir(slide.project_id) / "renders" / f"{slide.index:03d}.png"
        self.source_png = library_render(self.plan) or (png if png.exists() else None)
        self.assets = db.asset_files(slide.project_id)
        src_text = [self.content.get("title", "")]
        for b in self.content.get("text") or []:
            src_text += b.get("lines", [])
        for t in self.content.get("tables") or []:
            src_text += [" ".join(r) for r in t]
        for c in self.content.get("charts") or []:
            src_text += [str(v) for srs in c.get("series", []) for v in srs.get("values", []) if v is not None]
        self.source_text = "\n".join(src_text)


def _add_stats(acc: dict, r: llm.LLMResult) -> dict:
    acc = dict(acc or {})
    acc["calls"] = acc.get("calls", 0) + 1
    acc["prompt_tokens"] = acc.get("prompt_tokens", 0) + r.prompt_tokens
    acc["completion_tokens"] = acc.get("completion_tokens", 0) + r.completion_tokens
    acc["seconds"] = round(acc.get("seconds", 0) + r.seconds, 1)
    return acc


async def _complete_spec(msgs: list[dict], slide_id: str, temperature: float, stats: dict,
                         *, rebuild=None, stage: str = "generate") -> tuple[SlideSpec, list, dict]:
    """Ask for a spec, retrying on an unusable reply and once on a context-length refusal.

    `rebuild()` returns the same request built from trimmed content. Without it a single slide carrying a
    100-row table is fatal: vLLM answers 400, both variants fail with a raw HTTP error and the slide stays dead
    until it is removed from the deck.
    """
    s = settings()
    base = msgs
    last_err = ""
    trimmed = False
    attempt = 0
    while attempt < 3:
        try:
            r = await llm.chat(base if attempt == 0 else msgs, temperature=temperature, thinking=s.thinking_generate,
                               stage=stage)
        except llm.ContextLengthError as e:
            if trimmed or rebuild is None:
                raise
            trimmed = True
            log.warning("prompt exceeded the context window (%s) — retrying once with trimmed slide content", e)
            base = msgs = rebuild()
            continue
        stats = _add_stats(stats, r)
        try:
            if r.finish_reason == "length" and "</html>" not in r.text:
                raise ValueError("reply was cut off by the token limit — make the slide simpler and the code shorter")
            spec, issues = parse_spec(r.text, slide_id)
            return spec, issues, stats
        except ValueError as e:
            last_err = str(e)
            attempt += 1
            log.warning("spec parse failed (attempt %d): %s", attempt, e)
            # The bad reply is NOT echoed back: it is unusable by definition, and up to ~1.5k tokens of it would
            # only compete with the instruction to do it properly. The task is still in `base`, unchanged.
            msgs = base + [prompts.format_retry_message(last_err, attempt)]
    raise RuntimeError(f"model did not return a usable spec: {last_err}")


def _score(findings: list[dict], critic: dict | None, status: str = CRITIC_OK) -> float:
    """QA score. A missing critic is only worth the benefit of the doubt when it was skipped on purpose;
    a critic that was supposed to run and failed caps the score well below the pass mark."""
    if status == CRITIC_FAILED:
        base = CRITIC_FAILED_SCORE
    elif critic and isinstance(critic.get("scores"), dict):
        vals = [float(critic["scores"].get(k, 0) or 0) for k in criteria()]
        base = sum(vals) / len(vals)
    else:
        base = 10.0
    errors = sum(1 for f in findings if f["severity"] == "error")
    warns = sum(1 for f in findings if f["severity"] == "warn")
    return round(max(0.0, base - min(6.0, 1.5 * errors) - min(1.5, 0.3 * warns)), 2)


def _critic_passes(critic: dict | None, status: str = CRITIC_OK) -> bool:
    if status == CRITIC_FAILED:
        return False  # unreviewed is not reviewed-and-clean
    if critic is None:
        return True
    scores = critic.get("scores") or {}
    high = any((i or {}).get("severity") == "high" for i in critic.get("issues") or [])
    return not high and all(float(scores.get(k, 0) or 0) >= settings().critic_min_score for k in criteria())


def _criteria_mismatch(critic: dict) -> str:
    """The rubric is read out of skill/critic.md, so this can no longer be a copy drifting from the prompt — but
    a model answering with keys the rubric never asked for still has to be visible."""
    keys = criteria()
    scores = critic.get("scores")
    if not isinstance(scores, dict):
        return "critic returned no scores object"
    missing = [k for k in keys if k not in scores]
    extra = [k for k in scores if k not in keys]
    if not missing and not extra:
        return ""
    parts = []
    if missing:
        parts.append(f"not scored by the model: {', '.join(missing)}")
    if extra:
        parts.append(f"scored but not in the skill/critic.md rubric: {', '.join(sorted(extra))}")
    return "critic reply does not match the skill/critic.md rubric — " + "; ".join(parts)


async def _critic(ctx: Ctx, lineage: str, findings: list[dict], shots: list[Path], stats: dict, ledger=None) -> tuple[dict | None, str, str, dict]:
    """-> (critic json | None, status, error/warning text, stats). Retries once before giving up."""
    if settings().llm_mock:
        return mock.critic(), CRITIC_OK, "", stats
    msgs = prompts.critic_messages(variant=lineage, plan=ctx.plan, content=ctx.content, qa_findings=findings, shots=shots,
                                   source_png=ctx.source_png, ledger=ledger)
    last = ""
    for attempt in range(2):
        try:
            r = await llm.chat(msgs, role=Role.review, temperature=0.2, thinking=settings().thinking_critic,
                               max_tokens=3000, guided_json=prompts.critic_schema(), stage="critic")
            stats = _add_stats(stats, r)
            data = extract_json(r.text)
            if not isinstance(data, dict):
                raise ValueError("critic reply was not a JSON object")
            warning = _criteria_mismatch(data)
            if warning:
                log.warning("%s", warning)
            return data, CRITIC_OK, warning, stats
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:300]
            log.warning("critic failed (attempt %d): %s", attempt + 1, last)
    return None, CRITIC_FAILED, last, stats


def _iter_rank(it: dict) -> tuple:
    """Which QA iteration to promote: truthful first, then fewest errors, then reviewed, then score, then latest.

    Truthfulness outranks everything below it. An attempt that changes a figure from the source must never
    be promoted over one that merely looks worse — a wrong number survives into the deck, a cramped card
    does not.

    Errors are counted rather than tested, because some are beyond the repair loop's reach: a slide whose
    source facts simply do not fit will carry a `fidelity-key` error on every attempt, and a boolean would
    then rank a repaired layout level with the broken one it replaced.
    """
    return (0 if any(f.get("fatal") for f in it["findings"]) else 1,
            -sum(1 for f in it["findings"] if f["severity"] == "error"),
            1 if it["critic_status"] == CRITIC_OK else 0, it["score"], it["attempt"])


def ensure_citations(spec: SlideSpec, plan: dict) -> list[str]:
    """Make the slide cite what its figures came from. The generator is told to; this does not rely on it:
    a document or library citation the spec's `sources` does not name is appended. Returns what was added."""
    want = [str(c) for c in plan.get(DOC_SOURCES_KEY) or []]
    lib = library_citation(plan)
    have = (spec.meta.sources or "").lower()
    # "Whitepaper.pdf, p. 4" is cited if the document is named at all — the page is a courtesy, not the test.
    missing = [c for c in want if c.split(", p.")[0].lower() not in have]
    if lib and lib.lower() not in have:
        missing.append(lib)
    if missing:
        spec.meta.sources = "; ".join(x for x in (spec.meta.sources.strip().rstrip(";."), *missing) if x)
    return missing


async def _qa_loop(v: Version, spec: SlideSpec, spec_issues: list, ctx: Ctx, stats: dict,
                   best_of: dict | None = None) -> None:
    s = settings()
    vision = await llm.vision_enabled()
    vdir = db.version_dir(v.project_id, v.id)
    iterations = []
    best = None
    tried: list[list[str]] = []  # issue codes handed to each earlier repair — the repair prompt's only memory
    for attempt in range(s.qa_max_repairs + 1):
        await aset_version(v.id, status="qa", stage_note="Rendering and checking" if attempt == 0 else f"Re-checking after repair {attempt}", llm=stats)
        idir = vdir / f"iter{attempt}"
        ensure_citations(spec, ctx.plan)  # every attempt: a repair returns a whole new spec
        # `prev_dir` lets the renderer diff this attempt's screenshot against the previous one, so a repair
        # that returned a cosmetically different but equivalent slide is visible instead of looking like progress.
        report = await check_spec(spec, ctx.slide.id, ctx.assets, idir, title=ctx.brief.get("deck_title", "QA"),
                                  prev_dir=(vdir / f"iter{attempt - 1}") if attempt else None)
        findings = [i.model_dump() for i in spec_issues if i.severity == "error" or i.code in ("external", "js-global-query")]
        findings += [f.model_dump() for f in report.findings]
        notes_text = " ".join(spec.meta.notes)
        lg = facts.ledger(ctx.facts, report.text, notes_text)
        findings += [f.model_dump() for f in ledger_findings(ctx.facts, report.text, notes_text)]
        findings += [f.model_dump() for f in chart_findings(ctx.content.get("charts") or [], getattr(report, "charts", []),
                                                             getattr(report, "unverified_charts", 0), ctx.plan.get("pattern", ""))]
        critic, critic_status, critic_note = None, CRITIC_SKIPPED, ""
        render_ok = not any(f["code"] in ("render", "no-slide") for f in findings)
        errors = [f for f in findings if f["severity"] == "error"]
        last_attempt = attempt == s.qa_max_repairs
        # A repair is already guaranteed by the DOM errors, so design advice about an overflowing slide is noise:
        # only spend the critic (up to 3 images per call) when its verdict can still change what happens.
        if not (vision or s.llm_mock) or not render_ok:
            critic_note = "vision disabled" if not (vision or s.llm_mock) else "slide did not render"
        elif errors and not last_attempt:
            critic_note = f"skipped — {len(errors)} blocking error(s) already force a repair"
        else:
            await aset_version(v.id, stage_note="Design review")
            critic, critic_status, critic_note, stats = await _critic(ctx, v.lineage, findings, [idir / n for n in report.shots], stats, ledger=lg)
        score = _score(findings, critic, critic_status)
        it = {"attempt": attempt, "score": score, "findings": findings, "critic": critic, "critic_status": critic_status,
              "critic_note": critic_note, "steps": report.steps, "shots": report.shots, "spec": spec.model_dump()}
        iterations.append(it)
        if best is None or _iter_rank(it) > _iter_rank(best):
            best = it
        if (not errors and _critic_passes(critic, critic_status)) or last_attempt:
            break
        issues = [f"[{f['code']}] {f['message']}" for f in errors]
        for i in (critic or {}).get("issues") or []:
            if isinstance(i, dict) and i.get("severity") in ("high", "medium"):
                issues.append(f"[{i.get('area', 'design')}] {i.get('problem', '')} → Fix: {i.get('fix', '')}")
        issues += [f"[{f['code']}] {f['message']}" for f in findings if f["severity"] == "warn"][:4]
        await aset_version(v.id, status="repairing", stage_note=f"Repairing {len(issues)} issue(s)", repairs=attempt + 1)
        if s.llm_mock:
            break
        final_shot = idir / "shot_final.png"
        codes = [f["code"] for f in errors] + [(i or {}).get("area", "design") for i in (critic or {}).get("issues") or []
                                               if isinstance(i, dict) and i.get("severity") in ("high", "medium")]
        history = prompts.repair_history(tried)
        tried.append(codes)

        def _repair_msgs(content: dict = ctx.content, spec=spec, issues=issues, history=history) -> list[dict]:
            return prompts.repair_messages(variant=v.lineage, position=ctx.position, plan=ctx.plan, content=content,
                                           spec=spec, slide_id=ctx.slide.id, issues=issues[:10], shot=final_shot,
                                           vision=vision, verbatim=ctx.verbatim, history=history)

        try:
            spec, spec_issues, stats = await _complete_spec(
                _repair_msgs(), ctx.slide.id, s.temp_repair, stats,
                rebuild=lambda: _repair_msgs(content=prompts.trimmed_for_retry(ctx.content)), stage="repair")
        except RuntimeError as e:
            log.warning("repair failed: %s", e)
            break
    # promote the best iteration
    bdir = vdir / f"iter{best['attempt']}"
    for name in ("shot_0.png", "shot_final.png"):
        (vdir / name).unlink(missing_ok=True)
        if (bdir / name).exists():
            shutil.copy2(bdir / name, vdir / name)
    fatal = [f for f in best["findings"] if f.get("fatal")]
    passed = not any(f["severity"] == "error" for f in best["findings"]) and _critic_passes(best["critic"], best["critic_status"])
    # `fatal` is reported separately from `findings` because it is the one QA outcome the review stage must
    # act on rather than display: the slide asserts something the source does not.
    qa = {"passed": passed, "fatal": [f["message"] for f in fatal],
          "findings": best["findings"], "critic": best["critic"], "steps": best["steps"], "shots": best["shots"],
          "iterations": [{"attempt": i["attempt"], "score": i["score"], "errors": sum(1 for f in i["findings"] if f["severity"] == "error"),
                          "critic_status": i["critic_status"]} for i in iterations], "vision": vision,
          "critic_status": best["critic_status"],
          "critic_error": best["critic_note"] if best["critic_status"] == CRITIC_FAILED else "",
          "critic_warning": best["critic_note"] if best["critic_status"] == CRITIC_OK else "",
          "critic_skipped_reason": best["critic_note"] if best["critic_status"] == CRITIC_SKIPPED else ""}
    if best_of:
        qa["best_of"] = best_of
    await aset_version(v.id, spec=best["spec"], qa=qa, score=best["score"], status="ready", stage_note="", llm=stats,
                       repairs=len(iterations) - 1)


async def _sample_best_of(n: int, build, ctx: Ctx, temp: float, vdir: Path, title: str,
                          rebuild) -> tuple[SlideSpec, list, dict, dict]:
    """Draw `n` variant-A drafts, DOM-check them all and keep the cleanest. -> (spec, issues, stats, record)

    The filter is the Playwright DOM check only — no LLM, no critic — because that is the cheap part of QA and it
    catches exactly the failures a resample fixes: overflow, clipping, overlap, a dead script. The survivors are
    then indistinguishable to the machine, so the tie is broken by warnings and then by order.

    Coupling to app/qa/render_check.py is deliberately one function and two fields: `check_spec(...)` and
    `report.findings[].severity`. Anything else about the report shape is read through .get()/getattr so a change
    there degrades to "no filtering", never to a crash.
    """
    draws = await asyncio.gather(*(_complete_spec(build(), ctx.slide.id, temp, {}, rebuild=rebuild) for _ in range(n)),
                                 return_exceptions=True)
    stats: dict = {}
    cands: list[tuple[SlideSpec, list]] = []
    for d in draws:
        if isinstance(d, BaseException):
            if isinstance(d, asyncio.CancelledError):
                raise d
            log.warning("best-of-%d: one draft failed: %s", n, d)
            continue
        spec, issues, st = d
        for k in ("calls", "prompt_tokens", "completion_tokens", "seconds"):
            stats[k] = round(stats.get(k, 0) + st.get(k, 0), 1) if k == "seconds" else stats.get(k, 0) + st.get(k, 0)
        cands.append((spec, issues))
    if not cands:
        raise RuntimeError(f"all {n} best-of drafts failed")
    reports = await asyncio.gather(*(check_spec(sp, ctx.slide.id, ctx.assets, vdir / f"draft{i}", title=title)
                                     for i, (sp, _) in enumerate(cands)), return_exceptions=True)
    rows = []
    for i, rep in enumerate(reports):
        if isinstance(rep, BaseException):
            if isinstance(rep, asyncio.CancelledError):
                raise rep
            rows.append({"draft": i, "errors": 99, "warns": 99, "note": f"{type(rep).__name__}: {rep}"[:120]})
            continue
        fs = [f.model_dump() for f in getattr(rep, "findings", [])]
        rows.append({"draft": i, "errors": sum(1 for f in fs if f.get("severity") == "error"),
                     "warns": sum(1 for f in fs if f.get("severity") == "warn"), "note": ""})
    pick = min(rows, key=lambda r: (r["errors"], r["warns"], r["draft"]))["draft"]
    spec, issues = cands[pick]
    record = {"n": n, "drafts": rows, "picked": pick,
              "clean": sum(1 for r in rows if not r["errors"]), "requested": n, "returned": len(cands)}
    log.info("best-of-%d for slide %s: %d clean of %d, picked draft %d", n, ctx.slide.id, record["clean"], len(rows), pick)
    return spec, issues, stats, record


async def generate_version(slide_id: str, lineage: str, *, parent_id: str | None = None, comment: str = "",
                           avoid: str = "", ctx: Ctx | None = None) -> Version | None:
    slide = ctx.slide if ctx is not None else await _db(db.get, Slide, slide_id)
    if slide is None:
        return None
    existing = [x for x in await _db(db.versions_of_slide, slide_id) if x.lineage == lineage]
    v = await _db(db.save, Version(slide_id=slide_id, project_id=slide.project_id, lineage=lineage,
                                   number=len(existing) + 1, parent_id=parent_id, comment=comment,
                                   status="generating",
                                   stage_note="Revising from your comment" if comment and parent_id
                                   else "Redesigning from your reasons" if comment else "Designing"))
    await aset_version(v.id, status="generating")
    s = settings()
    stats: dict = {}
    best_of_record: dict | None = None
    try:
        if ctx is None:
            ctx = await _db(Ctx, slide)
        vision = await llm.vision_enabled()
        if s.llm_mock:
            await asyncio.sleep(s.mock_delay_s)
            spec, spec_issues = parse_spec(to_tagged(mock.spec(ctx.content, ctx.plan, lineage)), slide.id)
        else:
            if comment and parent_id:
                versions = await _db(db.versions_of_slide, slide_id)
                base = await _db(db.get, Version, parent_id)
                other = next((x for x in reversed(versions) if x.lineage != lineage and x.status == "ready"), None)
                base_shot = db.version_dir(v.project_id, parent_id) / "shot_final.png"
                # Chosen again with the comment in the query: what the presenter asks for is often not what the
                # slide was about when it was first designed.
                passages = await _db(reference.slide_reference, slide.project_id, ctx.plan, ctx.content, comment)

                def build(content: dict = ctx.content) -> list[dict]:
                    return prompts.revise_messages(variant=lineage, position=ctx.position, plan=ctx.plan, content=content,
                                                   spec=SlideSpec.model_validate(base.spec), slide_id=slide.id, comment=comment,
                                                   other=SlideSpec.model_validate(other.spec) if other else None,
                                                   other_id=slide.id if other else None, shot=base_shot, vision=vision,
                                                   verbatim=ctx.verbatim, reference=passages,
                                                   doc_sources=ctx.plan.get(DOC_SOURCES_KEY) or [])
                temp = s.temp_repair + 0.2
            else:
                if ctx.design_log is None:  # normally precomputed once per slide by generate_slide
                    ctx.design_log = await _db(design_log, slide.project_id, slide.id)
                log_text = ctx.design_log

                def build(content: dict = ctx.content) -> list[dict]:
                    return prompts.generate_messages(variant=lineage, position=ctx.position, total=ctx.total, brief=ctx.brief,
                                                     plan=ctx.plan, content=content, prev_plan=ctx.prev_plan,
                                                     next_plan=ctx.next_plan, source_png=ctx.source_png, vision=vision,
                                                     verbatim=ctx.verbatim, design_log=log_text,
                                                     avoid="\n\n".join(x for x in (ctx.redesign, avoid) if x),
                                                     ledger=ctx.facts, reference=ctx.reference,
                                                     doc_sources=ctx.plan.get(DOC_SOURCES_KEY) or [],
                                                     library_source=library_citation(ctx.plan))
                temp = s.temp_a if lineage == "A" else s.temp_b
            def rebuild(build=build, ctx=ctx) -> list[dict]:
                return build(prompts.trimmed_for_retry(ctx.content))

            n = best_of_a() if (lineage == "A" and not comment) else 1
            if n > 1:
                await aset_version(v.id, stage_note=f"Designing {n} drafts")
                spec, spec_issues, stats, best_of_record = await _sample_best_of(
                    n, build, ctx, temp, db.version_dir(v.project_id, v.id), ctx.brief.get("deck_title", "QA"), rebuild)
            else:
                spec, spec_issues, stats = await _complete_spec(build(), slide.id, temp, stats, rebuild=rebuild)
        await _qa_loop(v, spec, spec_issues, ctx, stats, best_of=best_of_record)
    except asyncio.CancelledError:
        set_version(v.id, status="cancelled", stage_note="")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed")
        await aset_version(v.id, status="failed", error=str(e)[:500], stage_note="", llm=stats)
    return await _db(db.get, Version, v.id)


def _project_status_change(project_id: str) -> dict | None:
    """The database half of a project-status refresh: queries only, no event. Split out so the async path can
    run the queries on a worker thread and still publish the SSE event on the event loop — bus.publish ends in
    asyncio.Queue.put_nowait, which must never be called from another thread."""
    slides = [s for s in db.slides_of(project_id) if s.included]
    if not slides or any(s.status in ("generating", "revising") for s in slides):
        return None
    if all(s.status == "approved" for s in slides):
        return {"status": "complete", "stage_note": ""}
    if any(s.status in ("review", "approved", "error") for s in slides):
        return {"status": "reviewing", "stage_note": ""}
    return None


def _refresh_project_status(project_id: str) -> None:
    change = _project_status_change(project_id)
    if change:
        set_project(project_id, **change)


async def _arefresh_project_status(project_id: str) -> None:
    change = await _db(_project_status_change, project_id)
    if change:
        await aset_project(project_id, **change)


async def _diverge_variants(slide_id: str, results: list, ctx: Ctx | None = None) -> list:
    """The whole review UX is "pick A or B". Two near-identical options is a product failure, and temperature
    (0.8 vs 0.5) is the only mechanical difference between the two calls — nothing stops them converging on the
    same grid of cards.

    A and B still run concurrently (sequencing B behind A would double the wall-clock cost of every slide on the
    slowest stage of the pipeline). They are compared afterwards instead, and only B is rebuilt — with a compact
    description of A's composition, not its HTML — when the two came out structurally the same.
    """
    ready = {v.lineage: v for v in results if isinstance(v, Version) and v.status == "ready" and v.spec}
    if settings().llm_mock or set(ready) != {"A", "B"}:
        return results
    try:
        a, b = SlideSpec.model_validate(ready["A"].spec), SlideSpec.model_validate(ready["B"].spec)
    except Exception as e:  # noqa: BLE001
        log.warning("could not compare variants: %s", e)
        return results
    sim = ab_similarity(a, b)
    if sim <= AB_SIMILARITY_MAX:
        return results
    log.info("slide %s: A and B are %.0f%% structurally identical — rebuilding B", slide_id, sim * 100)
    await aset_version(ready["B"].id, stage_note=f"Too close to the cinematic variant ({sim:.0%}) — trying a different design")
    nv = await generate_version(slide_id, "B", avoid=prompts.contrast_note("A", structure_brief(a)), ctx=ctx)
    if isinstance(nv, Version) and nv.status == "ready" and nv.spec:
        again = ab_similarity(a, SlideSpec.model_validate(nv.spec))
        log.info("slide %s: rebuilt B is %.0f%% similar to A", slide_id, again * 100)
        return [r for r in results if not (isinstance(r, Version) and r.id == ready["B"].id)] + [nv]
    return results


async def generate_slide(slide_id: str, lineages: tuple[str, ...] = ("A", "B"), redesign: str = "",
                         comment: str = "") -> None:
    """Design the slide from its plan. `redesign` is why the user rejected the previous designs (reasons plus
    what those designs were built from), and goes into the prompt as something not to repeat; `comment` labels
    the new versions in the history."""
    await aset_slide(slide_id, status="generating", error="", approved_version_id=None)
    slide = await _db(db.get, Slide, slide_id)
    ctx = None
    if slide is not None:
        # one Ctx (and one design_log) for the whole slide: both variants ask identical questions of the database
        ctx = await _db(Ctx, slide)
        ctx.design_log = await _db(design_log, slide.project_id, slide.id)
        ctx.redesign = redesign
    results = await asyncio.gather(*(generate_version(slide_id, ln, ctx=ctx, comment=comment) for ln in lineages),
                                   return_exceptions=True)
    if any(isinstance(r, asyncio.CancelledError) for r in results):
        set_slide(slide_id, status="pending")
        raise asyncio.CancelledError
    if set(lineages) == {"A", "B"}:
        results = await _diverge_variants(slide_id, results, ctx)
        await judge_pair(slide_id, results, ctx)
    ok = any(isinstance(r, Version) and r.status == "ready" for r in results)
    await aset_slide(slide_id, status="review" if ok else "error",
                     error="" if ok else "Generation failed for both variants")
    if slide:
        await _arefresh_project_status(slide.project_id)


REDESIGN_REASONS = {
    "too-dense": "Too dense — too much on the slide; cut to the message and move detail to the speaker notes.",
    "wrong-layout": "Wrong layout — the composition does not fit this content; use a different structure.",
    "off-story": "Off-story — the slide does not make the point the deck needs here; lead with the key message.",
    "too-plain": "Too plain — it needs a stronger visual idea and hierarchy, not a list on a background.",
    "too-busy": "Too busy — too many visual elements competing; simplify and give one thing focus.",
    "facts-buried": "Key facts buried — the figures that carry the message must be the most prominent things.",
    "chart-wrong": "Chart is wrong — rebuild it from the source data exactly, same chart type, every category.",
}


def redesign_note(slide_id: str, reasons: list[str], note: str) -> tuple[str, str, list[str]]:
    """(the prompt section, the history label, the ids of the designs being replaced)."""
    latest: dict[str, Version] = {}
    for v in db.versions_of_slide(slide_id):
        if v.status == "ready" and v.spec:
            latest[v.lineage] = v
    lines = ["## Why this slide is being redesigned",
             "The user rejected the previous designs of this slide. Fix what they said; do not repeat those designs."]
    lines += [f"- {REDESIGN_REASONS.get(r, r)}" for r in reasons]
    if note.strip():
        lines.append(f'- In their words: "{note.strip()}"')
    for ln, v in sorted(latest.items()):
        lines += ["", f"The rejected variant {ln} was built like this — use a genuinely different composition:",
                  structure_brief(SlideSpec.model_validate(v.spec))]
    label = ", ".join(REDESIGN_REASONS.get(r, r).split(" — ")[0] for r in reasons)
    if note.strip():
        label = f"{label}: {note.strip()}" if label else note.strip()
    return "\n".join(lines), (f"Redesign: {label}" if label else ""), [v.id for v in latest.values()]


async def generate_project(project_id: str, slide_ids: list[str] | None = None) -> None:
    slides = [s for s in await _db(db.slides_of, project_id)
              if s.included and (slide_ids is None or s.id in slide_ids)]
    await aset_project(project_id, status="generating", stage_note=f"Generating {len(slides)} slide(s)")
    for s in slides:
        await aset_slide(s.id, status="generating")
    t0 = time.perf_counter()
    try:
        await asyncio.gather(*(generate_slide(s.id) for s in slides))
    finally:
        await _arefresh_project_status(project_id)
        await roll_up_stats(project_id, wall_seconds=time.perf_counter() - t0)


async def revise(slide_id: str, base_version_id: str, comment: str) -> Version | None:
    base = await _db(db.get, Version, base_version_id)
    await aset_slide(slide_id, status="revising", approved_version_id=None)
    try:
        v = await generate_version(slide_id, base.lineage, parent_id=base_version_id, comment=comment)
    finally:
        await aset_slide(slide_id, status="review")
        await _arefresh_project_status(base.project_id)
        await roll_up_stats(base.project_id)
    return v


# ------------------------------------------------------------------ deck-level LLM rollup
_STAT_KEYS = ("calls", "prompt_tokens", "completion_tokens")


def deck_stats(project_id: str) -> dict:
    """Sum every version's `llm` dict for one deck. `_add_stats` has always accumulated calls, tokens and seconds
    per version, but nothing added them up, so "what did this deck cost and how long did it take" had no answer
    anywhere in the product."""
    out = {k: 0 for k in _STAT_KEYS}
    out.update({"seconds": 0.0, "versions": 0, "repairs": 0})
    for v in db.versions_of_project(project_id):
        out["repairs"] += v.repairs or 0
        stats = v.llm or {}
        if not stats:
            continue
        out["versions"] += 1
        for k in _STAT_KEYS:
            out[k] += int(stats.get(k) or 0)
        out["seconds"] += float(stats.get("seconds") or 0)
    out["seconds"] = round(out["seconds"], 1)
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    return out


async def roll_up_stats(project_id: str, wall_seconds: float | None = None) -> dict:
    """Recompute Project.llm. `seconds` is summed model time across concurrent calls, so it is much larger than
    `wall_seconds` — both are kept because they answer different questions (spend vs. how long the user waited)."""
    st = await _db(deck_stats, project_id)
    prev = (await _db(db.get, Project, project_id)) if wall_seconds is None else None
    st["wall_seconds"] = round(wall_seconds, 1) if wall_seconds is not None else (prev.llm or {}).get("wall_seconds") if prev else None
    await _db(db.update, Project, project_id, touch=False, llm=st)
    return st


# ------------------------------------------------------------------ pairwise A/B judging
def _critic_avg(v: Version) -> float | None:
    scores = ((v.qa or {}).get("critic") or {}).get("scores")
    if not isinstance(scores, dict):
        return None
    vals = [float(scores.get(k, 0) or 0) for k in criteria() if k in scores]
    return round(sum(vals) / len(vals), 2) if vals else None


def _ab_order_swapped(slide_id: str) -> bool:
    """Alternate which variant is shown first, deterministically per slide. Position bias is the best-documented
    LLM-judge failure mode; the eval cancels it by judging both orders, but a per-slide call cannot afford a
    second request, so at least no single deck inherits one direction of the bias."""
    return sum(ord(c) for c in slide_id) % 2 == 1


async def judge_pair(slide_id: str, results: list, ctx: Ctx | None = None) -> dict | None:
    """Ask the model, once, which of the two finished variants is better, and record it on both versions.

    This exists because `critic_min_score` is a threshold on a noisy absolute score. Pairwise comparison is the
    easier question and it is the same question the review view puts to the user, so the answer is worth showing
    as a recommendation. The pointwise critic stays exactly where it was — it produces the issues[] the repair
    loop consumes, which is a generation task, not a ranking one.
    """
    ready = {v.lineage: v for v in results if isinstance(v, Version) and v.status == "ready" and v.spec}
    if set(ready) != {"A", "B"}:
        return None
    va, vb = ready["A"], ready["B"]
    base = {"versions": {"A": va.id, "B": vb.id}, "winner": "", "confidence": None, "reason": "",
            "order": "BA" if _ab_order_swapped(slide_id) else "AB"}

    async def record(rec: dict) -> dict:
        for v in (va, vb):
            mine = dict(rec)
            mine["recommended"] = bool(rec.get("winner")) and rec["winner"] == v.lineage
            await aset_version(v.id, qa={**(v.qa or {}), "ab": mine})
        return rec

    shot_a = db.version_dir(va.project_id, va.id) / "shot_final.png"
    shot_b = db.version_dir(vb.project_id, vb.id) / "shot_final.png"
    if settings().llm_mock:
        return await record({**base, "status": AB_SKIPPED, "note": "mock pipeline"})
    if not await llm.vision_enabled():
        return await record({**base, "status": AB_SKIPPED, "note": "vision disabled"})
    if not (shot_a.exists() and shot_b.exists()):
        return await record({**base, "status": AB_SKIPPED, "note": "one variant has no final screenshot"})
    if ctx is None:
        slide = await _db(db.get, Slide, slide_id)
        ctx = await _db(Ctx, slide) if slide else None
    if ctx is None:
        return await record({**base, "status": AB_SKIPPED, "note": "slide is gone"})
    swapped = _ab_order_swapped(slide_id)
    msgs = prompts.ab_messages(plan=ctx.plan, content=ctx.content, shot_a=shot_a, shot_b=shot_b,
                               steps_a=(va.qa or {}).get("steps", 0), steps_b=(vb.qa or {}).get("steps", 0),
                               swapped=swapped)
    try:
        r = await llm.chat(msgs, role=Role.review, temperature=0.1, max_tokens=800,
                           guided_json=prompts.AB_SCHEMA, stage="ab")
        data = extract_json(r.text)
        if not isinstance(data, dict) or data.get("winner") not in ("A", "B", "tie"):
            raise ValueError(f"unusable pairwise reply: {str(data)[:160]}")
        conf = data.get("confidence")
        rec = {**base, "status": AB_OK, "winner": data["winner"],
               "confidence": float(conf) if isinstance(conf, (int, float)) else None,
               "reason": str(data.get("reason") or "")[:400]}
        # the model's own stats belong to no single version; fold them into the winner's ledger so the deck
        # rollup still counts the call
        target = va if data["winner"] != "B" else vb
        await aset_version(target.id, llm=_add_stats(target.llm or {}, r))
        return await record(rec)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("pairwise A/B judge failed for slide %s: %s", slide_id, e)
        return await record({**base, "status": AB_FAILED, "error": f"{type(e).__name__}: {e}"[:300]})


def ab_winner(v: Version) -> str:
    ab = (v.qa or {}).get("ab") or {}
    return ab.get("winner") or "" if ab.get("status") == AB_OK else ""


def choose(slide_id: str, version_id: str, *, source: str = "user") -> Slide:
    """Approve one version — and record the decision, permanently.

    The pick is the only ground truth the system ever gets: a person compared two finished slides, with both QA
    reports and both scores in front of them, and said which was better. It used to be thrown away the instant
    the status changed. `db.Choice` keeps it, which is what makes judge-human agreement measurable (see
    evals/run_eval.py) and what would make a later fine-tune possible at all.
    """
    try:
        _log_choice(slide_id, version_id, source)
    except Exception:  # noqa: BLE001 - logging the decision must never block making it
        log.exception("could not record the human choice for slide %s", slide_id)
    s = set_slide(slide_id, status="approved", approved_version_id=version_id)
    _refresh_project_status(s.project_id)
    return s


def _log_choice(slide_id: str, version_id: str, source: str) -> None:
    slide = db.get(Slide, slide_id)
    versions = db.versions_of_slide(slide_id)
    chosen = next((v for v in versions if v.id == version_id), None)
    if slide is None or chosen is None:
        return
    ready = [v for v in versions if v.status == "ready"]
    # what was passed over: the newest ready version of the other lineage (that is the A/B the user was shown)
    rejected = next((v for v in reversed(ready) if v.lineage != chosen.lineage), None)
    project = db.get(Project, slide.project_id)
    # the pairwise verdict is written identically on both versions; read whichever one still has it
    winner = ab_winner(chosen) or (ab_winner(rejected) if rejected is not None else "")
    ab = (chosen.qa or {}).get("ab") or {}
    judge_agrees = None
    if winner in ("A", "B"):
        judge_agrees = winner == chosen.lineage
    score_agrees = None
    if rejected is not None and chosen.score is not None and rejected.score is not None and chosen.score != rejected.score:
        score_agrees = chosen.score > rejected.score
    db.log_choice(
        project_id=slide.project_id, slide_id=slide_id, slide_index=slide.index,
        deck=(project.deck_title or project.name) if project else "", pattern=(slide.plan or {}).get("pattern", ""),
        chosen_version_id=chosen.id, chosen_lineage=chosen.lineage, chosen_score=chosen.score,
        chosen_critic=_critic_avg(chosen),
        rejected_version_id=rejected.id if rejected else "", rejected_lineage=rejected.lineage if rejected else "",
        rejected_score=rejected.score if rejected else None,
        rejected_critic=_critic_avg(rejected) if rejected else None,
        judge_winner=winner, judge_confidence=ab.get("confidence"), judge_agrees=judge_agrees,
        score_agrees=score_agrees, comment=(chosen.comment or "")[:500], candidates=len(ready), source=source)


def unapprove(slide_id: str) -> Slide:
    s = set_slide(slide_id, status="review", approved_version_id=None)
    _refresh_project_status(s.project_id)
    return s


# ------------------------------------------------------------------ export
def _version_rank(v: Version) -> tuple:
    """Rank a version for auto-selection.

    In order: a critiqued version always outranks one the critic never reviewed (so a critic timeout cannot
    promote an unreviewed variant into the export); then the pointwise score, but *banded* — pairwise judging
    breaks the tie inside a band of AB_SCORE_BAND, because two absolute critic scores that close are noise,
    while a bigger gap is signal the comparison should not override; then the raw score; then recency.
    """
    critiqued = 1 if (v.qa or {}).get("critic_status", CRITIC_OK) == CRITIC_OK else 0
    score = v.score or 0
    band = round(score / AB_SCORE_BAND)
    won = 1 if ab_winner(v) == v.lineage else 0
    return (critiqued, band, won, score, v.created_at)


def best_version(slide: Slide) -> Version | None:
    if slide.approved_version_id:
        v = db.get(Version, slide.approved_version_id)
        if v and v.status == "ready":
            return v
    ready = [v for v in db.versions_of_slide(slide.id) if v.status == "ready"]
    return max(ready, key=_version_rank) if ready else None


APPENDIX_DIVIDER_ID = "appendix"


def appendix_divider() -> SlideSpec:
    """The fixed section slide that opens the backup slides (see deckops.APPENDIX_SPEC)."""
    from .deckops import APPENDIX_SPEC

    spec, _ = parse_spec(APPENDIX_SPEC, APPENDIX_DIVIDER_ID)
    return spec


def build_deck(project_id: str, *, fill_unapproved: bool = True, asset_base: str | None = None, embed: bool = False) -> tuple[str, dict]:
    p = db.get(Project, project_id)
    slides = []
    stats = {"approved": 0, "filled": 0, "skipped": 0}
    for s in db.slides_of(project_id):
        if not s.included:
            continue
        v, kind = None, ""
        if s.approved_version_id:
            v, kind = db.get(Version, s.approved_version_id), "approved"
        elif fill_unapproved:
            v, kind = best_version(s), "filled"
        if v is None or not v.spec:  # an approved version with an empty spec is skipped, and only skipped
            stats["skipped"] += 1
            continue
        stats[kind] += 1
        if (s.plan or {}).get(APPENDIX_KEY) and not any(x.id == APPENDIX_DIVIDER_ID for x in slides):
            slides.append(DeckSlide(id=APPENDIX_DIVIDER_ID, spec=appendix_divider()))
        slides.append(DeckSlide(id=s.id, spec=SlideSpec.model_validate(v.spec)))
    title = p.deck_title or p.name
    html = assemble(DeckInput(title=title, slides=slides, assets=db.asset_files(project_id), storage_key=project_id),
                    asset_base=asset_base, embed=embed)
    return html, stats


def recover_interrupted() -> None:
    """Server restarted: mark in-flight work as failed so the UI can retry."""
    with db.session() as s:
        for v in s.exec(db.select(Version).where(Version.status.in_(["queued", "generating", "qa", "repairing"]))):
            v.status, v.stage_note, v.error = "failed", "", "Interrupted by server restart"
            s.add(v)
        for sl in s.exec(db.select(Slide).where(Slide.status.in_(["generating", "revising"]))):
            sl.status = "error"
            sl.error = "Interrupted by server restart"
            s.add(sl)
        for p in s.exec(db.select(Project).where(Project.status.in_(["ingesting", "planning", "generating"]))):
            if p.status == "generating":
                p.status = "reviewing"
            else:
                p.status, p.error = "error", "Interrupted by server restart — re-upload or re-plan"
            p.stage_note = ""
            s.add(p)
        s.commit()
