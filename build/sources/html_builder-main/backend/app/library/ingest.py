"""Library decks in: upload, render, parse, fingerprint, duplicates, versions, save-from-project, delete, backup.

A deck is ingested like a converted project (render first, then parse — see runner.ingest) but never planned:
the library keeps finished slides, it does not redesign them. Every file is a copy under `data/library/<deck>/`.

Numbering: `LibSlide.index` counts *visible* slides, exactly like the renders (`renders/{index:03d}.png`) and
`SlideContent.index`; hidden slides are neither rendered nor parsed. The slide's real 1-based position in the
PowerPoint — what `Slides.InsertFromFile` needs — is `content["source_number"]`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import select as sa_select
from starlette.background import BackgroundTask

from .. import facts
from ..config import settings
from ..ingest.pptx_parse import SlideContent, parse_pptx
from ..ingest.render import make_thumbs, render_slides
from ..pipeline import runner
from ..store import db
from ..store.db import LibDeck, LibSlide, LibTag, Project, Slide
from . import common, search
from .fingerprint import also_in_counts, dhash, text_sha
from .schema import deck_out, slide_out

log = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD = 300 * 1024 * 1024   # same limit as a project upload (main.MAX_UPLOAD)
BACKUP_VERSION = 1
_IMAGE_CACHE = {"Cache-Control": "max-age=86400"}   # image URLs carry ?v=<updated_at>, so a change is a new URL
_tasks: dict[str, asyncio.Task] = {}                # deck id → its ingest job, so a delete can cancel just that one


# ------------------------------------------------------------------ small DB helpers
def _deck(deck_id: str) -> LibDeck:
    d = db.get(LibDeck, deck_id)
    if d is None:
        raise HTTPException(404, "Library deck not found")
    return d


def slides_of(deck_id: str) -> list[LibSlide]:
    with db.session() as s:
        return list(s.exec(db.select(LibSlide).where(LibSlide.deck_id == deck_id).order_by(LibSlide.index)))


def _favourites_by_deck() -> dict[str, int]:
    t = LibSlide.__table__
    with db.session() as s:
        rows = s.execute(sa_select(t.c.deck_id, func.count()).where(t.c.favourite.is_(True)).group_by(t.c.deck_id))
        return {d: n for d, n in rows}


def _favourites(deck_id: str) -> int:
    return _favourites_by_deck().get(deck_id, 0)


def _out(d: LibDeck) -> dict:
    return deck_out(d, favourites=_favourites(d.id))


async def _aset_deck(deck_id: str, **fields) -> LibDeck | None:
    """Write on a worker thread, publish on the loop (bus.publish is not thread-safe — see runner._db)."""
    d = await asyncio.to_thread(db.update, LibDeck, deck_id, **fields)
    if d is not None:
        common.emit("deck", deck_id=deck_id, status=d.status, stage_note=d.stage_note)
    return d


def _spawn(deck_id: str, coro) -> None:
    t = runner.jobs.spawn(common.CHANNEL, coro)
    if t is not None:
        _tasks[deck_id] = t
        t.add_done_callback(lambda _t: _tasks.pop(deck_id, None) if _tasks.get(deck_id) is _t else None)


def _find_duplicate(sha: str) -> LibDeck | None:
    with db.session() as s:
        return s.exec(db.select(LibDeck).where(LibDeck.file_sha == sha).order_by(LibDeck.created_at)).first()


def _duplicate_409(d: LibDeck) -> HTTPException:
    where = f" in {d.project}" if d.project else ""
    return HTTPException(409, {"code": "duplicate", "deck_id": d.id,
                               "message": f"This is already in the library as “{d.title or d.filename}”{where}."})


# ------------------------------------------------------------------ text + content
# PowerPoint defaults a picture's alt text to its file name ("fury.svg", "Picture 3"); that is noise in search.
_FILENAME_ALT = re.compile(r"^(?:[\w .()-]+\.(?:png|jpe?g|gif|bmp|tiff?|svg|emf|wmf|webp)|picture \d+|image \d+)$", re.I)


def slide_text(sc: SlideContent) -> str:
    """Every word on the slide except the title, one line per paragraph / table row / chart."""
    lines: list[str] = []
    for t in sc.texts:
        if t.kind == "title":
            continue
        lines += [p.text for p in t.paragraphs if p.text.strip()]
    for tb in sc.tables:
        lines += [" | ".join(c for c in row if c) for row in tb.rows if any(row)]
    for ch in sc.charts:
        lines += [x for x in (ch.title, " ".join(ch.categories), " ".join(s.name for s in ch.series)) if x.strip()]
    lines += [i.alt for i in sc.images if i.alt and not i.decorative and not _FILENAME_ALT.match(i.alt.strip())]
    return "\n".join(lines)


def _slide_row(deck_id: str, index: int, sc: SlideContent, render: Path | None,
               ledger: list[dict] | None = None, source_number: int | None = None,
               extra: dict | None = None) -> LibSlide:
    content = sc.model_dump()
    if source_number:
        content["source_number"] = source_number
    content.update(extra or {})   # origin_slide_id / origin_version_id for a deck saved from a project
    text = slide_text(sc)
    if ledger is None:
        ledger = facts.dump(facts.extract(sc.for_prompt(), prefix=f"s{index}f"))
    return LibSlide(deck_id=deck_id, index=index, title=sc.title, text=text, notes=sc.notes, content=content,
                    facts=ledger, phash=dhash(render) if render is not None and render.exists() else "",
                    text_sha=text_sha(sc.title, text))


def _replace_slides(deck_id: str, rows: list[LibSlide]) -> list[str]:
    """Swap a deck's slides for `rows` (a retry re-ingests). Returns the new ids; [] if the deck is gone."""
    old = slides_of(deck_id)
    if old:
        search.drop([s.id for s in old])
    with db.session() as s:
        if s.get(LibDeck, deck_id) is None:
            return []   # deleted while it was being read
        for o in s.exec(db.select(LibSlide).where(LibSlide.deck_id == deck_id)):
            s.delete(o)
        for r in rows:
            s.add(r)
        s.commit()
    return [r.id for r in rows]


