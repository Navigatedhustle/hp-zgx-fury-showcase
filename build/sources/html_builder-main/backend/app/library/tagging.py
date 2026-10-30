"""Favourite → summary, slide type, tags and entities from the review model; the tag vocabulary.

`enqueue` is the fixed interface other modules call. It marks slides "pending" and hands them to one background
worker per event loop (runner.jobs, key common.CHANNEL, so the calls bill to "library"), which tags at most
CONCURRENCY slides at a time — the LLM client's own semaphore still caps the process as a whole.

One review-model call per slide: the system prefix is `review_system_prompt()` (byte-stable, shared with the
critic), the vocabulary and the slide go in the user message, and the vocabulary is also an enum in the guided-JSON
schema so a compliant server cannot invent a tag. What comes back is still validated and normalised here, because
a server without guided decoding can. User edits (`tags_user`, `summary_user`) are never overwritten.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Iterable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text as sql
from sqlmodel import select

from ..config import Role, settings
from ..ingest.pptx_parse import SlideContent
from ..llm import client as llm
from ..skillpack import read, review_system_prompt
from ..spec import extract_json
from ..store import db
from ..store.db import LibDeck, LibSlide, LibTag, now
from . import common, search, taxonomy
from .schema import slide_out, tag_out

log = logging.getLogger(__name__)
router = APIRouter()

STAGE = "library_tag"     # the usage-ledger label
CONCURRENCY = 3           # slides tagged at once
ATTEMPTS = 2              # per slide; the error of the last one is kept on ai_error
MAX_TAGS = 4
MAX_SUGGESTIONS = 2
MAX_ENTITIES = 8
SUMMARY_WORDS = 40
CONTENT_CHARS = 8000      # the slide's JSON in the prompt; a dense table beyond this adds nothing to a summary
REPLY_TOKENS = 700

_queue: list[str] = []                          # FIFO of slide ids waiting for the worker
_worker: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None  # the app's loop, for enqueue() from a worker thread


# ------------------------------------------------------------------ queue

def enqueue(slide_ids: list[str]) -> None:
    """Mark these slides ai_status="pending" and tag them in the background (runner.jobs, key common.CHANNEL).

    Safe from the event loop and from a worker thread (ingest runs parts of itself in `asyncio.to_thread`). With no
    loop at all (a script) the slides simply stay pending and `recover_interrupted()` picks them up next start."""
    ids = list(dict.fromkeys(i for i in slide_ids if i))
    if not ids:
        return
    with db.session() as s:
        rows = [r for r in (s.get(LibSlide, i) for i in ids) if r is not None]
        for r in rows:
            r.ai_status, r.ai_error = "pending", ""
            s.add(r)
        s.commit()
    for r in rows:
        common.emit("slide", slide_id=r.id, ai_status="pending")
        if r.id not in _queue:
            _queue.append(r.id)
    _kick()


def _kick() -> None:
    global _loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        if _loop is not None and _loop.is_running():
            _loop.call_soon_threadsafe(_kick)
        return
    _loop = loop
    global _worker
    if _worker is not None and not _worker.done() and _worker.get_loop() is loop:
        return
    from ..pipeline.runner import jobs
    _worker = jobs.spawn(common.CHANNEL, _drain())


async def _drain() -> None:
    inflight: set[asyncio.Task] = set()
    while _queue or inflight:
        while _queue and len(inflight) < CONCURRENCY:
            inflight.add(asyncio.create_task(tag_slide(_queue.pop(0))))
        done, inflight = await asyncio.wait(inflight, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if not t.cancelled() and t.exception():
                log.error("library tagging task failed: %s", t.exception())


def recover_interrupted() -> int:
    """Re-queue slides a previous run left "pending" (the app stopped mid-batch). Call once at startup, inside the
    running loop (FastAPI lifespan). Returns how many were queued."""
    with db.session() as s:
        ids = list(s.exec(select(LibSlide.id).where(LibSlide.ai_status == "pending")))
    if ids:
        log.info("library: re-queueing %d slides left pending", len(ids))
        enqueue(ids)
    return len(ids)


# ------------------------------------------------------------------ one slide

async def tag_slide(slide_id: str) -> None:
    """Tag one slide. Never raises (but for cancellation): a failure is recorded on the slide, and the batch goes on."""
    slide = await asyncio.to_thread(db.get, LibSlide, slide_id)
    if slide is None:
        return
    deck = await asyncio.to_thread(db.get, LibDeck, slide.deck_id)
    error = ""
    for attempt in range(ATTEMPTS):
        try:
            if settings().llm_mock:
                result = await asyncio.to_thread(mock_result, slide)
            else:
                result = await _ask_model(slide, deck)
            await asyncio.to_thread(apply_result, slide_id, result)
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"[:300]
            log.warning("library tagging %s failed (attempt %d): %s", slide_id, attempt + 1, error)
    await asyncio.to_thread(db.update, LibSlide, slide_id, ai_status="error", ai_error=error, touch=False)
    common.emit("slide", slide_id=slide_id, ai_status="error")


def schema(slugs: list[str]) -> dict:
    """The guided-JSON schema. Topic tags are an enum of the approved slugs, so a guided server cannot invent one."""
    tag_item: dict = {"type": "string", "enum": slugs} if slugs else {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "maxLength": 400},
            "slide_type": {"type": "string", "enum": list(taxonomy.SLIDE_TYPES)},
            "topic_tags": {"type": "array", "items": tag_item, "maxItems": MAX_TAGS},
            "entities": {"type": "array", "maxItems": MAX_ENTITIES, "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "type": {"type": "string", "enum": list(taxonomy.ENTITY_TYPES)}},
                "required": ["name", "type"]}},
            "new_tag_suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_SUGGESTIONS},
        },
        "required": ["summary", "slide_type", "topic_tags", "entities", "new_tag_suggestions"],
    }


def _content(slide: LibSlide) -> dict:
    try:
        out = SlideContent.model_validate(slide.content).for_prompt() if slide.content else {}
    except Exception:  # noqa: BLE001 - an older or partial content dict must not stop tagging
        out = {}
    if not out.get("title") and slide.title:
        out["title"] = slide.title
    if len(out) <= 1 and slide.text:
        out["text"] = slide.text
    if slide.notes and "speaker_notes" not in out:
        out["speaker_notes"] = slide.notes
    return out


def _vocab_text(tags: list[LibTag]) -> str:
    lines = []
    for facet in taxonomy.FACETS:
        rows = [t for t in tags if t.approved and t.facet == facet]
        if rows:
            lines.append(f"{facet}: " + "; ".join(f"{t.slug} — {t.label}" for t in rows))
    return "\n".join(lines)


def user_prompt(slide: LibSlide, deck: LibDeck | None, tags: list[LibTag], *, image: bool) -> str:
    body = json.dumps(_content(slide), ensure_ascii=False)
    if len(body) > CONTENT_CHARS:
        body = body[:CONTENT_CHARS] + " …[cut]"
    deck_lines = [f"- Project: {deck.project or '(none)'}", f"- Deck: {deck.title or deck.filename or '(untitled)'}",
                  f"- Slide {slide.index} of {deck.slide_count or '?'}"] if deck else [f"- Slide {slide.index}"]
    from ..pipeline.prompts import fill
    return fill(read("library_tag.md"), DECK="\n".join(deck_lines), CONTENT=body, VOCAB=_vocab_text(tags),
                IMAGE_NOTE="The rendered slide is attached; its parsed text follows." if image
                else "No picture is available; this is the slide's parsed text.",
                SLIDE_TYPES=", ".join(taxonomy.SLIDE_TYPES), ENTITY_TYPES=", ".join(taxonomy.ENTITY_TYPES))


async def _ask_model(slide: LibSlide, deck: LibDeck | None) -> dict:
    tags = await asyncio.to_thread(taxonomy.all_tags)
    render = common.render_path(slide.deck_id, slide.index)
    image = render.exists() and await llm.vision_enabled()
    text = user_prompt(slide, deck, tags, image=image)
    user = {"role": "user", "content": [llm.image_part(render), {"type": "text", "text": text}]} if image \
        else {"role": "user", "content": text}
    r = await llm.chat([{"role": "system", "content": review_system_prompt()}, user], role=Role.review,
                       temperature=0.2, max_tokens=REPLY_TOKENS, guided_json=schema(taxonomy.approved_slugs(tags)),
                       stage=STAGE)
    return extract_json(r.text)


# ------------------------------------------------------------------ mock

def _terms(t: LibTag) -> list[str]:
    out = {t.label.lower(), t.slug.replace("-", " ")}
    out |= {a.replace("-", " ") for a in t.aliases or []}
    return [x for x in out if len(x) >= 2]


def mock_result(slide: LibSlide) -> dict:
    """Deterministic stand-in for the model: vocabulary keyword hits (title counts triple), a summary from the
    title and the first line, a slide type from the content's shape."""
    tags = taxonomy.all_tags()
    title = (slide.title or "").lower()
    body = (slide.text or "").lower()
    scores: dict[str, int] = {}
    for t in tags:
        if not t.approved:
            continue
        n = 0
        for term in _terms(t):
            rx = re.compile(r"(?<![a-z0-9])" + re.escape(term).replace(r"\ ", r"[\s\-]+") + r"s?(?![a-z0-9])")
            n += 3 * len(rx.findall(title)) + len(rx.findall(body))
        if n:
            scores[t.slug] = n
    topic = [s for s, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))][:MAX_TAGS]
    first = next((ln.strip() for ln in (slide.text or "").splitlines() if ln.strip() and ln.strip() != slide.title), "")
    summary = ". ".join(x for x in (slide.title.strip(), first) if x)
    return {"summary": summary, "slide_type": _mock_type(slide, title, body), "topic_tags": topic,
            "entities": [], "new_tag_suggestions": []}


