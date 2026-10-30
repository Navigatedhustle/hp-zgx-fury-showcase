"""HTTP API + SSE + static frontend."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from . import assemble as assembler
from . import compose
from . import edit as editor
from . import skillpack
from .assemble import DeckInput, DeckSlide
from .config import FRONTEND_DIST, settings
from .events import bus
from .export_pptx import export_pptx
from .llm import client as llm
from .pipeline import deckops, deckreview, reference, runner
from . import docs, facts, images, usage
from .downloads import disposition
from .library import common as library_common
from .library import export as library_export
from .library import graph as library_graph
from .library import ingest as library_ingest
from .library import obsidian as library_obsidian
from .library import reuse as library_reuse
from .library import search as library_search
from .library import tagging as library_tagging
from .qa.charts import chart_findings
from .qa.render_check import check_spec, export_pdf, ledger_findings
from .spec import SlideSpec
from .store import db
from .store.db import Feedback, Project, ProjectDoc, Slide, Version

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
MAX_UPLOAD = 300 * 1024 * 1024
MAX_EDIT_OPS = 200  # one editing session; a longer list is a client bug, not a user
HEALTH_TTL_S = 20.0  # every open tab polls /api/health; one live GB300 probe per window is plenty


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.engine()
    for project in db.projects():
        if project.status=='generating' and project.stage_note in ('Queued for booth fast path','Writing three concise slides with the local author'):
            project.status='error';project.error='Application restarted during authoring. Please submit your brief again.';db.save(project)
    runner.recover_interrupted()
    library_ingest.recover_interrupted()
    library_tagging.recover_interrupted()
    log.info("LLM %s @ %s (mock=%s)", settings().llm_model, settings().llm_base_url, settings().llm_mock)
    yield


app = FastAPI(title="HP Deck Builder", lifespan=lifespan)
from .booth import router as booth_router
app.include_router(booth_router)
from pathlib import Path as _ShowcasePath
app.mount('/showcase-assets', StaticFiles(directory=_ShowcasePath(__file__).resolve().parents[5]/'showcase_app/assets'), name='showcase-assets')

# The slide library (app/library/): one router per module, all under /api/library.
for _r in (library_ingest.router, library_search.router, library_tagging.router, library_export.router,
           library_reuse.router, library_graph.router, library_obsidian.router):
    app.include_router(_r, prefix="/api/library", tags=["library"])
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ serializers
def iso(dt) -> str:
    """SQLite drops tzinfo; timestamps are stored in UTC."""
    return dt.isoformat() + ("Z" if dt.tzinfo is None else "")


def word_count(content: dict) -> int:
    """Words in the body copy of a parsed slide (`SlideContent.model_dump()` shape)."""
    return sum(len(p.get("text", "").split()) for t in content.get("texts", []) for p in t.get("paragraphs", []))


def version_out(v: Version, slim: bool = False) -> dict:
    """One version, as the review board sees it.

    `qa` is read through `db.QaReport` rather than as a raw dict, so a producer-side change of shape
    is reported here with the version id instead of arriving in the browser as `undefined`. The wire
    shape is a deliberate projection of the model, not a dump of it: the stored payload also carries
    working data (`shots`, per-iteration internals) that no client has any use for.

    `slim` drops the keys that cannot change without the version also changing status — the spec's
    title and notes, the token ledger, and the QA detail behind the quality dialog. Every key it
    emits is one the full payload emits too, so laying it over a cached full version is a plain
    object spread (`qa` included).
    """
    qa = db.QaReport.of(v.qa, version_id=v.id)
    out = {
        "id": v.id, "slide_id": v.slide_id, "lineage": v.lineage, "number": v.number, "parent_id": v.parent_id, "comment": v.comment,
        "origin": v.origin or "llm",  # versions written before the column exists read back NULL
        "status": v.status, "stage_note": v.stage_note, "score": v.score, "repairs": v.repairs, "error": v.error,
        "qa": {"passed": qa.passed, "vision": qa.vision, "critic_status": qa.critic_status or None,
               "critic_error": qa.critic_error, "critic_warning": qa.critic_warning,
               "critic_skipped_reason": qa.critic_skipped_reason,
               # `ab` is the pairwise A-vs-B verdict; `best_of` records the sampled drafts when best-of-n is on.
               "ab": qa.ab.model_dump() if qa.ab else None, "best_of": qa.best_of.model_dump() if qa.best_of else None},
        "created_at": iso(v.created_at), "updated_at": iso(v.updated_at),
    }
    if slim:  # `spec` and `llm` were never read from the database for this row — see db._versions_lite
        return out
    meta = (v.spec or {}).get("meta", {})
    out["qa"].update(findings=qa.findings, critic=qa.critic, iterations=qa.iterations, diff=qa.diff)
    return {**out, "title": meta.get("title", ""), "notes": meta.get("notes", []),
            "steps": qa.steps if qa.steps is not None else meta.get("steps"), "llm": v.llm}


THIN_WORDS = 25
_NEVER_THIN = {"title", "agenda", "section", "closing", "quote", "stat-hook"}


def is_thin(s: Slide, content: dict) -> bool:
    """A slide carrying too little to earn its place: a heading and a line or two, no table, chart or picture.
    Shown in the plan view next to the planner's merge suggestions — sparse decks were tester feedback, and a
    thin slide is usually half of a slide that belongs elsewhere. Slides that are meant to be sparse aren't."""
    if (s.plan or {}).get("pattern") in _NEVER_THIN or (s.plan or {}).get("role") in _NEVER_THIN:
        return False
    if content.get("tables") or content.get("charts") or any(not i.get("decorative") for i in content.get("images", [])):
        return False
    return word_count(content) < THIN_WORDS


def slide_label(s: Slide) -> str:
    """What to call this slide on screen: its source number, suffixed when that slide was split, "8+17" when
    the user merged slides, and "new" for one they added to a converted deck (it has no source number)."""
    plan = s.plan or {}
    if plan.get(runner.MERGED_LABELS_KEY):
        return "+".join(plan[runner.MERGED_LABELS_KEY])
    if plan.get(runner.ADDED_KEY):
        return "new"
    total = plan.get(runner.PART_KEY, [0, 1])[1]
    return f"{s.index}{'abc'[s.part]}" if total > 1 and s.part < 3 else str(s.index)