def core_date(pptx: Path) -> datetime | None:
    """When the deck was written, from its core properties: last modified, else created."""
    try:
        from pptx import Presentation
        cp = Presentation(str(pptx)).core_properties
        dt = cp.modified or cp.created
    except Exception:  # noqa: BLE001
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _supersede(new_id: str) -> None:
    """Mark the deck the new one replaces. Done once the new deck is ready, so a failed import hides nothing."""
    d = db.get(LibDeck, new_id)
    if d is None or not d.supersedes_id or d.supersedes_id == new_id:
        return
    if db.update(LibDeck, d.supersedes_id, superseded_by=new_id) is not None:
        search.reindex_deck(d.supersedes_id)


# ------------------------------------------------------------------ the ingest job
async def ingest_deck(deck_id: str) -> None:
    """Render, parse, fingerprint and index one uploaded deck. Never plans."""
    dd = common.deck_dir(deck_id)
    src = dd / "source.pptx"
    try:
        await _aset_deck(deck_id, status="ingesting", stage_note="Rendering slide previews", error="")
        renderer = await asyncio.to_thread(render_slides, src, dd / "renders", settings().renderer)
        await _aset_deck(deck_id, renderer=str(renderer), stage_note="Reading slides")
        parsed = await asyncio.to_thread(parse_pptx, src, dd / "assets", dd / "renders")
        await _aset_deck(deck_id, stage_note="Fingerprinting and indexing")

        def _store() -> list[str]:
            rows = [_slide_row(deck_id, sc.index, sc, common.render_path(deck_id, sc.index), source_number=sc.source_index)
                    for sc in parsed.slides]
            ids = _replace_slides(deck_id, rows)
            if ids:
                search.reindex(ids)
            return ids

        ids = await asyncio.to_thread(_store)
        d = await asyncio.to_thread(db.get, LibDeck, deck_id)
        if d is None:
            return
        fields: dict = {"status": "ready", "stage_note": "", "slide_count": len(ids)}
        if not d.title:
            fields["title"] = parsed.title
        if d.deck_date is None:
            fields["deck_date"] = await asyncio.to_thread(core_date, src)
        await _aset_deck(deck_id, **fields)
        await asyncio.to_thread(_supersede, deck_id)
        await asyncio.to_thread(search.reindex_deck, deck_id)   # the title / date may have just been filled in
    except asyncio.CancelledError:
        await asyncio.to_thread(db.update, LibDeck, deck_id, status="error", stage_note="", error="Cancelled during import")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("library ingest failed")
        await _aset_deck(deck_id, status="error", stage_note="", error=f"Import failed: {e}")


