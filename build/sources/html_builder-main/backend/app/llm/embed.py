"""Text embeddings from an OpenAI-compatible `/v1/embeddings` server (vLLM `--runner pooling`).

Optional, like the review model's split: with `EMBED_MODEL` empty nothing here is called and every search that
could use meaning ranks by words alone. It is a third model behind the same ZRT gateway, picked by its label.

Synchronous on purpose. Its two callers are a worker thread building one slide's context and the document
digest job (which wraps it in `asyncio.to_thread`); neither needs the event loop, and a sync client cannot
get the per-loop semaphore of `llm.chat` wrong.

Every vector that leaves here is unit length, so a dot product is the cosine.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from array import array
from collections.abc import Sequence

from openai import OpenAI

from ..config import settings

log = logging.getLogger(__name__)

BATCH = 32
MAX_CHARS = 6000   # per text: well inside any embedding model's window, and more than a chunk ever is
RETRIES = (0.5, 2.0)   # seconds before the second and third attempt at one batch
COOL_OFF_S = 60.0      # after a batch fails for good, how long callers skip the server instead of queueing on it
_lock = threading.Lock()
# One request at a time, app-wide. The embedding model shares a GPU with a model that is streaming a slide:
# two hundred chunks sent at once would be felt there, and nothing here is waiting on a person.
_gate = threading.Semaphore(1)
_clients: dict[tuple[str, str], OpenAI] = {}
_warned: set[str] = set()
_down_until = 0.0


def model() -> str:
    """The embedding model's name on the wire, or "" when embeddings are off (not configured, or offline mock)."""
    s = settings()
    return "" if s.llm_mock else s.embed_model.strip()


def enabled() -> bool:
    return bool(model())


def _client() -> OpenAI:
    s = settings()
    key = (s.embed_base_url or s.llm_base_url, s.embed_api_key or s.llm_api_key)
    with _lock:
        if key not in _clients:
            _clients[key] = OpenAI(base_url=key[0], api_key=key[1], timeout=s.embed_timeout_s, max_retries=1)
        return _clients[key]


def _unit(v: Sequence[float], dim: int) -> array:
    """Cut to `dim` (0 = keep all) and scale to length 1. Cutting is only meaningful for a Matryoshka-trained
    model — which is why EMBED_DIM is off unless the user sets it."""
    v = v[:dim] if dim and len(v) > dim else v
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return array("f", (x / norm for x in v))


def embed(texts: list[str], *, query: bool = False, timeout: float | None = None) -> list[array] | None:
    """One unit vector per text, in order — or None when embeddings are off or the server failed.

    None is a normal answer, never an error to handle: the caller ranks without vectors. `query=True` adds the
    instruction prefix retrieval models are trained with for the asking side (documents go in bare).
    `timeout` is for a caller with a person waiting (a search box): one attempt, that long, and no cool-off
    for everyone else if it is missed.
    """
    global _down_until
    name = model()
    if not name or not texts or time.monotonic() < _down_until:
        return None
    s = settings()
    prefix = s.embed_query_prefix.replace("\\n", "\n") if query else ""
    out: list[array] = []
    try:
        client = _client() if timeout is None else _client().with_options(timeout=timeout, max_retries=0)
        for i in range(0, len(texts), BATCH):
            batch = [prefix + (t[:MAX_CHARS] or " ") for t in texts[i:i + BATCH]]
            for wait in ((*RETRIES, None) if timeout is None else (None,)):
                try:
                    with _gate:
                        r = client.embeddings.create(model=name, input=batch)
                    break
                except Exception:  # noqa: BLE001 - a busy or restarting server usually answers the next try
                    if wait is None:
                        raise
                    time.sleep(wait)
            out += [_unit(d.embedding, s.embed_dim) for d in sorted(r.data, key=lambda d: d.index)]
    except Exception as e:  # noqa: BLE001 - any failure degrades to word search; it must never fail a slide
        if timeout is None:
            _down_until = time.monotonic() + COOL_OFF_S
        why = f"{type(e).__name__}: {e}"[:200]
        if why not in _warned:
            _warned.add(why)
            log.warning("embeddings unavailable (%s) — ranking by words only", why)
        return None
    return out if len(out) == len(texts) else None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of two unit vectors of the same model; 0 when their sizes disagree (a stale index)."""
    return sum(x * y for x, y in zip(a, b)) if len(a) == len(b) else 0.0
