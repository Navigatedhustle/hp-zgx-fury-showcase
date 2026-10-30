"""Shared by every library module: where files live, and how progress reaches the UI."""
from __future__ import annotations

from pathlib import Path

from ..config import settings
from ..events import bus

CHANNEL = "library"   # SSE channel (GET /api/library/events) and the runner.jobs key for library work


def library_dir() -> Path:
    d = settings().data_dir / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def deck_dir(deck_id: str) -> Path:
    d = library_dir() / deck_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def source_pptx(deck_id: str) -> Path:
    return deck_dir(deck_id) / "source.pptx"


def render_path(deck_id: str, index: int, thumb: bool = False) -> Path:
    """Same naming as ingest/render.py: {n:03d}.png at 1600 px, {n:03d}_thumb.jpg at ≤480 px."""
    return deck_dir(deck_id) / "renders" / (f"{index:03d}_thumb.jpg" if thumb else f"{index:03d}.png")


def emit(kind: str, **data) -> None:
    """kind: "deck" (deck_id, status, stage_note) | "slide" (slide_id, ai_status) | "tags" | "resync"."""
    bus.publish(CHANNEL, {"type": kind, **data})