def recover_interrupted() -> None:
    """Server restarted mid-import: the job is gone, so say so instead of showing "ingesting" for ever.
    Call it from main.lifespan next to `runner.recover_interrupted()`. The deck can be retried
    (`POST /decks/{id}/retry`) since its source.pptx is still on disk."""
    with db.session() as s:
        for d in s.exec(db.select(LibDeck).where(LibDeck.status == "ingesting")):
            d.status, d.stage_note, d.error = "error", "", "Interrupted by server restart — retry the import"
            s.add(d)
        s.commit()


# ------------------------------------------------------------------ upload
async def _receive(file: UploadFile, dest: Path) -> str:
    """Stream the upload to `dest`, hashing as it goes. Returns the sha256."""
    h = hashlib.sha256()
    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "File too large (max 300 MB)")
                h.update(chunk)
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "That file is empty.")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return h.hexdigest()


def _incoming() -> Path:
    d = common.library_dir() / "_incoming"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{secrets.token_hex(8)}.part"


def _check_supersedes(supersedes: str) -> str:
    if supersedes:
        _deck(supersedes)
    return supersedes


@router.post("/decks")
async def upload_deck(file: UploadFile = File(...), project: str = Form(...), title: str = Form(""),
                      supersedes: str = Form(""), force: str = Form("")):
    name = file.filename or "deck.pptx"
    if not name.lower().endswith(".pptx"):
        raise HTTPException(400, "Please upload a .pptx file (save .ppt files as .pptx first).")
    project = project.strip()
    if not project:
        raise HTTPException(400, "Say which project this deck belongs to.")
    _check_supersedes(supersedes.strip())
    tmp = _incoming()
    sha = await _receive(file, tmp)
    dup = await asyncio.to_thread(_find_duplicate, sha)
    if dup is not None and force.strip().lower() not in ("true", "1", "yes"):
        tmp.unlink(missing_ok=True)
        raise _duplicate_409(dup)
    d = await asyncio.to_thread(db.save, LibDeck(project=project, title=title.strip(), filename=name, file_sha=sha,
                                                 origin="upload", supersedes_id=supersedes.strip(),
                                                 status="ingesting", stage_note="Queued"))
    shutil.move(str(tmp), common.source_pptx(d.id))
    _spawn(d.id, ingest_deck(d.id))
    common.emit("deck", deck_id=d.id, status=d.status, stage_note=d.stage_note)
    return deck_out(d, favourites=0)


@router.post("/decks/{deck_id}/retry")
async def retry_deck(deck_id: str):
    """Import a deck again from its stored source.pptx — after an error or an interrupted restart."""
    d = _deck(deck_id)
    if d.status == "ingesting" and deck_id in _tasks:
        raise HTTPException(409, "This deck is still being imported.")
    if d.origin == "generated" or not common.source_pptx(deck_id).exists():
        raise HTTPException(400, "This deck has no PowerPoint to import again.")
    d = db.update(LibDeck, deck_id, status="ingesting", stage_note="Queued", error="")
    _spawn(deck_id, ingest_deck(deck_id))
    return _out(d)


# ------------------------------------------------------------------ decks
@router.get("/decks")
async def list_decks():
    def _q() -> list[dict]:
        favs = _favourites_by_deck()
        with db.session() as s:
            decks = list(s.exec(db.select(LibDeck).order_by(LibDeck.created_at.desc())))
        return [deck_out(d, favourites=favs.get(d.id, 0)) for d in decks]
    return await asyncio.to_thread(_q)


@router.get("/decks/{deck_id}")
async def get_deck(deck_id: str):
    def _q() -> dict:
        d = _deck(deck_id)
        slides = slides_of(deck_id)
        also = also_in_counts(slides)
        return {"deck": deck_out(d, favourites=sum(1 for s in slides if s.favourite)),
                "slides": [slide_out(s, d, also_in=also.get(s.id, 0)) for s in slides]}
    return await asyncio.to_thread(_q)