def slide_out(s: Slide, versions: list[Version], slim: bool = False) -> dict:
    """One slide. `slim` drops the parsed source copy — see `project_out`."""
    parsed = s.content or {}
    out = {
        "id": s.id, "index": s.index, "position": s.position, "included": s.included, "status": s.status, "error": s.error,
        "approved_version_id": s.approved_version_id, "plan": s.plan, "source_title": parsed.get("title", ""),
        # `part` and `parts` describe a source slide the planner split: both halves share `index` (and so the
        # same source render), and `label` is what the user should see — "4" normally, "4a"/"4b" when split.
        "part": s.part, "parts": (s.plan or {}).get(runner.PART_KEY, [0, 1])[1],
        "label": slide_label(s),
        "versions": [version_out(v, slim=slim) for v in versions],
    }
    if slim:
        return out
    c = {**parsed, **(s.content_edit or {})}  # counts and flags follow the copy the model will actually see
    merged = runner.merged_content(s).for_prompt()
    return {
        **out,
        # `content` is authoritative for generation; `content_original` is what the PowerPoint said.
        "content": merged, "content_edited": bool(s.content_edit),
        "content_original": runner.parsed_content(s).for_prompt() if s.content_edit else merged,
        "word_count": word_count(c),
        "has_chart": bool(c.get("charts")), "has_table": bool(c.get("tables")), "image_count": len([i for i in c.get("images", []) if not i.get("decorative")]),
        "notes": c.get("notes", ""), "warnings": c.get("warnings", []),
        "thin": is_thin(s, c),
        # The fact ledger this slide is held to, with each fact's tier. The review view adds what became of
        # them from `Version.qa`; here it is what the slide is *required* to show.
        "facts": facts.dump(runner.slide_facts(s)), "facts_edited": s.facts_edit is not None,
    }


def project_out(p: Project, with_slides: bool = False, slim: bool = False) -> dict:
    """The project. `slim` keeps every field that moves during a run (statuses, stage notes, scores,
    counts, QA) and drops the ones that do not: the parsed PowerPoint copy on each slide, and the
    `spec`/`llm` JSON on each version (`db.versions_of_project(slim=True)` never reads them at all).

    The frontend polls this route on every SSE event it cannot apply to its cache, so the difference
    is paid dozens of times per generation. The client lays the slim payload over the full one it
    already has — the keys are a strict subset, which is what makes that merge safe.
    """
    every = db.slides_of(p.id)
    slides = [s for s in every if not runner.is_removed(s)]  # deleted or merged away: out of the deck
    out = {
        "id": p.id, "name": p.name, "filename": p.filename, "source": p.source or "pptx",
        "status": p.status, "stage_note": p.stage_note, "error": p.error,
        "deck_title": p.deck_title, "brief": p.brief, "renderer": p.renderer, "warnings": p.warnings,
        "created_at": iso(p.created_at), "updated_at": iso(p.updated_at), "busy": runner.jobs.busy(p.id),
        "counts": {
            "slides": len(slides), "included": sum(1 for s in slides if s.included),
            "approved": sum(1 for s in slides if s.included and s.status == "approved"),
            "review": sum(1 for s in slides if s.included and s.status == "review"),
            "generating": sum(1 for s in slides if s.status in ("generating", "revising")),
            "error": sum(1 for s in slides if s.status == "error"),
            "removed": len(every) - len(slides),
            "appendix": sum(1 for s in slides if s.included and (s.plan or {}).get(runner.APPENDIX_KEY)),
        },
        "cover_slide_index": slides[0].index if slides else None,
    }
    if with_slides:
        versions = db.versions_of_project(p.id, slim=slim)
        by_slide: dict[str, list[Version]] = {}
        for v in versions:
            by_slide.setdefault(v.slide_id, []).append(v)
        out["slim"] = slim
        # Removed slides are sent too (their `plan.removed` says so): the plan view lists them apart, so a
        # delete or a merge can be undone from where it was done.
        out["slides"] = [slide_out(s, by_slide.get(s.id, []), slim=slim) for s in every]
    return out


def _project(pid: str) -> Project:
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


def _slide(sid: str) -> Slide:
    s = db.get(Slide, sid)
    if s is None:
        raise HTTPException(404, "Slide not found")
    return s


def _version(vid: str) -> Version:
    v = db.get(Version, vid)
    if v is None:
        raise HTTPException(404, "Version not found")
    return v


# ------------------------------------------------------------------ system
_health: dict = {"at": 0.0, "value": None}
_health_lock = asyncio.Lock()


@app.get("/api/health")
async def health():
    # The frontend polls this every 30s per open tab and llm.health() is a live call to the GB300 over
    # Tailscale. Cache it, and let concurrent pollers share the one in-flight probe.
    #
    # `llm` stays the authoring server so the shape never regressed for anything already reading it; `review`
    # is the critic/judge server beside it. When the two roles share one base URL, `split` is false and the
    # frontend reports one connection rather than implying two processes that do not exist.
    async with _health_lock:
        if _health["value"] is None or (time.monotonic() - _health["at"]) > HEALTH_TTL_S:
            _health.update(value=await llm.health_all(), at=time.monotonic())
        h = _health["value"]
    return {"llm": h["author"], "review": h["review"], "split": settings().split_endpoints,
            "renderer": settings().renderer, "qa_max_repairs": settings().qa_max_repairs}


@app.get("/api/usage")
async def usage_summary(days: int | None = None):
    """The usage dashboard: tokens per model/stage/deck and what the same work would have cost in the cloud."""
    s = settings()
    out = await asyncio.to_thread(usage.summary, days if days and days > 0 else None)
    out["mock"] = s.llm_mock
    out["endpoints"] = {str(r): {"model": ep.model, "base_url": ep.base_url} for r, ep in s.endpoints.items()}
    return out


@app.post("/api/admin/reload-skill")
async def reload_skill():
    skillpack.clear()
    assembler.clear_caches()
    return {"ok": True, "system_prompt_chars": len(skillpack.system_prompt())}


# ------------------------------------------------------------------ projects
@app.get("/api/projects")
async def list_projects():
    return [project_out(p) for p in db.projects()]


def _purge_project(pid: str) -> None:
    """Rows and bytes go together: deleting only the row stranded the partial upload on disk for ever."""
    db.delete_project(pid)
    shutil.rmtree(settings().projects_dir / pid, ignore_errors=True)


class BlankProject(BaseModel):
    name: str = "Untitled deck"
    slides: int = 1


@app.post("/api/projects/blank")
async def create_blank_project(body: BlankProject):
    """A deck written here rather than converted. Same pipeline from planning onwards.

    It starts `ready` with blank slides: there is nothing to ingest, and nothing to wait for before the
    user can begin typing.
    """
    p = db.save(Project(name=(body.name or "Untitled deck").strip()[:120], filename="", source="composed",
                        status="ready", deck_title=(body.name or "").strip()[:120]))
    for _ in range(max(1, min(body.slides, compose.MAX_SLIDES))):
        runner.add_slide(p.id)
    return project_out(db.get(Project, p.id), with_slides=True)


