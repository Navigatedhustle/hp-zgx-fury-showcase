"""Download filenames: one Content-Disposition helper for every export (deck HTML/PDF/PPTX, library PPTX)."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote


def ascii_name(stem: str, *, fallback: str = "deck", spaces: bool = False) -> str:
    """Transliterated fallback. A title with no Latin letters at all (CJK) leaves nothing usable, so
    those fall back to `fallback` rather than to a filename of punctuation. `spaces` keeps word breaks
    (the library names files "Project - selected slides"; deck exports use underscores already)."""
    folded = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    keep, edge = (r"[^A-Za-z0-9._\- ]+", "._- ") if spaces else (r"[^A-Za-z0-9._\-]+", "._-")
    out = re.sub(keep, "", folded).strip(edge)[:80]
    return out if re.search(r"[A-Za-z0-9]", out) else fallback


def disposition(stem: str, ext: str, *, fallback: str = "deck", spaces: bool = False) -> dict[str, str]:
    """Content-Disposition for a download.

    Starlette encodes response headers as latin-1, so a CJK or accented deck title (the planner writes
    it, so the user cannot see it coming) used to raise UnicodeEncodeError and 500 the whole export.
    RFC 5987 keeps the real name in `filename*` and leaves a transliterated ASCII fallback in `filename`.
    """
    name = f"{stem}.{ext}"
    return {"Content-Disposition": f'attachment; filename="{ascii_name(stem, fallback=fallback, spaces=spaces)}.{ext}"; '
                                   f"filename*=UTF-8''{quote(name, safe='')}"}