class DeckPatch(BaseModel):
    project: str | None = None
    title: str | None = None
    deck_date: str | None = None   # ISO date or datetime; "" clears it


def _parse_date(v: str) -> datetime | None:
    v = v.strip()
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"Not a date: {v!r} (use YYYY-MM-DD)") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.patch("/decks/{deck_id}")
async def patch_deck(deck_id: str, body: DeckPatch):
    _deck(deck_id)
    fields: dict = {}
    if body.project is not None:
        if not body.project.strip():
            raise HTTPException(400, "A deck needs a project name.")
        fields["project"] = body.project.strip()
    if body.title is not None:
        fields["title"] = body.title.strip()
    if body.deck_date is not None:
        fields["deck_date"] = _parse_date(body.deck_date)
    d = await asyncio.to_thread(db.update, LibDeck, deck_id, **fields) if fields else _deck(deck_id)
    await asyncio.to_thread(search.reindex_deck, deck_id)
    common.emit("deck", deck_id=deck_id, status=d.status, stage_note=d.stage_note)
    return await asyncio.to_thread(_out, d)


def delete_deck_rows(deck_id: str) -> None:
    """Index rows, slide rows, the deck row and every version link to it; then its folder."""
    slides = slides_of(deck_id)
    if slides:
        search.drop([s.id for s in slides])
    touched: list[str] = []
    with db.session() as s:
        for o in s.exec(db.select(LibSlide).where(LibSlide.deck_id == deck_id)):
            s.delete(o)
        # The deck it replaced is current again; a deck that replaced this one now replaces nothing.
        for o in s.exec(db.select(LibDeck).where(LibDeck.superseded_by == deck_id)):
            o.superseded_by = ""
            s.add(o)
            touched.append(o.id)
        for o in s.exec(db.select(LibDeck).where(LibDeck.supersedes_id == deck_id)):
            o.supersedes_id = ""
            s.add(o)
        d = s.get(LibDeck, deck_id)
        if d is not None:
            s.delete(d)
        s.commit()
    for t in touched:
        search.reindex_deck(t)
    shutil.rmtree(common.library_dir() / deck_id, ignore_errors=True)


@router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str):
    _deck(deck_id)
    t = _tasks.pop(deck_id, None)
    if t is not None and not t.done():
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
    await asyncio.to_thread(delete_deck_rows, deck_id)
    common.emit("deck", deck_id=deck_id, status="deleted", stage_note="")
    return {"ok": True}


@router.get("/projects")
async def list_projects():
    """One row per project name: for autocomplete and the grouping in the Decks view."""
    def _q() -> list[dict]:
        favs = _favourites_by_deck()
        with db.session() as s:
            decks = list(s.exec(db.select(LibDeck)))
        out: dict[str, dict] = {}
        for d in decks:
            r = out.setdefault(d.project, {"project": d.project, "decks": 0, "slides": 0, "favourites": 0})
            r["decks"] += 1
            r["slides"] += d.slide_count
            r["favourites"] += favs.get(d.id, 0)
        return sorted(out.values(), key=lambda r: r["project"].lower())
    return await asyncio.to_thread(_q)


# ------------------------------------------------------------------ slides + images
def _lib_slide(slide_id: str) -> LibSlide:
    s = db.get(LibSlide, slide_id)
    if s is None:
        raise HTTPException(404, "Library slide not found")
    return s


@router.get("/slides/{slide_id}")
async def get_slide(slide_id: str):
    def _q() -> dict:
        s = _lib_slide(slide_id)
        d = db.get(LibDeck, s.deck_id)
        return {**slide_out(s, d, also_in=also_in_counts([s]).get(s.id, 0)),
                "text": s.text, "content": s.content or {}, "facts": s.facts or []}
    return await asyncio.to_thread(_q)