class OutlineBody(BaseModel):
    """What to draft from. `about` is the user's own description; `source_text` is material pasted in."""

    about: str = ""
    source_text: str = ""
    slides: int = compose.DEFAULT_SLIDES
    # Only when drafting from reference documents: the sections to draw on (`<doc id>:<n>`; None = all of them).
    sections: list[str] | None = None
    angle: str = ""   # the kind of deck wanted: "Executive pitch", "Technical deep-dive", …


@app.post("/api/projects/{pid}/outline")
async def draft_outline(pid: str, body: OutlineBody):
    p = _project(pid)
    if (p.source or "pptx") != "composed":
        raise HTTPException(400, "Only a deck written here can be drafted; this one came from a PowerPoint.")
    source = body.source_text
    if not source.strip():
        # No pasted material: draft from the reference documents the user added, when there are any — whole
        # while they fit, summarised section by section when they do not (pipeline/reference.compose_source).
        only = set(body.sections) if body.sections is not None else None
        source = await asyncio.to_thread(reference.compose_source, pid, compose.MAX_SOURCE_CHARS, only)
    angle = {"angle": body.angle.strip()[:120]} if body.angle.strip() else {}
    runner.jobs.spawn(pid, runner.draft_outline(pid, body.slides, body.about, source, **angle))
    return {"ok": True}


class NewSlide(BaseModel):
    after: int | None = None   # 0-based position to insert after; None appends


@app.post("/api/projects/{pid}/slides")
async def add_slide(pid: str, body: NewSlide):
    _project(pid)
    s = runner.add_slide(pid, body.after)
    runner.emit(pid, "slides")
    return slide_out(s, [])


def _not_in_flight(slides: list[Slide]) -> None:
    """Refuse to delete or merge a slide the model is writing right now: the job would land on a row that is
    gone, or design content that has moved. Only those slides are checked — planning a merged slide in the
    background must not lock the whole deck."""
    busy = [s for s in slides if s.status in ("generating", "revising")]
    if busy:
        raise HTTPException(409, f"Slide {slide_label(busy[0])} is being designed — wait for it, or stop the run.")


@app.delete("/api/slides/{sid}")
async def delete_slide(sid: str):
    """A converted slide leaves the deck and can be restored; a slide made here is really deleted.
    See app/pipeline/deckops.py."""
    s = _slide(sid)
    _not_in_flight([s])
    try:
        deckops.delete_slide(sid)
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    runner.emit(s.project_id, "slides")
    return {"ok": True}


class RestoreBody(BaseModel):
    after: int | None = None   # 0-based position among the live slides; None = the end


@app.post("/api/slides/{sid}/restore")
async def restore_slide(sid: str, body: RestoreBody):
    s = _slide(sid)
    try:
        out = deckops.restore_slide(sid, body.after)
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    runner.emit(s.project_id, "slides")
    return slide_out(out, db.versions_of_slide(sid))


class MergeBody(BaseModel):
    slide_ids: list[str]


@app.post("/api/projects/{pid}/merge")
async def merge_slides(pid: str, body: MergeBody):
    """Combine slides into one. The parts of one split slide merge back into it (undo split); anything else
    becomes a new slide, planned on its own, with the originals out of the deck until an unmerge."""
    _project(pid)
    _not_in_flight([x for x in (db.get(Slide, i) for i in body.slide_ids) if x is not None])
    try:
        s = deckops.merge_slides(pid, body.slide_ids)
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    if (s.plan or {}).get(runner.MERGED_FROM_KEY):
        runner.jobs.spawn(pid, deckops.plan_slides(pid, [s.id]))
    runner.emit(pid, "slides")
    return slide_out(s, db.versions_of_slide(s.id))


class InstructBody(BaseModel):
    instruction: str
    slide_ids: list[str] | None = None   # None = every designed slide in the deck


@app.post("/api/projects/{pid}/instruct")
async def instruct(pid: str, body: InstructBody):
    """One instruction ("less text everywhere") revised into every slide in scope, one slide at a time."""
    _project(pid)
    text = body.instruction.strip()[:1000]
    if not text:
        raise HTTPException(400, "Write the instruction first.")
    if runner.jobs.busy(pid):
        raise HTTPException(409, "The deck is busy — wait for the current run to finish, or stop it.")
    scope = deckreview.instruct_scope(pid, body.slide_ids)
    if not scope:
        raise HTTPException(400, "No designed slides to apply it to yet.")
    runner.jobs.spawn(pid, deckreview.instruct_deck(pid, text, body.slide_ids))
    return {"ok": True, "slides": len(scope)}


@app.post("/api/projects/{pid}/consistency")
async def consistency(pid: str):
    _project(pid)
    runner.jobs.spawn(pid, deckreview.review_consistency(pid))
    return {"ok": True}


@app.get("/api/projects/{pid}/readiness")
async def readiness(pid: str):
    _project(pid)
    return deckreview.readiness(pid)


class CondenseBody(BaseModel):
    target: int
    keep: list[str] = []      # slide ids that must stay in the main deck
    guidance: str = ""        # the user's words: audience, time, what must survive


@app.post("/api/projects/{pid}/condense/propose")
async def condense_propose(pid: str, body: CondenseBody):
    """Ask for a shorter version of the deck. Nothing changes yet: the proposal lands in
    `brief.condense_proposal` for the user to review, then `apply`."""
    _project(pid)
    if body.target < 1:
        raise HTTPException(400, "Aim for at least one slide.")
    runner.jobs.spawn(pid, deckops.propose_condense(pid, body.target, body.keep, body.guidance[:2000]))
    return {"ok": True}


class ApplyCondense(BaseModel):
    main: list[dict]
    appendix: list[str] = []


@app.post("/api/projects/{pid}/condense/apply")
async def condense_apply(pid: str, body: ApplyCondense):
    """Apply the (possibly user-adjusted) proposal. Undoable with `condense/undo`."""
    p = _project(pid)
    _not_in_flight(deckops._live(pid))
    main = [{"ids": [str(i) for i in m.get("ids", [])], "headline": str(m.get("headline", ""))[:80]}
            for m in body.main if m.get("ids")]
    try:
        created = deckops.apply_condense(pid, {"main": main, "appendix": body.appendix})
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    guidance = ((p.brief or {}).get(deckops.PROPOSAL_KEY) or {}).get("guidance", "")
    if created:
        note = "The deck is being condensed" + (f" — the user's brief: {guidance}" if guidance else "") + \
               ". Make this one tight slide with a single message; detail goes to the speaker notes."
        runner.jobs.spawn(pid, deckops.plan_slides(pid, created, extra_note=note))
    runner.emit(pid, "slides")
    return {"ok": True, "created": created}


