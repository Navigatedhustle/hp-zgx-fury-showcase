"""The library inside the deck flows: stars on a project's slides, and slides inserted from the library.

Mapping a project slide to its library slide:
- **source** (a converted deck's PowerPoint): the project's own `origin="converted"` deck, else any ready deck of
  the very same file (`file_sha`) — an upload of it is reused, never duplicated. Matched by render `index`, which
  is the same number in both (visible slides only). Keyed by the part-0 project slide of each index.
- **generated** (approved designs): the project's current `origin="generated"` deck, matched by
  `content["origin_slide_id"]`. A copy is *stale* when its `origin_version_id` is no longer the approved version;
  starring a stale or missing slide saves a new deck that supersedes the old one (ingest._carry_forward keeps the
  user's favourites and locked tags).
A star on a deck that is still being copied is queued in `LibDeck.pending_favourites` and applied when it lands.

Inserting: a library slide becomes a slide of the project with its content, its pictures (re-keyed into the
project's assets) and its fact ledger (ids made unique), so grounding, QA and "a changed value is fatal" hold it
exactly like a converted slide. `plan.library_source` records where it came from; the generator cites its label
(runner.library_citation) and, for a PowerPoint-born slide, sees the library render as the original
(runner.library_render). Nothing here ever deletes a library row.
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import facts
from ..ingest.pptx_parse import SlideContent
from ..pipeline import runner
from ..store import db
from ..store.db import LibDeck, LibSlide, Project, Slide
from . import common, ingest, tagging

router = APIRouter()

MAX_INSERT = 30
_BUSY = ("ingesting", "planning", "composing")   # a whole-deck job is rewriting positions: as main.generate refuses
_sha_cache: dict[str, tuple[float, int, str]] = {}   # source.pptx path → (mtime, size, sha): links are polled


# ------------------------------------------------------------------ mapping
def _converted(p: Project) -> bool:
    return (p.source or "pptx") != "composed" and (db.project_dir(p.id) / "source.pptx").exists()


def _source_sha(pid: str) -> str:
    f = db.project_dir(pid) / "source.pptx"
    try:
        st = f.stat()
    except OSError:
        return ""
    hit = _sha_cache.get(str(f))
    if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2]
    sha = ingest._sha_file(f)
    _sha_cache[str(f)] = (st.st_mtime, st.st_size, sha)
    return sha


def _decks(*where) -> list[LibDeck]:
    """Current (not superseded) decks matching `where`, newest first."""
    with db.session() as s:
        return list(s.exec(db.select(LibDeck).where(LibDeck.superseded_by == "", *where)
                           .order_by(LibDeck.created_at.desc())))


def source_deck(pid: str) -> LibDeck | None:
    own = _decks(LibDeck.origin == "converted", LibDeck.origin_project_id == pid, LibDeck.status != "error")
    if own:
        return own[0]
    sha = _source_sha(pid)
    same = _decks(LibDeck.file_sha == sha, LibDeck.status == "ready", LibDeck.origin != "generated") if sha else []
    return same[0] if same else None


def generated_deck(pid: str) -> LibDeck | None:
    own = _decks(LibDeck.origin == "generated", LibDeck.origin_project_id == pid, LibDeck.status != "error")
    return own[0] if own else None


def _source_ids(pid: str) -> dict[int, str]:
    """index → the part-0 project slide of each source slide (what a source star is keyed by)."""
    return {s.index: s.id for s in ingest._source_slides(pid)}


def _origin(row: LibSlide) -> str | None:
    return (row.content or {}).get("origin_slide_id")


def _status(d: LibDeck) -> str:
    # "ready" only once queued stars have landed, so a star the user just set never flickers off
    return "ingesting" if d.status == "ready" and d.pending_favourites else d.status


def project_links(pid: str) -> dict:
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    out: dict = {"source": None, "generated": None, "favourites": {}}
    if _converted(p):
        d = source_deck(pid)
        if d is not None:
            by_index = _source_ids(pid)
            favs = {by_index[r.index]: r.id for r in ingest.slides_of(d.id) if r.favourite and r.index in by_index}
            out["source"] = {"deck_id": d.id, "status": _status(d), "favourites": favs,
                             "pending": list(d.pending_favourites or [])}
            out["favourites"].update(favs)
    g = generated_deck(pid)
    if g is not None:
        rows = ingest.slides_of(g.id)
        copied = {_origin(r): (r.content or {}).get("origin_version_id") for r in rows if _origin(r)}
        stale = [s.id for s in db.slides_of(pid)
                 if s.id in copied and s.approved_version_id and s.approved_version_id != copied[s.id]]
        # approved slides the copy does not have yet (approved after it was saved); unknown while it is copying
        missing = [s.id for s, _ in ingest._approved(pid) if s.id not in copied] if g.status == "ready" else []
        favs = {_origin(r): r.id for r in rows if r.favourite and _origin(r)}
        out["generated"] = {"deck_id": g.id, "status": _status(g), "stale_slide_ids": stale,
                            "missing_slide_ids": missing, "favourites": favs,
                            "pending": list(g.pending_favourites or [])}
        # A slide can be starred as both its source and its design; the per-kind maps above tell them apart.
        out["favourites"].update(favs)
    return out


@router.get("/project-links/{pid}")
async def get_project_links(pid: str):
    return await asyncio.to_thread(project_links, pid)


# ------------------------------------------------------------------ favourite from a deck view
class ProjectFavourite(BaseModel):
    slide_id: str
    kind: Literal["source", "generated"]
    favourite: bool = True


def _set_favourite(row_id: str, fav: bool) -> None:
    """Called on the event loop (as tagging.patch_slide is): it publishes, and the bus is not thread-safe."""
    row = db.get(LibSlide, row_id)
    if row is None:
        return
    if row.favourite != fav:
        db.update(LibSlide, row_id, favourite=fav, favourited_at=db.now() if fav else None)
        tagging._reindex([row_id])
    if fav and row.ai_status in ("none", "error"):
        tagging.enqueue([row_id])   # emits the slide event itself
    else:
        common.emit("slide", slide_id=row_id, ai_status=row.ai_status)


def _queue(deck_id: str, origin_id: str, fav: bool) -> bool:
    """Record a star on a deck still being copied. True = it is queued (or already applied, deck now ready).
    On the event loop, like _set_favourite."""
    with db.session() as s:
        d = s.get(LibDeck, deck_id)
        if d is None:
            return False
        pending = [x for x in (d.pending_favourites or []) if x != origin_id] + ([origin_id] if fav else [])
        d.pending_favourites = pending
        s.add(d)
        s.commit()
    # The copy may have finished between the read above and now: apply it ourselves (idempotent).
    retag = ingest.apply_pending_favourites(deck_id)
    if retag:
        tagging.enqueue(retag)
    return fav


def _out(lib_slide_id: str | None, deck_id: str | None, pending: bool) -> dict:
    return {"lib_slide_id": lib_slide_id, "deck_id": deck_id, "pending": pending}


async def _favourite_source(p: Project, s: Slide, fav: bool) -> dict:
    if not _converted(p) or ingest._made_here(s):
        raise HTTPException(400, "This slide has no PowerPoint slide behind it — favourite its approved design instead.")
    origin_id = (await asyncio.to_thread(_source_ids, p.id)).get(s.index, s.id)
    d = await asyncio.to_thread(source_deck, p.id)
    if d is None:
        if not fav:
            return _out(None, None, False)
        d = await ingest.start_from_project(p.id, "source", force=True, pending_favourites=[origin_id])
        return _out(None, d.id, True)
    if d.status != "ready":
        return _out(None, d.id, _queue(d.id, origin_id, fav))
    row = next((r for r in ingest.slides_of(d.id) if r.index == s.index), None)
    if row is None:
        raise HTTPException(404, "This slide is not in the library copy of the deck.")
    _set_favourite(row.id, fav)
    return _out(row.id, d.id, False)


async def _favourite_generated(p: Project, s: Slide, fav: bool) -> dict:
    d = await asyncio.to_thread(generated_deck, p.id)
    if not fav:
        # Off everywhere it could come back from: the current deck, its queue, and — while a newer copy is
        # being made — the deck it replaces, whose favourites that copy is about to carry forward.
        decks = [d] if d else []
        if d is not None and d.status != "ready":
            _queue(d.id, s.id, False)
            older = db.get(LibDeck, d.supersedes_id) if d.supersedes_id else None
            decks += [older] if older else []
        hit = None
        for x in decks:
            for r in ingest.slides_of(x.id):
                if _origin(r) == s.id and r.favourite:
                    _set_favourite(r.id, False)
                    hit = hit or r.id
        return _out(hit, d.id if d else None, False)
    if s.status != "approved" or not s.approved_version_id or not s.included or runner.is_removed(s):
        raise HTTPException(400, "Approve this slide first — the library keeps approved designs.")
    if d is not None and d.status != "ready":
        return _out(None, d.id, _queue(d.id, s.id, True))
    row = next((r for r in ingest.slides_of(d.id) if _origin(r) == s.id), None) if d else None
    if row is not None and (row.content or {}).get("origin_version_id") == s.approved_version_id:
        _set_favourite(row.id, True)
        return _out(row.id, d.id, False)
    # Missing or stale: a new copy of the approved slides replaces the old one (same name and title).
    new = await ingest.start_from_project(p.id, "generated", force=True, supersedes=d.id if d else "",
                                          project=d.project if d else None, title=d.title if d else None,
                                          pending_favourites=[s.id])
    return _out(None, new.id, True)


@router.post("/project-favourite")
async def project_favourite(body: ProjectFavourite):
    s = db.get(Slide, body.slide_id)
    if s is None:
        raise HTTPException(404, "Slide not found")
    p = db.get(Project, s.project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    if body.kind == "source":
        return await _favourite_source(p, s, body.favourite)
    return await _favourite_generated(p, s, body.favourite)


# ------------------------------------------------------------------ insert into a deck
class InsertBody(BaseModel):
    lib_slide_ids: list[str] = Field(default_factory=list)
    after: int | None = None   # as runner.add_slide: after this many slides (1-based "after slide n"); 0 = first, None = last


def citation(d: LibDeck, row: LibSlide) -> str:
    name = (d.title or d.filename or d.project or "Library deck").strip()
    # the real slide number in a PowerPoint (hidden slides count); a generated deck's index is its own numbering
    n = (row.content or {}).get("source_number") or row.index
    return f"{name}, slide {n} (slide library)"


def _copy_images(sc: SlideContent, deck_id: str, pid: str) -> SlideContent:
    """Bring the pictures the content names into the project, under content-addressed keys (`l_<sha>`): library
    keys (`img3`) mean nothing in another deck and would collide with its own. A picture whose file is gone is
    left out, with a warning, so no key on the slide is unresolvable."""
    src = {f.stem: f for f in (common.library_dir() / deck_id / "assets").glob("*.*")}
    dest_dir = db.project_dir(pid) / "assets"
    kept, lost = [], 0
    for img in sc.images:
        f = src.get(img.key)
        if f is None:
            lost += 1
            continue
        key = "l_" + hashlib.sha1(f.read_bytes()).hexdigest()[:10]
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not any(dest_dir.glob(f"{key}.*")):
            shutil.copy2(f, dest_dir / f"{key}{f.suffix.lower()}")
        kept.append(img.model_copy(update={"key": key}))
    warnings = list(sc.warnings) + ([f"{lost} picture(s) from the library slide could not be found and were left out."]
                                    if lost else [])
    return sc.model_copy(update={"images": kept, "warnings": warnings})


def _ledger(row: LibSlide, sc: SlideContent, sid: str) -> list[dict]:
    """The library slide's ledger with ids unique in this project. A figure a reference document brought into the
    original is asserted here by the library slide itself (cited through library_source), so it becomes "text":
    `doc` facts are re-derived from *this* project's documents on every re-plan (runner.plan) and would be lost."""
    got = facts.load(row.facts) if row.facts is not None else facts.extract(sc.for_prompt(), prefix="f")
    out = []
    for n, f in enumerate(got, 1):
        out.append(f.model_copy(update={"id": f"{sid}f{n}", "origin": "text" if f.origin == "doc" else f.origin}))
    return facts.dump(out)