def placeholder_svg(label: str = "", sub: str = "No preview") -> str:
    """A 16:9 card standing in for a slide with no render (RENDERER=none, a failed render, a lost file)."""
    label = label.strip()
    if len(label) > 60:
        label = label[:57] + "…"
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900'>"
            "<rect width='1600' height='900' fill='#eef1f4'/>"
            "<rect x='40' y='40' width='1520' height='820' fill='none' stroke='#c9d1d9' stroke-width='4' "
            "stroke-dasharray='18 14' rx='24'/>"
            "<text x='800' y='440' text-anchor='middle' font-family='Segoe UI, system-ui, sans-serif' "
            f"font-size='64' font-weight='600' fill='#5b6670'>{escape(label or sub)}</text>"
            + (f"<text x='800' y='530' text-anchor='middle' font-family='Segoe UI, system-ui, sans-serif' "
               f"font-size='40' fill='#8a949c'>{escape(sub)}</text>" if label else "")
            + "</svg>")


def _placeholder(label: str = "") -> Response:
    return Response(placeholder_svg(label), media_type="image/svg+xml", headers={"Cache-Control": "max-age=300"})


@router.get("/slides/{slide_id}/image")
async def slide_image(slide_id: str, thumb: bool = False):
    s = _lib_slide(slide_id)
    for f in ([common.render_path(s.deck_id, s.index, True)] if thumb else []) + [common.render_path(s.deck_id, s.index)]:
        if f.exists():
            return FileResponse(f, headers=_IMAGE_CACHE)
    return _placeholder(s.title)


@router.get("/decks/{deck_id}/cover.jpg")
async def deck_cover(deck_id: str):
    d = _deck(deck_id)
    first = await asyncio.to_thread(slides_of, deck_id)
    if first:
        for f in (common.render_path(deck_id, first[0].index, True), common.render_path(deck_id, first[0].index)):
            if f.exists():
                return FileResponse(f, headers=_IMAGE_CACHE)
    return _placeholder(d.title or d.filename)


# ------------------------------------------------------------------ save from a project
class FromProject(BaseModel):
    kind: str = "source"          # source | generated
    project: str | None = None    # library project name; defaults to the project's name
    title: str | None = None
    supersedes: str | None = None
    force: bool = False


def _made_here(s: Slide) -> bool:
    """Same test as deckops._made_here: added or merged in this app, so no PowerPoint slide behind it."""
    plan = s.plan or {}
    return bool(plan.get(runner.ADDED_KEY) or plan.get(runner.MERGED_FROM_KEY))


def _source_slides(pid: str) -> list[Slide]:
    """One row per source slide of a converted project (split parts share an index), in source order."""
    seen: dict[int, Slide] = {}
    for s in db.slides_of(pid):
        if _made_here(s) or s.part or s.index in seen:
            continue
        seen[s.index] = s
    return [seen[i] for i in sorted(seen)]


def _approved(pid: str) -> list[tuple[Slide, Path]]:
    """The deck as it would export: included, not removed, approved — with each one's final screenshot."""
    out = []
    for s in db.slides_of(pid):
        if not s.included or runner.is_removed(s) or s.status != "approved" or not s.approved_version_id:
            continue
        out.append((s, db.version_dir(pid, s.approved_version_id) / "shot_final.png"))
    return out


def _generated_sha(items: list[tuple[Slide, Path]]) -> str:
    """The same approved slides saved twice are the same input: hash each version id and its picture."""
    h = hashlib.sha256(b"generated\n")
    for s, shot in items:
        h.update(f"{s.approved_version_id}\n".encode())
        if shot.exists():
            h.update(hashlib.sha256(shot.read_bytes()).digest())
    return h.hexdigest()


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _carry_forward(deck_id: str, rows: list[LibSlide]) -> list[str]:
    """A new copy of a project's slides replaces an older one: what the user did to a slide in the old deck follows
    it, matched by `content["origin_slide_id"]` (the project Slide both copies were taken from).

    The favourite and every user-locked field (tags / summary / slide type, with its `*_user` flag) always carry.
    The model's own results carry only when the slide itself did not change (same approved version, same text and
    picture): a re-tag would cost a model call to say the same thing. Returns the ids of favourites that still need
    tagging; the caller queues them from the event loop (`tagging.enqueue` on a worker thread may find no loop)."""
    d = db.get(LibDeck, deck_id)
    if d is None or not d.supersedes_id:
        return []
    old = {(o.content or {}).get("origin_slide_id"): o for o in slides_of(d.supersedes_id)}
    old.pop(None, None)
    retag: list[str] = []
    for r in rows:
        o = old.get((r.content or {}).get("origin_slide_id"))
        if o is None:
            continue
        r.favourite, r.favourited_at = o.favourite, o.favourited_at
        same = ((o.content or {}).get("origin_version_id") == (r.content or {}).get("origin_version_id")
                and o.text_sha == r.text_sha and o.phash == r.phash)
        if same and o.ai_status == "done":
            r.summary, r.slide_type, r.tags = o.summary, o.slide_type, list(o.tags or [])
            r.entities, r.suggested, r.ai_status = list(o.entities or []), list(o.suggested or []), "done"
        if o.tags_user:
            r.tags, r.tags_user = list(o.tags or []), True
        if o.summary_user:
            r.summary, r.summary_user = o.summary, True
        if o.slide_type_user:
            r.slide_type, r.slide_type_user = o.slide_type, True
        if r.favourite and r.ai_status != "done":
            retag.append(r.id)
    return retag