@app.post("/api/projects/{pid}/condense/undo")
async def condense_undo(pid: str):
    _project(pid)
    _not_in_flight(deckops._live(pid))
    try:
        deckops.undo_condense(pid)
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    runner.emit(pid, "slides")
    return {"ok": True}


@app.delete("/api/projects/{pid}/condense/proposal")
async def condense_dismiss(pid: str):
    p = _project(pid)
    runner.set_project(pid, brief={k: v for k, v in (p.brief or {}).items() if k != deckops.PROPOSAL_KEY})
    runner.emit(pid, "slides")
    return {"ok": True}


@app.post("/api/slides/{sid}/unmerge")
async def unmerge_slide(sid: str):
    s = _slide(sid)
    _not_in_flight([s])
    try:
        back = deckops.unmerge(sid)
    except deckops.DeckOpError as e:
        raise HTTPException(400, str(e)) from e
    runner.emit(s.project_id, "slides")
    return {"ok": True, "restored": [b.id for b in back]}


class MoveSlide(BaseModel):
    to: int   # 0-based target position


@app.post("/api/slides/{sid}/move")
async def move_slide(sid: str, body: MoveSlide):
    s = _slide(sid)
    runner.move_slide(sid, body.to)
    runner.emit(s.project_id, "slides")
    return {"ok": True}


class WriteSlide(BaseModel):
    """Typing into a composed slide. Unset fields are left alone."""

    title: str | None = None
    body: str | None = None
    notes: str | None = None


@app.post("/api/slides/{sid}/write")
async def write_slide(sid: str, body: WriteSlide):
    s = _slide(sid)
    p = _project(s.project_id)
    # A slide the user added to a converted deck has no PowerPoint behind it: its typing is its source.
    if (p.source or "pptx") != "composed" and not (s.plan or {}).get(runner.ADDED_KEY):
        raise HTTPException(400, "Use the content editor: a converted deck keeps its PowerPoint copy recoverable.")
    out = runner.write_slide(sid, title=body.title, body=body.body, notes=body.notes)
    runner.emit(s.project_id, "slides")
    return slide_out(out, db.versions_of_slide(sid))


@app.post("/api/projects")
async def create_project(file: UploadFile = File(...), context: list[UploadFile] | None = File(None)):
    """A PowerPoint to convert, plus any reference documents to read before the first plan (`context`), so the
    first plan already uses them — no re-plan needed. A document that can't be read is skipped and reported in
    the project's warnings; it never stops the deck."""
    name = file.filename or "deck.pptx"
    if not name.lower().endswith(".pptx"):
        raise HTTPException(400, "Please upload a .pptx file (save .ppt files as .pptx first).")
    p = db.save(Project(name=re.sub(r"\.pptx$", "", name, flags=re.I), filename=name))
    dest = db.project_dir(p.id) / "source.pptx"
    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "File too large (max 300 MB)")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "That file is empty.")
    except BaseException:  # oversize, an empty file, or a dropped connection: keep no half-uploaded project
        _purge_project(p.id)
        raise
    skipped = []
    for f in context or []:
        try:
            await _store_doc(p.id, f)   # digested by ingest, before it plans
        except HTTPException as e:
            skipped.append(f"Reference document {f.filename}: {e.detail}")
    if skipped:
        runner.set_project(p.id, warnings=skipped)
    runner.jobs.spawn(p.id, runner.ingest(p.id))
    return project_out(db.get(Project, p.id))


@app.get("/api/projects/{pid}")
async def get_project(pid: str, slim: bool = False):
    """`?slim=true` is the polling variant — same shape, minus the parts that don't move. See
    `project_out`. The first load of a project must be a full one; the client only ever lays a slim
    payload over a full one it already holds."""
    return project_out(_project(pid), with_slides=True, slim=slim)


class ProjectPatch(BaseModel):
    name: str | None = None
    deck_title: str | None = None
    brief: dict | None = None


@app.patch("/api/projects/{pid}")
async def patch_project(pid: str, body: ProjectPatch):
    p = _project(pid)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "brief" in fields:
        fields["brief"] = {**(p.brief or {}), **fields["brief"]}
    runner.set_project(pid, **fields)
    return project_out(db.get(Project, pid))


@app.delete("/api/projects/{pid}")
async def delete_project(pid: str):
    _project(pid)
    await runner.jobs.cancel(pid)
    _purge_project(pid)
    return {"ok": True}


@app.post("/api/projects/{pid}/replan")
async def replan(pid: str):
    _project(pid)
    if runner.jobs.busy(pid):
        raise HTTPException(409, "Project is busy")
    runner.jobs.spawn(pid, runner.plan(pid))
    return {"ok": True}


class GenerateBody(BaseModel):
    slide_ids: list[str] | None = None


@app.post("/api/projects/{pid}/generate")
async def generate(pid: str, body: GenerateBody):
    p = _project(pid)
    if p.status in ("ingesting", "planning"):
        raise HTTPException(409, "Still importing — wait for the plan")
    # A slide the user added (or merged) since the plan has no pattern or ideas yet: plan just those first.
    unplanned = [s.id for s in db.slides_of(pid) if s.included and not runner.is_removed(s)
                 and not (s.plan or {}).get("pattern") and (body.slide_ids is None or s.id in body.slide_ids)]
    runner.jobs.spawn(pid, _plan_then_generate(pid, unplanned, body.slide_ids))
    return {"ok": True}


async def _plan_then_generate(pid: str, unplanned: list[str], slide_ids: list[str] | None) -> None:
    if unplanned and (db.get(Project, pid).source or "pptx") != "composed":
        await deckops.plan_slides(pid, unplanned)
    await runner.generate_project(pid, slide_ids)


@app.post("/api/projects/{pid}/cancel")
async def cancel(pid: str):
    _project(pid)
    from .booth import cancel_project
    booth_cancelled = await cancel_project(pid)
    n = await runner.jobs.cancel(pid)
    if booth_cancelled:return {'cancelled':n+1}
    for s in db.slides_of(pid):
        if s.status in ("generating", "revising"):
            runner.set_slide(s.id, status="pending" if not db.versions_of_slide(s.id) else "review")
    runner._refresh_project_status(pid)
    p = db.get(Project, pid)  # may have been deleted while we awaited the cancel
    if p is not None and p.status == "generating":
        runner.set_project(pid, status="ready", stage_note="")
    return {"cancelled": n}


class OrderBody(BaseModel):
    slide_ids: list[str]


@app.put("/api/projects/{pid}/order")
async def reorder(pid: str, body: OrderBody):
    _project(pid)
    for pos, sid in enumerate(body.slide_ids, start=1):
        s = db.get(Slide, sid)
        if s and s.project_id == pid:
            db.update(Slide, sid, position=pos)
    runner.emit(pid, "slides")
    return {"ok": True}