def _mock_type(slide: LibSlide, title: str, body: str) -> str:
    c = slide.content or {}
    if c.get("charts"):
        return "data-chart"
    if c.get("tables"):
        return "table"
    if re.search(r"\bagenda\b", title):
        return "agenda"
    if re.search(r"thank|questions|q&a", title):
        return "closing"
    if re.search(r"roadmap|timeline", title):
        return "timeline-roadmap"
    if re.search(r"\bvs\.?\b|versus|comparison|compare", title):
        return "comparison"
    if re.search(r"summary|takeaway|conclusion", title):
        return "summary"
    if slide.index == 1:
        return "title"
    if len(body.split()) < 8:
        return "section-divider"
    return "other"


# ------------------------------------------------------------------ validate + apply

def _clip_words(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^(this|the) slide (shows|presents|describes|outlines|illustrates)\s*(that\s+)?", "", text, flags=re.I)
    words = text.split(" ")
    if len(words) > n:
        text = " ".join(words[:n]).rstrip(",;:") + "…"
    return text[:1].upper() + text[1:]


def clean_result(raw: dict, tags: list[LibTag]) -> dict:
    """Validate a model reply against the vocabulary. Unknown topic tags and the model's own suggestions become
    suggestions (≤2) unless they normalise onto a known tag; a known-but-unapproved slug stays a suggestion."""
    if not isinstance(raw, dict):
        raise ValueError("the reply is not a JSON object")
    table = taxonomy.alias_map(tags)
    by_slug = {t.slug: t for t in tags}
    topic: list[str] = []
    suggested: list[str] = []
    labels: dict[str, str] = {}

    def place(spelling: str) -> None:
        slug = taxonomy.normalise(str(spelling), table)
        if not slug or len(slug) > 48:
            return
        t = by_slug.get(slug)
        if t is not None and t.approved:
            # also a "new" suggestion that is really a known spelling: it is just that tag
            if slug not in topic and len(topic) < MAX_TAGS:
                topic.append(slug)
        elif slug not in suggested and len(suggested) < MAX_SUGGESTIONS:
            suggested.append(slug)
            labels.setdefault(slug, str(spelling).strip()[:60])

    for x in [*(raw.get("topic_tags") or []), *(raw.get("new_tag_suggestions") or [])]:
        place(x)

    kind = str(raw.get("slide_type") or "").strip().lower()
    kind = taxonomy.slugify(kind)
    if kind not in taxonomy.SLIDE_TYPES:
        kind = "other"

    entities: list[dict] = []
    seen: set[str] = set()
    for e in raw.get("entities") or []:
        if not isinstance(e, dict):
            continue
        name = re.sub(r"\s+", " ", str(e.get("name") or "")).strip()[:80]
        etype = str(e.get("type") or "").strip().lower()
        if not name or etype not in taxonomy.ENTITY_TYPES or name.lower() in seen:
            continue
        seen.add(name.lower())
        entities.append({"name": name, "type": etype})
        if len(entities) >= MAX_ENTITIES:
            break

    return {"summary": _clip_words(str(raw.get("summary") or ""), SUMMARY_WORDS), "slide_type": kind,
            "tags": topic, "entities": entities, "suggested": suggested, "labels": labels}


def apply_result(slide_id: str, raw: dict) -> None:
    """Write one reply to its slide: user-locked fields untouched, new suggestions stored as unapproved tags."""
    tags = taxonomy.all_tags()
    res = clean_result(raw, tags)
    known = {t.slug for t in tags}
    with db.session() as s:
        for slug in res["suggested"]:
            if slug not in known:
                s.add(LibTag(slug=slug, label=_label(res["labels"].get(slug) or slug), facet="topic", approved=False))
        row = s.get(LibSlide, slide_id)
        if row is None:
            return
        if not row.slide_type_user:
            row.slide_type = res["slide_type"]
        row.entities = res["entities"]
        row.suggested = res["suggested"]
        if not row.tags_user:
            row.tags = res["tags"]
        if not row.summary_user:
            row.summary = res["summary"]
        row.ai_status, row.ai_error, row.updated_at = "done", "", now()
        s.add(row)
        s.commit()
    _reindex([slide_id])
    common.emit("slide", slide_id=slide_id, ai_status="done")
    if any(slug not in known for slug in res["suggested"]):
        common.emit("tags")


def _label(spelling: str) -> str:
    s = re.sub(r"[-_]+", " ", spelling).strip()
    return s[:1].upper() + s[1:] if s.islower() else s


def _reindex(slide_ids: Iterable[str]) -> None:
    ids = list(dict.fromkeys(slide_ids))
    if not ids:
        return
    try:
        search.reindex(ids)
    except Exception:  # noqa: BLE001 - a stale index row is recoverable; a lost tag write is not
        log.exception("library search reindex failed for %d slides", len(ids))


# ------------------------------------------------------------------ queries

def _slides_with(slug: str, column: str = "tags") -> list[str]:
    """Slide ids whose JSON list `column` (tags | suggested) contains `slug`."""
    assert column in ("tags", "suggested")
    with db.engine().connect() as c:
        rows = c.execute(sql(f"SELECT DISTINCT libslide.id FROM libslide, json_each(libslide.{column}) "
                             "WHERE json_each.value = :slug"), {"slug": slug})
        return [r[0] for r in rows]


def tag_counts() -> dict[str, int]:
    with db.engine().connect() as c:
        rows = c.execute(sql("SELECT json_each.value, count(*) FROM libslide, json_each(libslide.tags) "
                             "GROUP BY json_each.value"))
        return {r[0]: r[1] for r in rows}


def _resolve_user_tags(spellings: Iterable[str]) -> list[str]:
    """Tags the user typed: a known spelling maps onto its tag (and approves a suggestion — the user chose it);
    an unknown one becomes a new approved topic tag."""
    tags = taxonomy.all_tags()
    table = taxonomy.alias_map(tags)
    by_slug = {t.slug: t for t in tags}
    out: list[str] = []
    created = False
    with db.session() as s:
        for spelling in spellings:
            slug = taxonomy.normalise(str(spelling), table)
            if not slug or slug in out:
                continue
            t = by_slug.get(slug)
            if t is None:
                t = LibTag(slug=slug, label=_label(str(spelling).strip()[:60]), facet="topic", approved=True)
                s.add(t)
                by_slug[slug] = t
                table[taxonomy.base_form(slug)] = slug
                created = True
            elif not t.approved:
                row = s.get(LibTag, slug)
                row.approved = True
                s.add(row)
                created = True
            out.append(slug)
        s.commit()
    if created:
        common.emit("tags")
    return out


def _slide(slide_id: str) -> LibSlide:
    s = db.get(LibSlide, slide_id)
    if s is None:
        raise HTTPException(404, "Slide not found")
    return s


def _out(slide_id: str) -> dict:
    s = _slide(slide_id)
    return slide_out(s, db.get(LibDeck, s.deck_id))


def _get_tag(slug: str) -> LibTag:
    taxonomy.ensure_seeded()
    t = db.get(LibTag, slug)
    if t is None:
        raise HTTPException(404, "Tag not found")
    return t


# ------------------------------------------------------------------ slides

class SlidePatch(BaseModel):
    favourite: bool | None = None
    tags: list[str] | None = None
    summary: str | None = None
    slide_type: str | None = None


@router.patch("/slides/{slide_id}")
async def patch_slide(slide_id: str, body: SlidePatch) -> dict:
    """User edits. Setting tags or a summary locks that field against re-tagging; an empty summary unlocks it
    (the model writes one next time). Favouriting an untagged (or failed) slide queues it for tagging."""
    slide = _slide(slide_id)
    fields: dict = {}
    if body.slide_type is not None:
        kind = taxonomy.slugify(body.slide_type)
        if kind not in taxonomy.SLIDE_TYPES:
            raise HTTPException(400, f"Unknown slide type '{body.slide_type}'")
        fields["slide_type"] = kind
        fields["slide_type_user"] = True
    if body.tags is not None:
        fields["tags"] = _resolve_user_tags(body.tags)
        fields["tags_user"] = True
    if body.summary is not None:
        fields["summary"] = body.summary.strip()[:600]
        fields["summary_user"] = bool(fields["summary"])
    if body.favourite is not None and body.favourite != slide.favourite:
        fields["favourite"] = body.favourite
        fields["favourited_at"] = now() if body.favourite else None
    if fields:
        db.update(LibSlide, slide_id, **fields)
        _reindex([slide_id])
    if body.favourite and slide.ai_status in ("none", "error"):
        enqueue([slide_id])
    return _out(slide_id)


class BulkBody(BaseModel):
    slide_ids: list[str]
    favourite: bool | None = None
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None


@router.post("/slides/bulk")
async def bulk(body: BulkBody) -> dict:
    """Favourite/unfavourite and add/remove tags on many slides. A hand-added or hand-removed tag locks the tags."""
    add = _resolve_user_tags(body.add_tags or [])
    table = taxonomy.alias_map()
    remove = {taxonomy.normalise(x, table) for x in body.remove_tags or []} - {""}
    to_tag: list[str] = []
    changed: list[str] = []
    with db.session() as s:
        for sid in dict.fromkeys(body.slide_ids):
            row = s.get(LibSlide, sid)
            if row is None:
                continue
            dirty = False
            if body.favourite is not None and row.favourite != body.favourite:
                row.favourite = body.favourite
                row.favourited_at = now() if body.favourite else None
                dirty = True
                if body.favourite and row.ai_status in ("none", "error"):
                    to_tag.append(sid)
            if add or remove:
                tags = [t for t in row.tags or [] if t not in remove]
                tags += [t for t in add if t not in tags]
                if tags != (row.tags or []):
                    row.tags, row.tags_user, dirty = tags, True, True
            if dirty:
                row.updated_at = now()
                s.add(row)
                changed.append(sid)
        s.commit()
    _reindex(changed)
    for sid in changed:
        common.emit("slide", slide_id=sid, ai_status=db.get(LibSlide, sid).ai_status)
    enqueue(to_tag)
    return {"updated": len(changed)}


@router.post("/slides/{slide_id}/retag")
async def retag(slide_id: str) -> dict:
    _slide(slide_id)
    enqueue([slide_id])
    return _out(slide_id)


@router.post("/decks/{deck_id}/tag-all")
async def tag_all(deck_id: str) -> dict:
    """Every slide of one deck, favourite or not."""
    if db.get(LibDeck, deck_id) is None:
        raise HTTPException(404, "Deck not found")
    with db.session() as s:
        ids = list(s.exec(select(LibSlide.id).where(LibSlide.deck_id == deck_id).order_by(LibSlide.index)))
    enqueue(ids)
    return {"queued": len(ids)}


# ------------------------------------------------------------------ vocabulary

@router.get("/taxonomy")
def get_taxonomy() -> dict:
    return taxonomy.taxonomy()


@router.get("/tags")
def list_tags() -> list[dict]:
    counts = tag_counts()
    return [tag_out(t, counts.get(t.slug, 0)) for t in taxonomy.all_tags()]


class TagNew(BaseModel):
    label: str
    facet: str = "topic"


class TagPatch(BaseModel):
    label: str | None = None
    facet: str | None = None
    aliases: list[str] | None = None


class TagMerge(BaseModel):
    from_: list[str] = Field(alias="from")
    into: str


def _facet(facet: str) -> str:
    f = (facet or "").strip().lower()
    if f not in taxonomy.FACETS:
        raise HTTPException(400, f"Unknown facet '{facet}' — one of {', '.join(taxonomy.FACETS)}")
    return f


@router.post("/tags")
def create_tag(body: TagNew) -> dict:
    label = body.label.strip()
    facet = _facet(body.facet)
    slug = taxonomy.normalise(label)
    if not slug:
        raise HTTPException(400, "A tag needs a name")
    existing = db.get(LibTag, slug)
    if existing is not None:
        raise HTTPException(409, f"'{existing.label}' already exists" + ("" if existing.approved else " as a suggestion"))
    t = db.save(LibTag(slug=slug, label=label[:60], facet=facet, approved=True))
    common.emit("tags")
    return tag_out(t)


@router.patch("/tags/{slug}")
def patch_tag(slug: str, body: TagPatch) -> dict:
    t = _get_tag(slug)
    fields: dict = {}
    if body.label is not None and body.label.strip():
        fields["label"] = body.label.strip()[:60]
    if body.facet is not None:
        fields["facet"] = _facet(body.facet)
    if body.aliases is not None:
        own = taxonomy.base_form(slug)
        aliases = list(dict.fromkeys(a for a in (taxonomy.base_form(x) for x in body.aliases) if a and a != own))
        with db.session() as s:
            others = {taxonomy.base_form(o.slug): o.label for o in s.exec(select(LibTag)) if o.slug != slug}
        clash = [a for a in aliases if a in others]
        if clash:
            raise HTTPException(409, f"'{clash[0]}' is already the tag '{others[clash[0]]}'")
        fields["aliases"] = aliases
    with db.session() as s:
        row = s.get(LibTag, t.slug)
        for k, v in fields.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()
        s.refresh(row)
    _reindex(_slides_with(slug))   # labels and aliases are searchable
    common.emit("tags")
    return tag_out(row, tag_counts().get(slug, 0))


@router.post("/tags/merge")
def merge_tags(body: TagMerge) -> dict:
    """Fold tags into one: every slide is rewritten, and each merged tag (and its aliases) becomes an alias."""
    into = _get_tag(body.into)
    sources = [x for x in dict.fromkeys(body.from_) if x != into.slug]
    if not sources:
        raise HTTPException(400, "Nothing to merge")
    gone = [_get_tag(x) for x in sources]
    names = {x.slug for x in gone}
    affected = set()
    for slug in names:
        affected |= set(_slides_with(slug)) | set(_slides_with(slug, "suggested"))
    with db.session() as s:
        for sid in affected:
            row = s.get(LibSlide, sid)
            tags = [into.slug if t in names else t for t in row.tags or []]
            sug = [into.slug if t in names else t for t in row.suggested or []]
            row.tags = list(dict.fromkeys(tags))
            row.suggested = [t for t in dict.fromkeys(sug) if t not in row.tags]
            row.updated_at = now()
            s.add(row)
        target = s.get(LibTag, into.slug)
        own = taxonomy.base_form(into.slug)
        aliases = list(target.aliases or [])
        for g in gone:
            aliases += [taxonomy.base_form(g.slug), *(g.aliases or [])]
            s.delete(s.get(LibTag, g.slug))
        target.aliases = [a for a in dict.fromkeys(aliases) if a and a != own]
        s.add(target)
        s.commit()
        s.refresh(target)
    _reindex(sorted(affected | set(_slides_with(into.slug))))
    common.emit("tags")
    return tag_out(target, tag_counts().get(into.slug, 0))


@router.post("/tags/{slug}/approve")
def approve_tag(slug: str) -> dict:
    """Accept a model suggestion: the tag joins the vocabulary and is applied to every slide that suggested it
    (except where the user has set the tags by hand — there it simply stops being a suggestion)."""
    t = _get_tag(slug)
    ids = _slides_with(slug, "suggested")
    with db.session() as s:
        row = s.get(LibTag, t.slug)
        row.approved = True
        s.add(row)
        for sid in ids:
            sl = s.get(LibSlide, sid)
            sl.suggested = [x for x in sl.suggested or [] if x != slug]
            if not sl.tags_user and slug not in (sl.tags or []):
                sl.tags = [*(sl.tags or []), slug]
            sl.updated_at = now()
            s.add(sl)
        s.commit()
        s.refresh(row)
    _reindex(ids)
    common.emit("tags")
    return tag_out(row, tag_counts().get(slug, 0))


@router.delete("/tags/{slug}")
def delete_tag(slug: str) -> dict:
    """Remove a tag (or reject a suggestion): it leaves the vocabulary and every slide."""
    _get_tag(slug)
    ids = sorted(set(_slides_with(slug)) | set(_slides_with(slug, "suggested")))
    with db.session() as s:
        for sid in ids:
            sl = s.get(LibSlide, sid)
            sl.tags = [x for x in sl.tags or [] if x != slug]
            sl.suggested = [x for x in sl.suggested or [] if x != slug]
            sl.updated_at = now()
            s.add(sl)
        s.delete(s.get(LibTag, slug))
        s.commit()
    _reindex(ids)
    common.emit("tags")
    return {"deleted": slug, "slides": len(ids)}
