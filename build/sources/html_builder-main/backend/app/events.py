"""In-process pub/sub for live progress (SSE)."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


def _resync(channel: str, q: asyncio.Queue) -> None:
    """A subscriber fell behind (Chrome throttles EventSource in hidden tabs, and one run emits hundreds
    of events). Dropping silently left that client on stale state until a manual reload, so drop the
    backlog in one go and leave a single sentinel telling it to refetch the project.
    """
    dropped = 0
    while True:
        try:
            q.get_nowait()
            dropped += 1
        except asyncio.QueueEmpty:
            break
    try:
        q.put_nowait({"channel": channel, "type": "resync", "dropped": dropped})
    except asyncio.QueueFull:  # pragma: no cover - the queue was just emptied
        pass


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str) -> asyncio.Queue:
        if sum(map(len,self._subs.values()))>=24:
            from fastapi import HTTPException
            raise HTTPException(429,'Too many presentation event subscribers')
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        self._subs[channel].discard(q)
        if not self._subs[channel]:self._subs.pop(channel, None)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(channel, ())) + list(self._subs.get("*", ())):
            try:
                q.put_nowait({"channel": channel, **event})
            except asyncio.QueueFull:
                _resync(channel, q)


bus = EventBus()