# ------------------------------------------------------------------ slides
class ContentEdit(BaseModel):
    """The plan view's editable view of the slide: one string per body block, one line per paragraph."""

    title: str | None = None
    blocks: list[str] | None = None


class FactPatch(BaseModel):
    """One correction to the fact ledger. `drop` strikes a fact out; `tier` re-tiers it."""

    id: str
    tier: Literal["key", "supporting"] | None = None
    drop: bool = False


class SlidePatch(BaseModel):
    included: bool | None = None
    plan: dict | None = None
    content: ContentEdit | None = None
    reset_content: bool = False  # drop the override and go back to the PowerPoint parse
    facts: list[FactPatch] | None = None
    reset_facts: bool = False   # drop the corrections and go back to what was extracted


@app.patch("/api/slides/{sid}")
async def patch_slide(sid: str, body: SlidePatch):
    s = _slide(sid)
    fields = {}
    if body.included is not None:
        fields["included"] = body.included
    if body.plan is not None:
        fields["plan"] = {**(s.plan or {}), **body.plan}
    if body.reset_content:
        fields["content_edit"] = None
    elif body.content is not None:
        fields["content_edit"] = runner.content_edit(s, title=body.content.title, blocks=body.content.blocks)
    if body.reset_facts:
        fields["facts_edit"] = None
    elif body.facts is not None:
        # Stored whole rather than as an overlay: striking a fact out is a real edit — a source slide can
        # carry a figure that genuinely does not belong on the designed one — and an overlay cannot express
        # a deletion. Corrections survive a re-plan; see runner.plan's `facts_edit is None` guard.
        patches = {f.id: f for f in body.facts}
        kept = []
        for fact in runner.slide_facts(s):
            patch = patches.get(fact.id)
            if patch and patch.drop:
                continue
            if patch and patch.tier:
                fact = fact.model_copy(update={"tier": patch.tier})
            kept.append(fact)
        fields["facts_edit"] = facts.dump(kept)
    elif body.content is not None or body.reset_content:
        # The copy decides what the slide claims, so a ledger extracted from the old copy would hold the
        # design to figures the user has just removed.
        if s.facts_edit is None:
            after = db.get(Slide, sid)
            fields["facts"] = facts.dump(runner.refresh_facts(after.model_copy(update=fields)))
    runner.set_slide(sid, **fields)
    runner.emit(s.project_id, "slides")
    return {"ok": True}


class RedesignBody(BaseModel):
    reasons: list[str] = []      # keys of runner.REDESIGN_REASONS (anything else is passed through as text)
    note: str = ""               # the user's own words
    pattern: str | None = None   # "wrong layout": try this one instead


@app.post("/api/slides/{sid}/regenerate")
async def regenerate(sid: str, body: RedesignBody | None = None):
    """Redesign both variants. With a reason, the reason and what the rejected designs were built from go into
    the prompt, so the redesign does not repeat them — and the reason is kept (`db.Feedback`)."""
    s = _slide(sid)
    body = body or RedesignBody()
    if body.pattern:
        runner.set_slide(sid, plan={**(s.plan or {}), "pattern": body.pattern[:40]})
    note, label = "", ""
    if body.reasons or body.note.strip() or body.pattern:
        reasons = [r[:80] for r in body.reasons][:8]
        if body.pattern and "wrong-layout" not in reasons:
            reasons.append("wrong-layout")
        note, label, rejected = runner.redesign_note(sid, reasons, body.note[:600])
        if body.pattern:
            note += f"\n\nUse the `{body.pattern}` pattern this time."
        db.save(Feedback(project_id=s.project_id, slide_id=sid, pattern=(s.plan or {}).get("pattern", ""),
                         reasons=reasons, note=body.note[:600], rejected=rejected))
    runner.jobs.spawn(s.project_id, runner.generate_slide(sid, redesign=note, comment=label))
    return {"ok": True}


class ChooseBody(BaseModel):
    version_id: str


@app.post("/api/slides/{sid}/choose")
async def choose(sid: str, body: ChooseBody):
    s = _slide(sid)
    v = _version(body.version_id)
    if v.slide_id != s.id or v.status != "ready":
        raise HTTPException(400, "That version is not ready for this slide")
    runner.choose(sid, v.id)
    return {"ok": True}


@app.post("/api/slides/{sid}/unapprove")
async def unapprove(sid: str):
    _slide(sid)
    runner.unapprove(sid)
    return {"ok": True}


class ReviseBody(BaseModel):
    base_version_id: str
    comment: str
    asset_keys: list[str] = []   # images to bring in: attached to the slide, and named in the comment


@app.post("/api/slides/{sid}/revise")
async def revise(sid: str, body: ReviseBody):
    s = _slide(sid)
    v = _version(body.base_version_id)
    if v.slide_id != sid or not v.spec:
        raise HTTPException(400, "Choose a ready version to revise from")
    if not body.comment.strip() and not body.asset_keys:
        raise HTTPException(400, "Comment is empty")
    comment = body.comment.strip()
    if body.asset_keys:
        have = db.asset_files(s.project_id)
        missing = [k for k in body.asset_keys if k not in have]
        if missing:
            raise HTTPException(400, f"No such image in this deck: {', '.join(missing)}")
        for k in body.asset_keys:
            runner.attach_image(sid, k)
        keys = ", ".join(f"asset:{k}" for k in body.asset_keys)
        comment = (comment + "\n" if comment else "") + f"Use the image(s) the user added: {keys}."
    runner.jobs.spawn(s.project_id, runner.revise(sid, v.id, comment))
    return {"ok": True}


@app.get("/api/slides/{sid}/source.png")
async def source_png(sid: str, thumb: bool = False):
    s = _slide(sid)
    d = db.project_dir(s.project_id) / "renders"
    f = d / (f"{s.index:03d}_thumb.jpg" if thumb else f"{s.index:03d}.png")
    if not f.exists():
        raise HTTPException(404, "No render")
    return FileResponse(f, headers={"Cache-Control": "max-age=3600"})


@app.get("/api/projects/{pid}/cover.jpg")
async def cover(pid: str):
    slides = db.slides_of(pid)
    if slides:
        f = db.project_dir(pid) / "renders" / f"{slides[0].index:03d}_thumb.jpg"
        if f.exists():
            return FileResponse(f)
    raise HTTPException(404)


