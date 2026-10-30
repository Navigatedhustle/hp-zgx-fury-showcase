"""Search the slide library by meaning, next to the two word indexes in `search.py`.

Optional, like every use of the embedding model: with `EMBED_MODEL` empty nothing here runs and search is exactly
what it was. With it, a query also finds slides that say the same thing in other words ("cost savings" → a slide
titled "TCO reduction"); they are listed after the slides that contain the words, never instead of them.

Scale is the point of the design. A flat scan of float vectors is fine for one document and too slow for ten
thousand slides in pure Python, so each vector is stored twice in `lib_vec`:

- `bits`: one sign bit per dimension, held in memory as a Python int. Comparing two is an XOR and a popcount —
  a few milliseconds for the whole library — and ranks candidates almost as well as the cosine does;
- `vec`: the float32 vector, read only for the few hundred best candidates, to score them exactly.

No extension, no new dependency, and nothing to keep in step by hand: `sync` embeds whatever is missing or whose
text changed (a hash of the text is stored with the vector), a search kicks it off in the background, and
`search.drop` removes a deleted slide's row.
"""
from __future__ import annotations

import hashlib
import heapq
import logging
import threading
import time
from array import array
from functools import lru_cache

from sqlmodel import select

from ..llm import embed
from ..store import db
from ..store.db import LibSlide

log = logging.getLogger(__name__)

TEXT_CHARS = 2000      # of a slide's own words; title and summary go in front of them
CANDIDATES = 300       # how many the bit comparison passes on to the exact one
FLOOR = 0.42           # cosine below this is not "about the same thing" for a short query against a whole slide
TOP = 40               # meaning adds at most this many slides to a result
QUERY_TIMEOUT_S = 2.5  # a person is typing: past this, the search answers with words alone
KICK_EVERY_S = 30.0    # how often a search may look for slides still to index
TABLE = ("CREATE TABLE IF NOT EXISTS lib_vec (slide_id TEXT PRIMARY KEY, model TEXT NOT NULL, sha TEXT NOT NULL, "
         "dim INTEGER NOT NULL, bits BLOB NOT NULL, vec BLOB NOT NULL)")

_lock = threading.Lock()
_worker: threading.Thread | None = None
_kicked = 0.0
_gen = 0                                   # bumped by every write, so the in-memory index knows it is stale
_index: tuple[int, str, list[str], list[int]] | None = None   # (gen, model, slide ids, sign bits)


def enabled() -> bool:
    return embed.enabled()


def _text(title: str, summary: str, text: str) -> str:
    return "\n".join(p for p in (title, summary, (text or "")[:TEXT_CHARS]) if p and p.strip())


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]  # noqa: S324 - a change detector, not security


def _bits(v) -> int:  # noqa: ANN001
    n = 0
    for x in v:
        n = (n << 1) | (x > 0)
    return n


def _touch() -> None:
    global _gen
    _gen += 1


def pending(limit: int | None = None) -> list[tuple[str, str]]:
    """(slide id, text to embed) for slides with no vector from the current model, or whose words changed since
    it was made."""
    from . import search as S
    name = embed.model()
    if not name:
        return []
    S._ensure()
    with S._conn() as c:
        have = {sid: sha for sid, sha in c.execute("SELECT slide_id, sha FROM lib_vec WHERE model = ?", (name,))}
    with db.session() as s:  # only the columns that are embedded: a slide row also carries its whole parse
        rows = list(s.exec(select(LibSlide.id, LibSlide.title, LibSlide.summary, LibSlide.text)))
    out = [(sid, t) for sid, title, summary, text in rows if (t := _text(title, summary, text)) and have.get(sid) != _sha(t)]
    return out[:limit] if limit else out