def insert(pid: str, lib_ids: list[str], after: int | None) -> list[Slide]:
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    if p.status in _BUSY:
        raise HTTPException(409, "The deck is being planned — insert once it is ready.")
    ids = list(dict.fromkeys(i for i in lib_ids if i))
    if not ids:
        raise HTTPException(400, "Pick at least one library slide.")
    if len(ids) > MAX_INSERT:
        raise HTTPException(400, f"Insert at most {MAX_INSERT} slides at a time.")
    rows = [db.get(LibSlide, i) for i in ids]
    if any(r is None for r in rows):
        raise HTTPException(404, "Library slide not found")
    every = db.slides_of(pid)
    live = [s for s in every if not runner.is_removed(s)]
    removed = [s for s in every if runner.is_removed(s)]
    at = len(live) if after is None else max(0, min(after, len(live)))
    converted = (p.source or "pptx") != "composed"
    idx = runner.next_index(pid)
    new: list[Slide] = []
    for i, row in enumerate(rows):
        d = db.get(LibDeck, row.deck_id)
        # A converted deck: an index past every source slide (index names a PowerPoint render, and this slide has
        # none here) and the ADDED marker — like a slide typed here it is really deleted, labelled "new", planned
        # by deckops.plan_slides and never mistaken for a PowerPoint slide when the deck is saved to the library.
        # A composed deck renumbers below.
        index = idx + i if converted else at + i + 1
        sc = SlideContent.model_validate(row.content or {}).model_copy(update={"index": index, "source_index": index})
        sc = _copy_images(sc, row.deck_id, pid)
        sid = db.new_id("s")
        plan: dict = {runner.LIBRARY_SOURCE_KEY: {
            "lib_slide_id": row.id, "deck_id": row.deck_id, "project": d.project if d else "",
            "deck_title": (d.title or d.filename) if d else "", "index": row.index,
            "origin": d.origin if d else "", "label": citation(d, row) if d else f"Slide library, slide {row.index}"}}
        if converted:
            plan[runner.ADDED_KEY] = True
        new.append(db.save(Slide(id=sid, project_id=pid, index=index, position=at + i + 1, content=sc.model_dump(),
                                 facts=_ledger(row, sc, sid), plan=plan)))
    runner.reposition(live[:at] + new + live[at:] + removed)
    return [db.get(Slide, s.id) for s in new]


@router.post("/insert/{pid}")
async def insert_slides(pid: str, body: InsertBody):
    from .. import main   # the project API's slide shape; imported late (main mounts this router)

    slides = await asyncio.to_thread(insert, pid, body.lib_slide_ids, body.after)
    runner.emit(pid, "slides")
    return {"slides": [main.slide_out(s, []) for s in slides]}