# ------------------------------------------------------------------ versions / previews
@app.get("/api/versions/{vid}/preview")
async def version_preview(vid: str, embed: bool = True):
    v = _version(vid)
    if not v.spec:
        return HTMLResponse("<body style='font:14px system-ui;color:#888;display:grid;place-items:center;height:100vh'>Not ready</body>")
    deck = DeckInput(title="Preview", slides=[DeckSlide(id=v.slide_id, spec=SlideSpec.model_validate(v.spec))], storage_key=f"preview-{v.slide_id}",
                     assets=db.asset_files(v.project_id))
    html = assembler.assemble(deck, embed=embed, asset_base=f"/api/projects/{v.project_id}/assets/")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/versions/{vid}/shot/{name}")
async def version_shot(vid: str, name: str):
    v = _version(vid)
    if name not in ("shot_0.png", "shot_final.png"):
        raise HTTPException(404)
    f = db.version_dir(v.project_id, v.id) / name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/versions/{vid}/spec")
async def version_spec(vid: str):
    return _version(vid).spec


# ------------------------------------------------------------------ direct edits
# The editor changes a slide without the model: app/edit.py applies structured ops to the stored
# HTML. One editing session becomes one new Version in the same lineage, marked origin="edit", with
# the pre-edit version left untouched as its parent — so the history stays a straight line and a
# revert is just "show the parent again".
def _editable(vid: str) -> tuple[Version, SlideSpec]:
    v = _version(vid)
    if not v.spec:
        raise HTTPException(400, "This version has no slide to edit yet")
    return v, SlideSpec.model_validate(v.spec)


def _edit_summary(ops: list) -> str:
    names = {"set_text": "text change", "delete": "deletion", "reorder": "move", "set_style": "style change",
             "set_src": "image swap"}
    counts: dict[str, int] = {}
    for o in ops:
        counts[o.op] = counts.get(o.op, 0) + 1
    parts = [f"{n} {names[k]}{'s' if n > 1 else ''}" for k, n in counts.items() if k in names]
    return "Edited by hand: " + ", ".join(parts)


async def qa_recheck(vid: str, reasons: list[str]) -> None:
    """Re-verify a hand-edited slide: render it, re-run the DOM checks, and ask the critic when vision
    is available. It never repairs — the markup is the user's now, so QA reports instead of rewriting.
    Runs as a background job so the edit response is immediate."""
    v = db.get(Version, vid)
    slide = db.get(Slide, v.slide_id) if v else None
    if v is None or slide is None or not v.spec:
        return
    try:
        spec = SlideSpec.model_validate(v.spec)
        ctx = runner.Ctx(slide)
        out = db.version_dir(v.project_id, v.id)
        report = await check_spec(spec, slide.id, ctx.assets, out, title=ctx.brief.get("deck_title", "QA"))
        findings = [f.model_dump() for f in report.findings]
        notes_text = " ".join(spec.meta.notes)
        lg = facts.ledger(ctx.facts, report.text, notes_text)
        findings += [f.model_dump() for f in ledger_findings(ctx.facts, report.text, notes_text)]
        findings += [f.model_dump() for f in chart_findings(ctx.content.get("charts") or [], getattr(report, "charts", []),
                                                             getattr(report, "unverified_charts", 0), ctx.plan.get("pattern", ""))]
        vision = await llm.vision_enabled()
        critic, status, note = None, runner.CRITIC_SKIPPED, "vision disabled"
        if any(f["code"] in ("render", "no-slide") for f in findings):
            note = "slide did not render"
        elif vision or settings().llm_mock:
            critic, status, note, _ = await runner._critic(ctx, v.lineage, findings, [out / n for n in report.shots], {}, ledger=lg)
        passed = not any(f["severity"] == "error" for f in findings) and runner._critic_passes(critic, status)
        # A hand edit can break fidelity as easily as a generation can — retyping a number is one keystroke.
        fatal = [f["message"] for f in findings if f.get("fatal")]
        # Merge, never rebuild: `ab` (the pairwise verdict) and `best_of` are recorded by the generation
        # pipeline and say nothing about this edit, so rebuilding the dict would silently discard them.
        qa = {**(db.get(Version, vid).qa or {}),
              "passed": passed, "fatal": fatal, "findings": findings, "critic": critic, "steps": report.steps, "shots": report.shots,
              "iterations": [], "vision": vision, "critic_status": status,
              "critic_error": note if status == runner.CRITIC_FAILED else "",
              "critic_warning": note if status == runner.CRITIC_OK else "",
              "critic_skipped_reason": note if status == runner.CRITIC_SKIPPED else "",
              "edit": {"parent": v.parent_id, "reasons": reasons, "checked": True}}
        runner.set_version(vid, qa=qa, score=runner._score(findings, critic, status), status="ready", stage_note="")
    except asyncio.CancelledError:
        runner.set_version(vid, stage_note="")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("edit QA re-check failed")
        qa = {**(db.get(Version, vid).qa or {}), "edit": {"parent": v.parent_id, "reasons": reasons, "checked": False, "error": str(e)[:300]}}
        runner.set_version(vid, qa=qa, status="ready", stage_note="")


@app.get("/api/versions/{vid}/outline")
async def version_outline(vid: str):
    """Every element the editor may address, in document order.

    The stamped HTML is written back, because a `data-eid` is only stable while it lives in the
    stored spec: walking the same document twice happens to produce the same ids, but the first
    structural edit would break that. The write is deliberately quiet (no `updated_at`, no event) —
    nothing about the slide looks different, and bumping the timestamp would reload the preview
    iframe underneath the session that just asked for the outline.
    """
    v, spec = _editable(vid)
    stamped = editor.ensure_ids(spec)
    if stamped.html != spec.html:
        db.update(Version, vid, touch=False, spec=stamped.model_dump())
    return {"version_id": vid, "elements": [e.model_dump() for e in editor.outline(stamped)]}


