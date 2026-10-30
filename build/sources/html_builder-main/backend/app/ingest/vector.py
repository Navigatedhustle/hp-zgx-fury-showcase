"""EMF/WMF -> PNG.

PowerPoint stores pasted vector art (logos, Visio drawings, pasted Excel charts) as EMF/WMF, which no
browser renders. Converting keeps that art in the deck instead of dropping the most important visual on
the slide. LibreOffice does the conversion; when it is unavailable the caller falls back to cropping the
region out of the reference render.
"""
from __future__ import annotations

import gzip
import logging
import tempfile
from pathlib import Path

from . import soffice

log = logging.getLogger(__name__)

VECTOR_EXT = {"emf", "wmf", "emz", "wmz"}
_unavailable = False  # LibreOffice missing: stop retrying for the rest of the process


def sniff_ext(blob: bytes) -> str:
    """Magic-byte sniff for the vector formats python-pptx cannot name."""
    if blob[:4] == b"\x01\x00\x00\x00" and blob[40:44] == b" EMF":
        return "emf"
    if blob[:4] in (b"\xd7\xcd\xc6\x9a", b"\x01\x00\x09\x00") or blob[:2] == b"\x02\x00":
        return "wmf"
    if blob[:2] == b"\x1f\x8b":  # gzipped emz/wmz
        return "emz"
    return ""


def to_png(blob: bytes, ext: str, timeout: int = 120) -> bytes | None:
    """Convert an EMF/WMF/EMZ/WMZ blob to PNG bytes. Returns None when conversion is not possible."""
    global _unavailable
    ext = (ext or "").lower().lstrip(".")
    if ext not in VECTOR_EXT or _unavailable:
        return None
    if ext in ("emz", "wmz"):
        try:
            blob = gzip.decompress(blob)
        except Exception as e:  # noqa: BLE001
            log.warning("could not decompress %s: %s", ext, e)
            return None
        ext = sniff_ext(blob) or "emf"
    if soffice.find_soffice() is None:
        _unavailable = True
        log.warning("LibreOffice not found — EMF/WMF images cannot be converted")
        return None
    with tempfile.TemporaryDirectory(prefix="vector-", ignore_cleanup_errors=True) as td:
        src = Path(td) / f"art.{ext}"
        src.write_bytes(blob)
        try:
            out = soffice.convert(src, Path(td) / "out", "png", timeout=timeout)
        except Exception as e:  # noqa: BLE001
            log.warning("%s -> png conversion failed: %s", ext, e)
            return None
        return out.read_bytes() if out and out.exists() else None
