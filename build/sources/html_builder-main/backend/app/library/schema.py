"""What the library API returns. `frontend/src/lib/library.ts` mirrors these shapes — change both together."""
from __future__ import annotations

from ..store.db import LibDeck, LibSlide, LibTag


def iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def deck_out(d: LibDeck, *, favourites: int | None = None) -> dict:
    return {
        "id": d.id, "project": d.project, "title": d.title, "filename": d.filename,
        "deck_date": iso(d.deck_date), "origin": d.origin, "origin_project_id": d.origin_project_id,
        "supersedes_id": d.supersedes_id, "superseded_by": d.superseded_by,
        "status": d.status, "stage_note": d.stage_note, "error": d.error, "renderer": d.renderer,
        "slide_count": d.slide_count, "favourites": favourites,
        "cover": f"/api/library/decks/{d.id}/cover.jpg?v={iso(d.updated_at)}",
        "created_at": iso(d.created_at), "updated_at": iso(d.updated_at),
    }


def slide_out(s: LibSlide, deck: LibDeck | None = None, *, also_in: int = 0, snippet: str = "") -> dict:
    v = iso(s.updated_at)
    return {
        "id": s.id, "deck_id": s.deck_id, "index": s.index, "title": s.title,
        "notes": s.notes, "favourite": s.favourite, "favourited_at": iso(s.favourited_at),
        "ai_status": s.ai_status, "ai_error": s.ai_error, "summary": s.summary, "slide_type": s.slide_type,
        "tags": s.tags or [], "entities": s.entities or [], "suggested": s.suggested or [],
        "tags_user": s.tags_user, "summary_user": s.summary_user, "slide_type_user": s.slide_type_user,
        "thumb": f"/api/library/slides/{s.id}/image?thumb=true&v={v}",
        "image": f"/api/library/slides/{s.id}/image?v={v}",
        # the same slide (by render fingerprint) in this many *other* decks
        "also_in": also_in,
        "superseded": bool(deck and deck.superseded_by),
        "deck": None if deck is None else {"id": deck.id, "project": deck.project, "title": deck.title,
                                           "origin": deck.origin, "deck_date": iso(deck.deck_date),
                                           "origin_project_id": deck.origin_project_id},
        # converted / generated decks: the project Slide this came from ("Open original" in the lightbox)
        "origin_slide_id": (s.content or {}).get("origin_slide_id") or None,
        "snippet": snippet,   # search only: HTML with <mark> around the matched words, everything else escaped
        "created_at": iso(s.created_at), "updated_at": v,
    }


def tag_out(t: LibTag, count: int = 0) -> dict:
    return {"slug": t.slug, "label": t.label, "facet": t.facet, "aliases": t.aliases or [],
            "approved": t.approved, "count": count}