@app.post("/api/versions/{vid}/edit")
async def version_edit(vid: str, body: editor.EditRequest):
    v, spec = _editable(vid)
    if not body.ops:
        raise HTTPException(400, "No edits to apply")
    if len(body.ops) > MAX_EDIT_OPS:
        raise HTTPException(400, f"Too many edits in one save (max {MAX_EDIT_OPS})")
    result = editor.apply_ops(spec, body.ops, assets=db.asset_files(v.project_id).keys())
    if not result.ok:
        # 400 carries the failing op so the UI can say which change was refused and why.
        failed = body.ops[result.failed_index] if result.failed_index is not None else None
        raise HTTPException(400, detail={"message": result.error, "error_code": result.error_code,
                                         "failed_index": result.failed_index,
                                         "op": failed.op if failed else "", "eid": failed.eid if failed else ""})
    warnings = [n.model_dump() for n in result.warnings]
    if not result.changed:
        return {"ok": True, "changed": False, "version": version_out(v), "warnings": warnings,
                "qa_recommended": False, "qa_reasons": []}

    slide = _slide(v.slide_id)
    same_lineage = [x for x in db.versions_of_slide(v.slide_id) if x.lineage == v.lineage]
    qa = {**(v.qa or {}), "edit": {"parent": v.id, "reasons": result.qa_reasons, "checked": False}}
    nv = db.save(Version(
        slide_id=v.slide_id, project_id=v.project_id, lineage=v.lineage, number=len(same_lineage) + 1,
        parent_id=v.id, origin="edit", comment=_edit_summary(body.ops), status="ready",
        spec=result.spec.model_dump(), qa=qa, score=v.score, repairs=v.repairs, llm=v.llm or {},
    ))
    # The parent's screenshots are the best picture of the slide until QA takes new ones (and for a
    # cosmetic edit they stay the only ones), so the rail thumbnail doesn't go blank on a save.
    src = db.version_dir(v.project_id, v.id)
    dst = db.version_dir(v.project_id, nv.id)
    for name in ("shot_0.png", "shot_final.png"):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    if slide.approved_version_id == v.id:
        # The user edited what is in the deck, so the deck follows the edit. `source="edit"` keeps this
        # out of the A/B calibration corpus: it is a consequence of a save, not a fresh human comparison.
        runner.choose(slide.id, nv.id, source="edit")
    if result.qa_recommended:
        runner.set_version(nv.id, stage_note="Re-checking the layout after your edits")
        runner.jobs.spawn(nv.project_id, qa_recheck(nv.id, result.qa_reasons))
    runner.emit(v.project_id, "slides")
    return {"ok": True, "changed": True, "version": version_out(db.get(Version, nv.id)), "warnings": warnings,
            "qa_recommended": result.qa_recommended, "qa_reasons": result.qa_reasons}


# ------------------------------------------------------------------ reference documents
def doc_out(d: ProjectDoc) -> dict:
    pdir = db.project_dir(d.project_id)
    return {"id": d.id, "name": d.name, "pages": d.pages, "chars": d.chars, "truncated": d.truncated,
            "status": d.status, "error": d.error, "digest": d.digest, "created_at": iso(d.created_at),
            "primary": bool(d.primary),
            # How it was read: digested in this many sections (0 = whole), and whether it is searchable by meaning.
            "sections": len(docs.load_section_digests(pdir, d.id)), "semantic": docs.vectors_path(pdir, d.id).exists(),
            "pictures": len(docs.picture_keys(pdir, d.id))}


@app.get("/api/projects/{pid}/docs")
async def list_docs(pid: str):
    _project(pid)
    return [doc_out(d) for d in db.docs_of(pid)]


@app.post("/api/projects/{pid}/docs")
async def upload_doc(pid: str, file: UploadFile = File(...)):
    """A PDF, Word or text file the planner and generator read as background (app/docs.py)."""
    _project(pid)
    d = await _store_doc(pid, file)
    runner.jobs.spawn(pid, reference.digest_doc(d.id))
    runner.emit(pid, "slides")
    return doc_out(d)


async def _store_doc(pid: str, file: UploadFile) -> ProjectDoc:
    """Read one uploaded reference document into the project. Raises HTTPException with a readable reason."""
    name = Path(file.filename or "document").name[:160]
    ext = Path(name).suffix.lower()
    if ext not in docs.DOC_TYPES:
        raise HTTPException(400, "Please add a PDF, Word (.docx), .txt or .md file.")
    work = Path(tempfile.mkdtemp(prefix="doc-", dir=db.project_dir(pid)))
    try:
        raw = work / f"upload{ext}"
        size = 0
        with raw.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > docs.MAX_BYTES:
                    raise HTTPException(413, f"File too large (max {docs.MAX_BYTES // (1024 * 1024)} MB)")
                f.write(chunk)
        try:
            text = await asyncio.to_thread(docs.extract, raw)
        except docs.DocRefused as e:
            raise HTTPException(400, str(e)) from e
        figures = await asyncio.to_thread(docs.pictures, raw)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    d = db.save(ProjectDoc(project_id=pid, name=name, pages=len(text.pages), chars=len(text.text), truncated=text.truncated))
    docs.save_text(db.project_dir(pid), d.id, text)
    # Its diagrams and charts become ordinary deck images, so a slide can use the figure and not only describe it.
    keys: list[str] = []
    for blob in figures:
        try:
            key, _, _ = await asyncio.to_thread(images.store_upload, blob, "figure.png", db.project_dir(pid) / "assets")
        except images.ImageRefused:
            continue
        if key not in keys:
            keys.append(key)
    if keys:
        docs.save_picture_keys(db.project_dir(pid), d.id, keys)
    return d


def _images_in_use(pid: str) -> set[str]:
    """Asset keys some slide of the deck shows."""
    used: set[str] = set()
    for s in db.slides_of(pid):
        for src in (s.content or {}, s.content_edit or {}):
            used |= {str(i.get("key")) for i in src.get("images") or [] if isinstance(i, dict)}
    return used


@app.delete("/api/docs/{did}")
async def delete_doc(did: str):
    d = db.get(ProjectDoc, did)
    if d is None:
        raise HTTPException(404, "Document not found")
    with db.session() as s:
        row = s.get(ProjectDoc, did)
        if row:
            s.delete(row)
            s.commit()
    pdir = db.project_dir(d.project_id)
    # Its pictures leave with it, except any a slide is using — and any another document also brought.
    others = {k for o in db.docs_of(d.project_id) for k in docs.picture_keys(pdir, o.id)}
    keep = _images_in_use(d.project_id) | others
    for key in docs.picture_keys(pdir, did):
        if key not in keep:
            for f in (pdir / "assets").glob(f"{key}.*"):
                f.unlink(missing_ok=True)
    docs.remove(pdir, did)
    # What it gave the deck goes with it: its figures, its citations, its section references.
    marked = await asyncio.to_thread(reference.forget_doc, d.project_id, did, d.name)
    runner.emit(d.project_id, "slides")
    return {"ok": True, "slides_affected": [s.id for s in marked]}


class DocPatch(BaseModel):
    primary: bool


@app.patch("/api/docs/{did}")
async def patch_doc(did: str, body: DocPatch):
    """Mark a document as the one to believe where documents disagree (or take the mark off)."""
    d = db.get(ProjectDoc, did)
    if d is None:
        raise HTTPException(404, "Document not found")
    d = db.update(ProjectDoc, did, primary=body.primary)
    runner.emit(d.project_id, "slides")
    return doc_out(d)


@app.get("/api/projects/{pid}/docs/sections")
async def doc_sections(pid: str):
    """The documents' sections, to choose from before drafting an outline (pipeline/reference.section_list)."""
    _project(pid)
    return await asyncio.to_thread(reference.section_list, pid)


