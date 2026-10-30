"""Loads the prompt pack in /skill: skill doc, gold examples, task prompts."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from .config import BRAND_DIR, SKILL_DIR
from .spec import SlideSpec, parse_spec

log = logging.getLogger(__name__)


@dataclass
class Example:
    name: str
    variant: str  # A | B
    input: dict
    why: str
    output: str  # raw tagged text

    def spec(self, slide_id: str = "ex") -> SlideSpec:
        return parse_spec(self.output, slide_id)[0]


def _section(md: str, name: str) -> str:
    m = re.search(rf"^## {name}\s*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


@lru_cache
def examples() -> list[Example]:
    out = []
    for p in sorted((SKILL_DIR / "examples").glob("*.md")):
        md = p.read_text(encoding="utf-8")
        head = md.splitlines()[0]
        variant = "A" if "variant A" in head else "B"
        raw_in = re.sub(r"^```json\s*|\s*```$", "", _section(md, "Input"))
        out.append(Example(name=p.stem, variant=variant, input=json.loads(raw_in), why=_section(md, "Why"), output=_section(md, "Output")))
    return out


def read(name: str) -> str:
    return (SKILL_DIR / name).read_text(encoding="utf-8")


def _brand_rules() -> str:
    brand = BRAND_DIR / "BRAND.md"
    if not brand.exists():
        return ""
    return "# HP brand kit rules (these override anything above when they conflict)\n\n" + brand.read_text(encoding="utf-8")


@lru_cache
def system_prompt() -> str:
    """Static, cache-friendly system prefix shared by every *authoring* call (vLLM prefix caching).

    Authoring = plan, generate, repair, revise: everything that writes a slide and therefore needs the full skill
    doc plus all gold examples. Judgement calls use review_system_prompt() instead — see there.
    """
    from .assemble import icons

    parts = [read("HP_DECK_SKILL.md").replace("{{ICONS}}", " ".join(icons().keys()))]
    brand = _brand_rules()
    if brand:
        parts.append(brand)
    parts.append("# Gold examples\n\nStudy these. They show the quality bar, the output format and how source content becomes a slide.\n")
    for ex in examples():
        parts.append(
            f"## {ex.name} (variant {ex.variant})\n\n### Input\n```json\n{json.dumps(ex.input, ensure_ascii=False)}\n```\n\n"
            f"### Design reasoning\n{ex.why}\n\n### Output\n{ex.output}\n"
        )
    return "\n\n".join(parts)


@lru_cache
def review_system_prompt() -> str:
    """The SECOND static prefix: brand rules + scoring discipline for the critic and the eval judge.

    Scoring a screenshot is a judgement task, not an authoring one. Handing it the full authoring prefix
    (skill doc + 13 complete gold specs, ~17k tokens of HTML) buys nothing and spreads attention over code the
    judge will never write. This prompt is byte-stable too, so vLLM simply caches a second prefix — it is not a
    cache loss, and every critic/judge call in the process shares it.
    """
    parts = [read("critic_system.md")]
    brand = _brand_rules()
    if brand:
        parts.append(brand)
    return "\n\n".join(parts)


# ------------------------------------------------------------------ critic contract
# Last-resort fallback only. The real list is parsed out of skill/critic.md by criteria() below, so the scoring
# code and the prompt cannot drift apart — editing the rubric in one place is now enough.
CRITERIA_FALLBACK = ("layout", "hierarchy", "brand", "fidelity", "craft", "interaction")
_SCORES_BLOCK = re.compile(r'"scores"\s*:\s*\{([^}]*)\}')


@lru_cache
def criteria() -> tuple[str, ...]:
    """The scoring leaves the critic must return, read from the `"scores": {...}` line of skill/critic.md."""
    m = _SCORES_BLOCK.search(read("critic.md"))
    if m:
        keys = tuple(dict.fromkeys(re.findall(r'"([a-z_]+)"\s*:', m.group(1))))
        if len(keys) >= 3:
            return keys
    log.error("could not read the criterion list out of skill/critic.md — falling back to %s", CRITERIA_FALLBACK)
    return CRITERIA_FALLBACK


def clear() -> None:
    examples.cache_clear()
    system_prompt.cache_clear()
    review_system_prompt.cache_clear()
    criteria.cache_clear()