def sync(limit: int | None = None) -> int:
    """Embed what is pending and store it. Returns how many slides were written; stops at the first batch the
    server does not answer (a later search tries again once it has cooled off)."""
    from . import search as S
    name = embed.model()
    todo = pending(limit)
    done = 0
    for i in range(0, len(todo), embed.BATCH):
        batch = todo[i:i + embed.BATCH]
        vecs = embed.embed([t for _, t in batch])
        if vecs is None:
            break
        with S._conn() as c:
            for (sid, t), v in zip(batch, vecs):
                c.execute("INSERT OR REPLACE INTO lib_vec (slide_id, model, sha, dim, bits, vec) VALUES (?, ?, ?, ?, ?, ?)",
                          (sid, name, _sha(t), len(v), _bits(v).to_bytes((len(v) + 7) // 8, "big"), v.tobytes()))
        done += len(batch)
        _touch()
    if done:
        log.info("library: %d slide(s) indexed by meaning", done)
    return done


def kick() -> None:
    """Start indexing in the background, unless it is running or was looked at a moment ago. Never blocks."""
    global _worker, _kicked
    if not enabled():
        return
    with _lock:
        if (_worker is not None and _worker.is_alive()) or time.monotonic() - _kicked < KICK_EVERY_S:
            return
        _kicked = time.monotonic()

        def run() -> None:
            try:
                sync()
            except Exception:  # noqa: BLE001 - a background convenience: log, and let a later search try again
                log.exception("library: indexing by meaning failed")

        _worker = threading.Thread(target=run, name="lib-vec", daemon=True)
        _worker.start()


def forget(slide_ids: list[str]) -> None:
    """Remove these slides' vectors (called by `search.drop`)."""
    from . import search as S
    with S._conn() as c:
        c.executemany("DELETE FROM lib_vec WHERE slide_id = ?", [(i,) for i in slide_ids])
    _touch()


def _loaded(name: str) -> tuple[list[str], list[int]]:
    """Every indexed slide's id and sign bits, in memory; reloaded only after a write."""
    global _index
    from . import search as S
    cur = _index
    if cur is not None and cur[0] == _gen and cur[1] == name:
        return cur[2], cur[3]
    gen = _gen
    with S._conn() as c:
        rows = c.execute("SELECT slide_id, bits FROM lib_vec WHERE model = ?", (name,)).fetchall()
    ids = [r[0] for r in rows]
    bits = [int.from_bytes(r[1], "big") for r in rows]
    _index = (gen, name, ids, bits)
    return ids, bits


@lru_cache(maxsize=256)
def _query(name: str, q: str, dim: int) -> tuple | None:  # noqa: ARG001 - name and dim key the cache
    got = embed.embed([q], query=True, timeout=QUERY_TIMEOUT_S)
    return tuple(got[0]) if got else None


def nearest(qv, k: int = TOP, floor: float = FLOOR) -> list[tuple[str, float]]:  # noqa: ANN001
    """The `k` indexed slides closest in meaning to the unit vector `qv`: (slide id, cosine), best first."""
    from . import search as S
    name = embed.model()
    if not name:
        return []
    ids, bits = _loaded(name)
    if not ids:
        return []
    qb = _bits(qv)
    close = heapq.nsmallest(min(CANDIDATES, len(ids)), range(len(ids)), key=lambda i: (qb ^ bits[i]).bit_count())
    want = [ids[i] for i in close]
    out: list[tuple[str, float]] = []
    with S._conn() as c:
        for j in range(0, len(want), 500):
            part = want[j:j + 500]
            marks = ",".join("?" * len(part))
            for sid, blob in c.execute(f"SELECT slide_id, vec FROM lib_vec WHERE model = ? AND slide_id IN ({marks})",  # noqa: S608
                                       (name, *part)):
                v = array("f")
                v.frombytes(blob)
                cos = embed.cosine(qv, v)
                if cos >= floor:
                    out.append((sid, cos))
    return sorted(out, key=lambda x: -x[1])[:k]


def matches(q: str) -> dict[str, float]:
    """slide id → cosine for the slides that mean what `q` says. {} when meaning is off, the query is too short,
    or the embedding server did not answer in time. Also keeps the index catching up in the background."""
    q = " ".join(q.split())
    if not enabled() or len(q) < 3:
        return {}
    kick()
    from ..config import settings
    qv = _query(embed.model(), q.lower(), settings().embed_dim)
    if qv is None:
        _query.cache_clear()  # do not remember a miss: the server may be back for the next keystroke
        return {}
    return dict(nearest(qv))