@app.get("/api/projects/{pid}/docs/conflicts")
async def doc_conflicts(pid: str):
    """Quantities two documents give different values for (pipeline/reference.conflicts)."""
    _project(pid)
    return await asyncio.to_thread(reference.conflicts, pid)


@app.get("/api/projects/{pid}/assets")
async def list_assets(pid: str):
    """The deck's images, for the picker: the PowerPoint's own and the user's uploads."""
    _project(pid)
    pdir = db.project_dir(pid)
    from_doc = {k: d.name for d in db.docs_of(pid) for k in docs.picture_keys(pdir, d.id)}
    out = []
    for key, f in sorted(db.asset_files(pid).items()):
        out.append({"key": key, "upload": key.startswith("u_"), "bytes": f.stat().st_size,
                    "url": f"/api/projects/{pid}/assets/{key}",
                    "doc": from_doc.get(key, "")})  # the reference document this picture was taken from, if any
    return out


@app.post("/api/projects/{pid}/assets")
async def upload_asset(pid: str, file: UploadFile = File(...)):
    _project(pid)
    blob = await file.read(images.MAX_UPLOAD_BYTES + 1)
    try:
        key, w, h = await asyncio.to_thread(images.store_upload, blob, file.filename or "", db.project_dir(pid) / "assets")
    except images.ImageRefused as e:
        raise HTTPException(413 if len(blob) > images.MAX_UPLOAD_BYTES else 400, str(e)) from e
    return {"key": key, "width": w, "height": h, "upload": True, "url": f"/api/projects/{pid}/assets/{key}"}


class AttachImage(BaseModel):
    key: str
    alt: str = ""
    detach: bool = False


@app.post("/api/slides/{sid}/images")
async def attach_image(sid: str, body: AttachImage):
    """Put an image on a slide's content, so the next design or revision lays it out.

    A converted slide gets it in `content_edit` (the PowerPoint parse stays recoverable); a composed
    slide's content is its own source, so it goes straight in."""
    s = _slide(sid)
    if body.key not in db.asset_files(s.project_id):
        raise HTTPException(400, "No such image in this deck — upload it first.")
    runner.attach_image(sid, body.key, alt=body.alt, detach=body.detach)
    runner.emit(s.project_id, "slides")
    return {"ok": True}


@app.get("/api/projects/{pid}/assets/{key}")
async def asset(pid: str, key: str):
    files = db.asset_files(pid)
    if key in files:
        return FileResponse(files[key], headers={"Cache-Control": "max-age=86400"})
    if key == "hp":
        return FileResponse(assembler.default_logo())
    raise HTTPException(404)


# ------------------------------------------------------------------ export
def _safe_name(p: Project) -> str:
    """Filename stem from the deck title. May be non-ASCII — see downloads.disposition()."""
    return re.sub(r"[^\w\- ]+", "", p.deck_title or p.name).strip().replace(" ", "_")[:80] or "deck"


@app.get("/api/projects/{pid}/deck")
async def deck_preview(pid: str, fill: bool = True):
    _project(pid)
    html, _ = runner.build_deck(pid, fill_unapproved=fill, asset_base=f"/api/projects/{pid}/assets/", embed=True)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/projects/{pid}/export/stats")
async def export_stats(pid: str, fill: bool = True):
    _project(pid)
    html, stats = await asyncio.to_thread(runner.build_deck, pid, fill_unapproved=fill)
    return {**stats, "bytes": len(html.encode())}


@app.get("/api/projects/{pid}/export.html")
async def export_html(pid: str, fill: bool = True):
    p = _project(pid)
    html, stats = await asyncio.to_thread(runner.build_deck, pid, fill_unapproved=fill)
    out = db.project_dir(pid) / "export"
    out.mkdir(exist_ok=True)
    (out / "deck.html").write_text(html, encoding="utf-8")
    return Response(html, media_type="text/html", headers=disposition(_safe_name(p), "html"))


@app.get("/api/projects/{pid}/export.pdf")
async def export_pdf_route(pid: str, fill: bool = True):
    p = _project(pid)
    html, _ = await asyncio.to_thread(runner.build_deck, pid, fill_unapproved=fill)
    out = db.project_dir(pid) / "export"
    out.mkdir(exist_ok=True)
    # Fixed paths let two concurrent exports of the same project overwrite each other's print HTML and
    # PDF and hand both users a mixed file, so every request gets its own directory and drops it after.
    work = Path(tempfile.mkdtemp(prefix="pdf-", dir=out))
    hp = work / "deck_print.html"
    hp.write_text(html, encoding="utf-8")
    pdf = work / "deck.pdf"
    try:
        await export_pdf(hp, pdf)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return FileResponse(pdf, media_type="application/pdf", headers=disposition(_safe_name(p), "pdf"),
                        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@app.get("/api/projects/{pid}/export.pptx")
async def export_pptx_route(pid: str, fill: bool = True, editable: bool = False):
    """A PowerPoint file: one slide per rendered design, speaker notes attached. `editable=true` rebuilds each
    slide with real text boxes and pictures over a picture of the rest of the design (app/qa/extract_layout.py).

    The pictures are flat, so nothing here is interactive — the HTML deck stays the real artefact.
    What this buys is the review loop: a reviewer who will not open an HTML file can still read the
    deck, and the notes land in the notes pane rather than being lost.

    Same private working directory as the PDF route, and for the same reason: two exports of one
    project used to render into the same paths and hand both users a mixed file.
    """
    p = _project(pid)
    out = db.project_dir(pid) / "export"
    out.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pptx-", dir=out))
    try:
        deck, stats = await export_pptx(pid, work / "deck.pptx", fill_unapproved=fill, editable=editable)
        if not stats["slides"]:
            raise HTTPException(409, "No slides are ready yet — approve a design, or turn on “Fill unapproved slides”.")
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return FileResponse(deck, media_type=PPTX_MIME, headers=disposition(_safe_name(p), "pptx"),
                        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))


# ------------------------------------------------------------------ live events
@app.get("/api/projects/{pid}/events")
async def events(pid: str):
    q = bus.subscribe(pid)

    async def gen():
        try:
            yield {"event": "hello", "data": json.dumps({"project_id": pid})}
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": "update", "data": json.dumps(ev, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(pid, q)

    return EventSourceResponse(gen())


@app.get("/api/library/events")
async def library_events():
    """The library's live channel: deck ingest progress and per-slide tagging status (library/common.emit)."""
    return await events(library_common.CHANNEL)


# ------------------------------------------------------------------ frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        f = FRONTEND_DIST / path
        if path and f.is_file() and FRONTEND_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({"message": "Frontend not built. Run: cd frontend && npm install && npm run build"})
