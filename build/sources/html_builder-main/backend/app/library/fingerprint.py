"""Fingerprints that find the same slide in another deck: a dHash of the render, and a hash of the words.

Exact match on either is what `also_in` counts. dHash survives re-encoding and a re-render at another size
(it compares neighbouring pixels of a 9x8 greyscale), so the slide pasted into next quarter's deck still
matches; it does not survive an edit, which is the point — an edited slide is a different slide.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from PIL import Image
from sqlalchemy import select as sa_select

from ..store import db
from ..store.db import LibSlide

_BLANK = "0" * 16   # a uniform image (blank slide, solid colour) — would match every other blank slide


def dhash(path: Path) -> str:
    """64-bit difference hash of an image, as 16 hex digits. "" for an unreadable or featureless image."""
    try:
        with Image.open(path) as im:
            g = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            px = g.tobytes()   # one byte per pixel in "L" mode
    except Exception:  # noqa: BLE001
        return ""
    bits = 0
    for y in range(8):
        row = px[y * 9:(y + 1) * 9]
        for x in range(8):
            bits = (bits << 1) | (1 if row[x] > row[x + 1] else 0)
    h = f"{bits:016x}"
    return "" if h == _BLANK else h


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", t).strip()


def text_sha(title: str, text: str) -> str:
    """Hash of the normalised words. "" when the slide has none, so empty slides never match each other."""
    t = normalise(f"{title}\n{text}")
    return hashlib.sha1(t.encode("utf-8")).hexdigest() if t else ""


def also_in_counts(slides: list[LibSlide]) -> dict[str, int]:
    """slide id → how many OTHER decks hold a slide with the same render fingerprint (else the same words,
    when the slide has no render). Two queries however many slides are asked about."""
    phashes = {s.phash for s in slides if s.phash}
    shas = {s.text_sha for s in slides if not s.phash and s.text_sha}
    by_phash: dict[str, set[str]] = defaultdict(set)
    by_sha: dict[str, set[str]] = defaultdict(set)
    t = LibSlide.__table__
    with db.session() as ses:
        for chunk in _chunks(sorted(phashes)):
            for ph, deck in ses.execute(sa_select(t.c.phash, t.c.deck_id).where(t.c.phash.in_(chunk))):
                by_phash[ph].add(deck)
        for chunk in _chunks(sorted(shas)):
            for sh, deck in ses.execute(sa_select(t.c.text_sha, t.c.deck_id).where(t.c.text_sha.in_(chunk))):
                by_sha[sh].add(deck)
    out: dict[str, int] = {}
    for s in slides:
        decks = by_phash.get(s.phash, set()) if s.phash else by_sha.get(s.text_sha, set()) if s.text_sha else set()
        out[s.id] = len(decks - {s.deck_id})
    return out


def _chunks(xs: list[str], n: int = 500):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]
