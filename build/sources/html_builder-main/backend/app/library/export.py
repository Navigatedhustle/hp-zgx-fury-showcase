"""Selected library slides → one PPTX.

Two modes. "original" puts the real slides back together with PowerPoint COM — editable, with their own
master, theme and speaker notes (see `ppt_merge_worker.py` for how source formatting is kept). "picture"
is python-pptx only: one picture of each slide's render per page, notes attached — what works on any
machine, and what every slide falls back to when it has no source file (a deck made here) or when
PowerPoint is missing or fails.

Order is the order the user asked for, always: a mixed export inserts its picture slides through the same
COM session, at their place, rather than appending them afterwards.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pptx import Presentation
from pptx.util import Emu, Pt
from pydantic import BaseModel
from sqlmodel import select
from starlette.background import BackgroundTask

from ..config import settings
from ..downloads import disposition
from ..ingest import render
from ..ingest.pptx_parse import is_hidden
from ..store import db
from ..store.db import LibDeck, LibSlide
from . import common

log = logging.getLogger(__name__)
router = APIRouter()

MAX_SLIDES = 300
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
SLIDE_W, SLIDE_H = Emu(12192000), Emu(6858000)   # 16:9, PowerPoint's default
BLANK_LAYOUT = 6
EMU_PER_PT = 12700
_WORKER = Path(__file__).with_name("ppt_merge_worker.py")
# Opening each source deck costs about as much as a cold start's worth of slides.
COM_TIMEOUT_PER_DECK_S = 20.0


class ExportBody(BaseModel):
    slide_ids: list[str]
    mode: Literal["original", "picture"] = "original"


@dataclass
class Item:
    slide: LibSlide
    deck: LibDeck
    png: Path | None        # the 1600 px render, if there is one
    number: int | None      # the slide's number in source.pptx (hidden slides counted); None = picture only

    @property
    def source(self) -> Path:
        return common.source_pptx(self.deck.id)


# ------------------------------------------------------------------ choosing the slides
def _visible_numbers(pptx: Path) -> list[int]:
    """Actual 1-based slide numbers of the visible slides: library index i is the i-th visible slide."""
    try:
        return [n for n, s in enumerate(Presentation(str(pptx)).slides, start=1) if not is_hidden(s)]
    except Exception as e:  # noqa: BLE001
        log.warning("could not read %s: %s", pptx, e)
        return []


def _items(slide_ids: list[str]) -> list[Item]:
    ids = list(dict.fromkeys(slide_ids))  # the same slide twice is one slide
    if not ids:
        raise HTTPException(400, "No slides selected")
    if len(ids) > MAX_SLIDES:
        raise HTTPException(400, f"At most {MAX_SLIDES} slides per export ({len(ids)} selected)")
    with db.session() as s:
        slides = {x.id: x for x in s.exec(select(LibSlide).where(LibSlide.id.in_(ids)))}
        missing = [i for i in ids if i not in slides]
        if missing:
            raise HTTPException(400, f"Unknown slide id(s): {', '.join(missing[:10])}")
        decks = {d.id: d for d in s.exec(select(LibDeck).where(LibDeck.id.in_({x.deck_id for x in slides.values()})))}
    numbers: dict[str, list[int]] = {}
    out = []
    for i in ids:
        sl = slides[i]
        deck = decks.get(sl.deck_id)
        if deck is None:
            raise HTTPException(400, f"Slide {i} belongs to no deck")
        png = common.render_path(deck.id, sl.index)
        number = None
        src = common.source_pptx(deck.id)
        if deck.origin != "generated" and src.exists():
            number = (sl.content or {}).get("source_number")
            if not number:
                if deck.id not in numbers:
                    numbers[deck.id] = _visible_numbers(src)
                vis = numbers[deck.id]
                number = vis[sl.index - 1] if 0 < sl.index <= len(vis) else None
        out.append(Item(slide=sl, deck=deck, png=png if png.exists() else None, number=int(number) if number else None))
    return out


# ------------------------------------------------------------------ picture mode (python-pptx)
def write_picture_pptx(items: list[Item], out: Path) -> Path:
    """One page per slide: the render, fitted to a 16:9 page (full-bleed when it is 16:9), notes attached.
    A slide with no render gets its title on an otherwise blank page, so the count and order still hold."""
    from PIL import Image

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    blank = prs.slide_layouts[BLANK_LAYOUT]
    for it in items:
        page = prs.slides.add_slide(blank)
        if it.png is not None:
            with Image.open(it.png) as im:
                w, h = im.size
            scale = min(SLIDE_W / w, SLIDE_H / h)
            pw, ph = int(w * scale), int(h * scale)
            page.shapes.add_picture(str(it.png), (SLIDE_W - pw) // 2, (SLIDE_H - ph) // 2, width=pw, height=ph)
        else:
            box = page.shapes.add_textbox(Emu(SLIDE_W // 12), Emu(SLIDE_H // 3), Emu(SLIDE_W * 10 // 12), Emu(SLIDE_H // 4))
            box.text_frame.word_wrap = True
            box.text_frame.text = it.slide.title or f"{it.deck.title or it.deck.filename} — slide {it.slide.index}"
            box.text_frame.paragraphs[0].runs[0].font.size = Pt(32)
        if it.slide.notes:
            page.notes_slide.notes_text_frame.text = it.slide.notes
    prs.save(str(out))
    return out


# ------------------------------------------------------------------ original mode (PowerPoint COM)
def com_available() -> bool:
    """PowerPoint COM is only tried where it can exist, and never when the app is told not to drive it
    (RENDERER=none / libreoffice — tests, and machines without Office)."""
    return (sys.platform == "win32" and settings().renderer in ("auto", "powerpoint")
            and find_spec("win32com") is not None)


def _slide_size_pt(pptx: Path) -> tuple[float, float]:
    try:
        p = Presentation(str(pptx))
        return p.slide_width / EMU_PER_PT, p.slide_height / EMU_PER_PT
    except Exception:  # noqa: BLE001
        return SLIDE_W / EMU_PER_PT, SLIDE_H / EMU_PER_PT


def run_merge(job: dict, timeout: float) -> dict:
    """The worker, under the same discipline as ingest/render.py: one COM user at a time, a deadline, and
    on a timeout only the PowerPoint processes that appeared since we started are killed."""
    work = Path(job["out"]).parent
    job_file = work / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    cmd = [sys.executable, str(_WORKER), str(job_file)]
    with render._com_lock:
        before = render._powerpnt_pids()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=render._NO_WINDOW)
        except subprocess.TimeoutExpired:
            render._kill_powerpoint(render._powerpnt_pids() - before)
            raise RuntimeError(f"PowerPoint did not respond within {timeout:.0f}s (hung or showing a dialog)") from None
    if proc.stderr:
        log.info("library export worker: %s", proc.stderr.strip()[-1000:])
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[-400:] or f"exit code {proc.returncode}")
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise RuntimeError("PowerPoint merge produced no result")


def page_size(items: list[Item]) -> tuple[float, float]:
    """The slide size most of the original slides already have (ties: the first one's), so the fewest are fitted."""
    sizes = {d: _slide_size_pt(it.source) for d, it in {it.deck.id: it for it in items if it.number}.items()}
    votes = Counter(sizes[it.deck.id] for it in items if it.number)
    return max(votes, key=lambda size: (votes[size], -list(votes).index(size)))


def write_original_pptx(items: list[Item], out: Path) -> tuple[list[str], list[str], list[str]]:
    """Returns (fallback, skipped, resized) slide ids. Raises when PowerPoint failed outright. `resized`: originals
    from a deck of another slide size, fitted onto this file's page (ppt_merge_worker._fit_to_page)."""
    sw, sh = page_size(items)
    job = {"out": str(out.resolve()), "slide_width": sw, "slide_height": sh, "items": [
        {**({"file": str(it.source.resolve()), "number": it.number} if it.number else {}),
         **({"png": str(it.png.resolve())} if it.png else {}), "notes": it.slide.notes or ""}
        for it in items]}
    decks = len({it.deck.id for it in items if it.number})
    timeout = render.COM_TIMEOUT_BASE_S + render.COM_TIMEOUT_PER_SLIDE_S * len(items) + COM_TIMEOUT_PER_DECK_S * decks
    res = run_merge(job, timeout)
    if not out.exists():
        raise RuntimeError("PowerPoint saved no file")
    fell = {int(k) for k in res.get("fallback", [])}
    fallback = [it.slide.id for k, it in enumerate(items) if not it.number or k in fell]
    skipped = [items[int(k)].slide.id for k in res.get("skipped", [])]
    resized = [items[int(k)].slide.id for k in res.get("resized", [])]
    return fallback, skipped, resized


def build(items: list[Item], mode: str, work: Path) -> tuple[Path, str, list[str], list[str], list[str]]:
    """→ (file, mode actually used, fallback slide ids, skipped slide ids, resized slide ids)."""
    out = work / "export.pptx"
    if mode == "original" and any(it.number for it in items) and com_available():
        try:
            fallback, skipped, resized = write_original_pptx(items, out)
            return out, "original", fallback, skipped, resized
        except Exception as e:  # noqa: BLE001 — a picture of every slide beats no file
            log.warning("library export: PowerPoint merge failed, exporting pictures: %s", e)
            out.unlink(missing_ok=True)
    write_picture_pptx(items, out)
    return out, "picture", ([it.slide.id for it in items] if mode == "original" else []), [], []


# ------------------------------------------------------------------ download name
LIBRARY_STEM = "Library - selected slides"   # also the ASCII fallback for a project name with no Latin letters


def file_stem(items: list[Item]) -> str:
    projects = {it.deck.project.strip() for it in items}
    project = projects.pop() if len(projects) == 1 else ""
    project = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", project).strip()[:80]
    return f"{project} - selected slides" if project else LIBRARY_STEM


@router.post("/export.pptx")
async def export_pptx(body: ExportBody):
    """Selected slides, in the order given, as one PowerPoint file.

    Headers: `X-Export-Mode` (original | picture — what was actually built), `X-Export-Fallback` (slide ids
    that came out as pictures although originals were asked for), `X-Export-Skipped` (slide ids that could
    not be placed at all — no source and no render), `X-Export-Resized` (originals from a deck of another slide
    size, fitted onto the page — worth a look)."""
    items = _items(body.slide_ids)
    # not under library/: that folder holds one directory per deck, and backup walks it
    work = Path(tempfile.mkdtemp(prefix="libexport-"))
    try:
        out, mode, fallback, skipped, resized = await asyncio.to_thread(build, items, body.mode, work)
    except Exception as e:
        shutil.rmtree(work, ignore_errors=True)
        log.exception("library export failed")
        raise HTTPException(500, f"Export failed: {e}") from e
    headers = {**disposition(file_stem(items), "pptx", fallback=LIBRARY_STEM, spaces=True), "X-Export-Mode": mode,
               "X-Export-Fallback": ",".join(fallback), "X-Export-Skipped": ",".join(skipped),
               "X-Export-Resized": ",".join(resized),
               "Access-Control-Expose-Headers": "X-Export-Mode, X-Export-Fallback, X-Export-Skipped, X-Export-Resized, "
                                                "Content-Disposition"}
    return FileResponse(out, media_type=PPTX_MIME, headers=headers,
                        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))
