"""Decks written here rather than converted from a PowerPoint.

The converter's pipeline is: parse a .pptx → render it → plan → generate two variants → QA → review →
export. Everything from `plan` onwards only ever sees `SlideContent`, so a composed deck needs to
produce exactly that and nothing else changes: the same planner, the same fact ledger, the same
critic, the same exports.

So this module is small on purpose. It creates blank slides, lets them be typed into, and — when the
user would rather not start from an empty page — asks the model for an outline that fills them in.
There is no second pipeline.

What a composed deck does *not* have is a source render, which matters in three places the code
already handles by asking rather than assuming: the planner sends thumbnails only when it has them,
the generator attaches the original slide only when `source_png` exists, and the critic scores
fidelity against the fact ledger, which is extracted from the typed content exactly as it is from a
parse.
"""
from __future__ import annotations

import json
import logging

from .ingest.pptx_parse import Paragraph, SlideContent, TextBlock

log = logging.getLogger(__name__)

# A composed deck the model drafts. Kept modest deliberately: a 40-slide outline from one paragraph of
# brief is a worse starting point than a tight 10 the user extends.
DEFAULT_SLIDES = 10
MAX_SLIDES = 30
MAX_SOURCE_CHARS = 60_000  # reference documents fed to the outline: ~15k tokens

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "deck_title": {"type": "string"},
        "audience": {"type": "string"},
        "tone": {"type": "string"},
        "narrative": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["title", "content", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["deck_title", "audience", "tone", "narrative", "slides"],
    "additionalProperties": False,
}


def blank(index: int, title: str = "", lines: list[str] | None = None, notes: str = "") -> SlideContent:
    """One slide's content, in the shape the rest of the pipeline already reads.

    `index` is 1-based and doubles as the render name in the converter; a composed slide has no render,
    and every consumer of that path is `.exists()`-guarded, so the number is only an ordinal here.
    """
    blocks = []
    body = [ln for ln in (lines or []) if ln.strip()]
    if body:
        blocks.append(TextBlock(kind="body", paragraphs=[_para(ln) for ln in body]))
    return SlideContent(index=index, source_index=index, layout="composed", title=title.strip(),
                        texts=blocks, notes=notes.strip())


def _para(line: str) -> Paragraph:
    """One typed line. Two spaces per level indents, ** … ** bolds — the same convention the plan view
    already documents for edited PowerPoint copy, so there is one thing to learn rather than two."""
    text = line.rstrip()
    level = 0
    while text.startswith("  "):
        text = text[2:]
        level += 1
    bold = text.startswith("**") and text.endswith("**") and len(text) > 4
    return Paragraph(text=text[2:-2].strip() if bold else text.strip(), level=min(level, 4), bold=bold)


def content_from(title: str, body: str, notes: str, index: int) -> SlideContent:
    """What the compose form sends, as SlideContent. `body` is a textarea: one line per paragraph."""
    return blank(index, title=title or "", lines=(body or "").splitlines(), notes=notes or "")


# ------------------------------------------------------------------ the outline draft
def outline_messages(brief: dict, count: int, source_text: str = "") -> list[dict]:
    """Ask the model for a deck outline. Uses the authoring prefix, so it shares the cached system prompt.

    Deliberately NOT the planner's job. The planner decides how content becomes a design; this decides
    what the content *is*, and running them together would let a design decision quietly invent a fact.
    """
    from .pipeline.prompts import _system, _user
    from .skillpack import read

    want = {
        "deck_title": brief.get("deck_title", ""),
        "audience": brief.get("audience", ""),
        "tone": brief.get("tone", ""),
        "narrative": brief.get("narrative", ""),
        "about": brief.get("about", ""),
    }
    if brief.get("angle"):
        want["angle"] = brief["angle"]
    text = read("compose.md").replace("{{BRIEF}}", json.dumps(want, ensure_ascii=False, indent=1))
    text = text.replace("{{COUNT}}", str(count))
    text = text.replace("{{SOURCE}}", source_text.strip() or "(nothing — write the deck from the brief alone)")
    return [_system(), _user(text)]


def slides_from_outline(data: dict, limit: int = MAX_SLIDES) -> list[SlideContent]:
    """The model's outline as slide content. Anything unreadable is skipped, never guessed at."""
    out: list[SlideContent] = []
    for item in (data or {}).get("slides") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        raw = item.get("content")
        lines = [str(x) for x in raw] if isinstance(raw, list) else str(raw or "").splitlines()
        if not title and not any(ln.strip() for ln in lines):
            continue
        out.append(blank(len(out) + 1, title=title, lines=lines, notes=str(item.get("notes") or "")))
        if len(out) >= limit:
            break
    return out


def brief_from_outline(data: dict) -> dict:
    return {k: str((data or {}).get(k) or "") for k in ("deck_title", "audience", "tone", "narrative")}