def apply_pending_favourites(deck_id: str, *, before_ready: bool = False) -> list[str]:
    """Favourite the project slides starred while this deck was being copied (`LibDeck.pending_favourites`).
    Idempotent, so the copy job and a star that raced it may both call it. Returns the slides that need tagging.

    The copy job calls it twice — once before the deck reads "ready" (so a queued star never flickers off) and once
    after; a star (reuse.py) appends, then calls it if the deck is ready by then. Whatever the interleaving, one of
    the three sees the appended id."""
    with db.session() as s:
        d = s.get(LibDeck, deck_id)
        if d is None or not d.pending_favourites or (d.status != "ready" and not before_ready):
            return []
        wanted = set(d.pending_favourites)
        d.pending_favourites = []
        s.add(d)
        hit: list[LibSlide] = []
        for r in s.exec(db.select(LibSlide).where(LibSlide.deck_id == deck_id)):
            if (r.content or {}).get("origin_slide_id") in wanted:
                if not r.favourite:
                    r.favourite, r.favourited_at, r.updated_at = True, db.now(), db.now()
                    s.add(r)
                hit.append(r)
        s.commit()
    if hit:
        search.reindex([r.id for r in hit])
    return [r.id for r in hit if r.ai_status in ("none", "error")]


async def copy_project(deck_id: str, pid: str, kind: str) -> None:
    """Fill a library deck from a project's files — no re-render, no re-parse.

    Every row records the project Slide it came from (`content["origin_slide_id"]`; a generated row also the
    approved `origin_version_id`). That is how library/reuse.py maps the stars in the deck views to library
    slides, and tells a stale generated copy from a current one."""
    from . import tagging

    try:
        await _aset_deck(deck_id, stage_note="Copying slides")

        def _work() -> tuple[int, list[str]]:
            pdir = db.project_dir(pid)
            dd = common.deck_dir(deck_id)
            rd = dd / "renders"
            rd.mkdir(parents=True, exist_ok=True)
            rows: list[LibSlide] = []
            if kind == "source":
                shutil.copy2(pdir / "source.pptx", dd / "source.pptx")
                if (pdir / "assets").exists():
                    shutil.copytree(pdir / "assets", dd / "assets", dirs_exist_ok=True)
                for f in list((pdir / "renders").glob("[0-9][0-9][0-9].png")) + \
                        list((pdir / "renders").glob("[0-9][0-9][0-9]_thumb.jpg")):
                    shutil.copy2(f, rd / f.name)
                for s in _source_slides(pid):
                    sc = runner.parsed_content(s)
                    rows.append(_slide_row(deck_id, s.index, sc, common.render_path(deck_id, s.index),
                                           ledger=list(s.facts or []) or None,
                                           source_number=sc.source_index or s.index,
                                           extra={"origin_slide_id": s.id}))
            else:
                have = db.asset_files(pid)
                for n, (s, shot) in enumerate(_approved(pid), 1):
                    if shot.exists():
                        shutil.copy2(shot, rd / f"{n:03d}.png")
                    sc = runner.merged_content(s).model_copy(update={"index": n})
                    # The pictures its content names, so the slide can be inserted into another deck (reuse.py).
                    for img in sc.images:
                        if img.key in have:
                            (dd / "assets").mkdir(exist_ok=True)
                            shutil.copy2(have[img.key], dd / "assets" / have[img.key].name)
                    rows.append(_slide_row(deck_id, n, sc, common.render_path(deck_id, n),
                                           ledger=facts.dump(runner.slide_facts(s)),
                                           extra={"origin_slide_id": s.id, "origin_version_id": s.approved_version_id}))
                make_thumbs(rd)
            retag = _carry_forward(deck_id, rows)
            ids = _replace_slides(deck_id, rows)
            if ids:
                search.reindex(ids)
            return len(ids), retag

        n, retag = await asyncio.to_thread(_work)
        retag += await asyncio.to_thread(lambda: apply_pending_favourites(deck_id, before_ready=True))
        await _aset_deck(deck_id, status="ready", stage_note="", slide_count=n)
        retag += await asyncio.to_thread(apply_pending_favourites, deck_id)
        await asyncio.to_thread(_supersede, deck_id)
        await asyncio.to_thread(search.reindex_deck, deck_id)
        if retag:
            tagging.enqueue(retag)
    except asyncio.CancelledError:
        await asyncio.to_thread(db.update, LibDeck, deck_id, status="error", stage_note="", error="Cancelled")
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("save to library failed")
        await _aset_deck(deck_id, status="error", stage_note="", error=f"Could not save to the library: {e}")


