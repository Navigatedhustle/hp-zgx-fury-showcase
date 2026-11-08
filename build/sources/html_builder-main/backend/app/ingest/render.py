"""Render PPTX slides to PNG. PowerPoint COM (Windows) first, LibreOffice fallback.

Images are numbered 1..N over the *visible* slides, the same way parse_pptx() numbers SlideContent:
LibreOffice's PDF export silently omits hidden slides, so any other numbering puts the model in front of
the wrong original slide.
"""
from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image
from pptx import Presentation

from . import soffice
from .pptx_parse import is_hidden

log = logging.getLogger(__name__)
_com_lock = threading.Lock()
MSO_TRUE = -1

_WORKER = Path(__file__).with_name("ppt_worker.py")
# PowerPoint has no non-blocking mode: a modal dialog (repair prompt, activation nag, a deck left open by
# a crashed instance) blocks the COM call for ever. The export therefore runs in its own process with a
# deadline; a generous one, because a first cold start of PowerPoint plus a large deck is genuinely slow.
COM_TIMEOUT_BASE_S = 150.0
COM_TIMEOUT_PER_SLIDE_S = 12.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def visible_slide_count(pptx: Path) -> int | None:
    try:
        from showcase_app.document_parser import run_parser
        return run_parser('pptx-count', pptx)['count']
    except Exception as e:  # noqa: BLE001
        log.warning("could not count slides in %s: %s", pptx.name, e)
        return None


def _powerpnt_pids() -> set[str]:
    """PIDs of the PowerPoint processes running right now (empty off Windows / on any error)."""
    if sys.platform != "win32":
        return set()
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq POWERPNT.EXE", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW).stdout
    except Exception as e:  # noqa: BLE001
        log.warning("could not list PowerPoint processes: %s", e)
        return set()
    return {row[1] for row in csv.reader(out.splitlines()) if len(row) > 1 and row[1].isdigit()}


def _kill_powerpoint(pids: set[str]) -> None:
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=30, creationflags=_NO_WINDOW)
            log.warning("killed hung PowerPoint process %s", pid)
        except Exception as e:  # noqa: BLE001
            log.warning("could not kill PowerPoint process %s: %s", pid, e)


def _powerpoint(pptx: Path, out_dir: Path, expected: int | None = None) -> int:
    """Export via PowerPoint COM in a child process, so a hang is killable.

    COM is called from `asyncio.to_thread`, which cannot be cancelled: an in-process `Presentations.Open`
    stuck on a modal dialog would hold `_com_lock` for the lifetime of the server and every later import
    would hang behind it. The lock now only guards a `subprocess.run` with a deadline, so it is always
    released — and on a timeout both the worker and the PowerPoint instance it started are killed.
    """
    timeout = COM_TIMEOUT_BASE_S + COM_TIMEOUT_PER_SLIDE_S * max(1, expected or 1)
    cmd = [sys.executable, str(_WORKER), str(pptx.resolve()), str(out_dir.resolve())]
    with _com_lock:
        before = _powerpnt_pids()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            # subprocess.run has killed the worker; the PowerPoint it started is a separate process and
            # survives it, still sitting on its dialog, so take down anything that appeared since we began.
            _kill_powerpoint(_powerpnt_pids() - before)
            raise RuntimeError(f"PowerPoint did not respond within {timeout:.0f}s (hung or showing a dialog)") from None
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[-400:] or f"exit code {proc.returncode}")
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("RESULT "):
            return int(json.loads(line[len("RESULT "):])["count"])
    raise RuntimeError("PowerPoint export produced no result")


def _libreoffice(pptx: Path, out_dir: Path) -> int:
    import fitz  # PyMuPDF

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        pdf = soffice.convert(pptx, Path(td), "pdf", timeout=300)
        if pdf is None:
            raise RuntimeError("LibreOffice produced no PDF")
        doc = fitz.open(pdf)
        for i, page in enumerate(doc, start=1):
            zoom = 1600 / page.rect.width
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(str(out_dir / f"{i:03d}.png"))
        return len(doc)


def make_thumbs(out_dir: Path) -> None:
    for p in sorted(out_dir.glob("[0-9][0-9][0-9].png")):
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((480, 480))
            im.save(p.with_name(p.stem + "_thumb.jpg"), "JPEG", quality=82)


def _clear(out_dir: Path) -> None:
    """Never leave half-written or mis-numbered renders behind: a stale PNG is worse than none."""
    for pat in ("[0-9][0-9][0-9].png", "[0-9][0-9][0-9]_thumb.jpg"):
        for p in out_dir.glob(pat):
            p.unlink(missing_ok=True)


def render_slides(pptx: Path, out_dir: Path, renderer: str = "auto") -> str:
    """Render every visible slide to `out_dir/{n:03d}.png`. Returns the renderer used, or 'none'."""
    out_dir.mkdir(parents=True, exist_ok=True)
    order = {"auto": ["powerpoint", "libreoffice"], "powerpoint": ["powerpoint"], "libreoffice": ["libreoffice"], "none": []}[renderer]
    expected = visible_slide_count(pptx) if order else None
    for name in order:
        _clear(out_dir)
        try:
            n = _powerpoint(pptx, out_dir, expected) if name == "powerpoint" else _libreoffice(pptx, out_dir)
            if n and expected and n != expected:
                # Off-by-one renders are worse than no renders: the model would be shown one slide and
                # asked to restyle another. Drop them and say so.
                raise RuntimeError(f"{name} produced {n} image(s) for {expected} visible slide(s) — "
                                   "renders would not line up with the parsed slides")
            if n:
                make_thumbs(out_dir)
                return name
        except subprocess.CalledProcessError as e:  # noqa: PERF203
            log.warning("render with %s failed: %s", name, (e.stderr or b"")[-400:].decode("utf-8", "replace") or e)
        except Exception as e:  # noqa: BLE001
            log.warning("render with %s failed: %s", name, e)
    _clear(out_dir)
    return "none"