async def start_from_project(pid: str, kind: str, *, project: str | None = None, title: str | None = None,
                             supersedes: str = "", force: bool = False,
                             pending_favourites: list[str] | None = None) -> LibDeck:
    """Create the library deck for a project's slides and start copying them: the one way in for the from-project
    route and for the stars in the deck views (library/reuse.py). Raises HTTPException."""
    p = db.get(Project, pid)
    if p is None:
        raise HTTPException(404, "Project not found")
    if kind not in ("source", "generated"):
        raise HTTPException(400, 'kind must be "source" or "generated"')
    if supersedes:
        _check_supersedes(supersedes)
    if kind == "source":
        src = db.project_dir(pid) / "source.pptx"
        if (p.source or "pptx") == "composed" or not src.exists():
            raise HTTPException(400, "This deck was written here — it has no PowerPoint source to save.")
        sha = await asyncio.to_thread(_sha_file, src)
        origin, deck_date = "converted", await asyncio.to_thread(core_date, src)
    else:
        items = await asyncio.to_thread(_approved, pid)
        if not items:
            raise HTTPException(400, "No approved slides yet — approve some slides first.")
        sha = await asyncio.to_thread(_generated_sha, items)
        origin, deck_date = "generated", p.updated_at
    dup = await asyncio.to_thread(_find_duplicate, sha)
    if dup is not None and not force:
        raise _duplicate_409(dup)
    # The approved slides of a converted deck would otherwise share the title of its PowerPoint (often saved too),
    # and the two read as one deck in every list and filter.
    title = (title or "").strip() or (p.deck_title or p.name).strip() + (" (generated)" if origin == "generated" else "")
    d = await asyncio.to_thread(db.save, LibDeck(
        project=(project or p.name).strip() or p.name, title=title,
        filename=p.filename, file_sha=sha, deck_date=deck_date, origin=origin, origin_project_id=pid,
        supersedes_id=supersedes or "", renderer=p.renderer if origin == "converted" else "screenshot",
        status="ingesting", stage_note="Queued", pending_favourites=list(pending_favourites or []) or None))
    _spawn(d.id, copy_project(d.id, pid, kind))
    common.emit("deck", deck_id=d.id, status=d.status, stage_note=d.stage_note)
    return d


@router.post("/from-project/{pid}")
async def from_project(pid: str, body: FromProject):
    """Keep a project's slides in the library: "source" = the PowerPoint it was converted from, "generated" =
    the approved slides as designed here (pictures; they export as pictures)."""
    d = await start_from_project(pid, body.kind, project=body.project, title=body.title,
                                 supersedes=body.supersedes or "", force=body.force)
    return deck_out(d, favourites=0)


# ------------------------------------------------------------------ backup / restore
def _rows() -> dict:
    with db.session() as s:
        return {"version": BACKUP_VERSION, "exported_at": datetime.now(timezone.utc).isoformat(),
                "decks": [d.model_dump(mode="json") for d in s.exec(db.select(LibDeck))],
                "slides": [x.model_dump(mode="json") for x in s.exec(db.select(LibSlide))],
                "tags": [t.model_dump(mode="json") for t in s.exec(db.select(LibTag))]}


def build_backup(dest: Path) -> None:
    """library.json (every library row) + files/<deck id>/… (sources, renders, assets)."""
    root = common.library_dir()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("library.json", json.dumps(_rows(), ensure_ascii=False))
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if f.is_file() and rel.parts[0] != "_incoming":
                # renders and pptx are already compressed: store them rather than deflate them again
                z.write(f, "files/" + rel.as_posix(),
                        compress_type=zipfile.ZIP_STORED if f.suffix.lower() in (".png", ".jpg", ".pptx") else None)


@router.get("/backup")
async def backup():
    tmp = Path(tempfile.mkdtemp(prefix="library-backup-"))
    dest = tmp / "library.zip"
    await asyncio.to_thread(build_backup, dest)
    stamp = datetime.now().strftime("%Y-%m-%d")
    return FileResponse(dest, media_type="application/zip", filename=f"slide-library-{stamp}.zip",
                        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True))


def _load(model, row: dict):  # noqa: ANN001
    """A row from library.json → a model instance, datetimes parsed (JSON carries them as strings)."""
    fields = {k: v for k, v in row.items() if k in model.model_fields}
    for k, v in fields.items():
        if isinstance(v, str) and k.endswith(("_at", "_date")) and v:
            try:
                fields[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                fields[k] = None
    return model(**fields)


_SAFE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def restore_backup(zf: zipfile.ZipFile) -> dict:
    """Merge a backup in: rows whose id already exists are skipped, and so are their files."""
    try:
        data = json.loads(zf.read("library.json"))
    except (KeyError, ValueError):
        raise HTTPException(400, "Not a library backup (no library.json).") from None
    added = {"decks": 0, "slides": 0, "tags": 0}
    new_decks: set[str] = set()
    new_slides: list[str] = []
    with db.session() as s:
        for row in data.get("decks", []):
            if not row.get("id") or not _SAFE.match(row["id"]) or s.get(LibDeck, row["id"]) is not None:
                continue
            d = _load(LibDeck, row)
            if d.status == "ingesting":
                d.status, d.stage_note, d.error = "error", "", "Backed up mid-import — retry the import"
            s.add(d)
            new_decks.add(d.id)
        have_decks = new_decks | {i for i in s.execute(sa_select(LibDeck.__table__.c.id)).scalars()}
        for row in data.get("slides", []):
            if not row.get("id") or row.get("deck_id") not in have_decks or s.get(LibSlide, row["id"]) is not None:
                continue
            s.add(_load(LibSlide, row))
            new_slides.append(row["id"])
        for row in data.get("tags", []):
            if not row.get("slug") or s.get(LibTag, row["slug"]) is not None:
                continue
            s.add(_load(LibTag, row))
            added["tags"] += 1
        s.commit()
    added["decks"], added["slides"] = len(new_decks), len(new_slides)
    root = common.library_dir().resolve()
    for info in zf.infolist():
        parts = PurePosixPath(info.filename).parts
        if info.is_dir() or len(parts) < 3 or parts[0] != "files" or parts[1] not in new_decks:
            continue
        if any(p in ("..", "") or ":" in p for p in parts):
            continue
        dest = (root / Path(*parts[1:])).resolve()
        if not dest.is_relative_to(root):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)
    if new_slides:
        search.reindex(new_slides)
    return added


@router.post("/restore")
async def restore(file: UploadFile = File(...)):
    tmp = _incoming()   # a backup holds every render: stream it to disk rather than into memory
    try:
        with tmp.open("wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)

        def _go() -> dict:
            try:
                zf = zipfile.ZipFile(tmp)
            except zipfile.BadZipFile:
                raise HTTPException(400, "That is not a zip file.") from None
            with zf:
                return restore_backup(zf)

        added = await asyncio.to_thread(_go)
    finally:
        tmp.unlink(missing_ok=True)
    common.emit("resync")
    return added
