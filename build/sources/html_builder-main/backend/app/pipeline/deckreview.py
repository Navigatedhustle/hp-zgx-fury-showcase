"""Work on the whole deck at once: one instruction applied to every slide, a consistency review across slides, and
the pre-export readiness checklist.

Everything slide-level already exists — revise, QA, the critic. What was missing is the view no single slide has:
"less text everywhere" means fifteen revise comments; "slide 3 says $4.2M and slide 9 says $4.5M" is invisible
to a critic that sees one slide at a time; and "is this deck ready to send?" had no answer short of opening
every slide.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from .. import facts
from ..config import Role, settings
from ..llm import client as llm
from ..skillpack import read
from ..spec import extract_json
from ..store import db
from ..store.db import Project, Slide, Version
from . import prompts
from . import runner as r
from .deckops import _label, _live

log = logging.getLogger(__name__)

CONSISTENCY_KEY = "consistency"      # Project.brief: the last consistency review
_TAG = re.compile(r"<[^>]+>")


# ------------------------------------------------------------------ one instruction, every slide
def instruct_scope(project_id: str, slide_ids: list[str] | None) -> list[Slide]:
    """The slides an instruction applies to: live, in the deck, with a design to revise from."""
    out = []
    for s in _live(project_id):
        if not s.included or (slide_ids is not None and s.id not in slide_ids):
            continue
        if r.best_version(s) is not None:
            out.append(s)
    return out


def _passes(v: Version | None) -> bool:
    qa = (v.qa or {}) if v else {}
    return bool(v and v.status == "ready" and qa.get("passed") and not qa.get("fatal"))


async def instruct_deck(project_id: str, instruction: str, slide_ids: list[str] | None = None) -> dict:
    """Revise each slide in scope from its approved (else best) design, one at a time. A slide that was approved
    stays approved — on the revision — only when the revision passes QA; otherwise it waits in review."""
    scope = await r._db(instruct_scope, project_id, slide_ids)
    done, kept = 0, 0
    try:
        for i, s in enumerate(scope, 1):
            await r.aset_project(project_id, status="generating",
                                 stage_note=f"Applying your instruction to slide {_label(s)} ({i} of {len(scope)})")
            base = await r._db(r.best_version, s)
            if base is None:
                continue
            was_approved = s.approved_version_id is not None
            v = await r.revise(s.id, base.id, instruction)
            done += 1
            if was_approved and _passes(v):
                await r._db(r.choose, s.id, v.id, source="auto")
                kept += 1
    finally:
        await r.aset_project(project_id, stage_note="")
        await r._arefresh_project_status(project_id)
        r.emit(project_id, "slides")
    return {"revised": done, "approvals_kept": kept}


# ------------------------------------------------------------------ consistency
def _on_slide_text(s: Slide) -> str:
    v = r.best_version(s)
    if v is None or not v.spec:
        return ""
    html = (v.spec or {}).get("html", "")
    return re.sub(r"\s+", " ", _TAG.sub(" ", re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html))).strip()[:900]


def _slides_for_review(project_id: str) -> list[Slide]:
    return [s for s in _live(project_id) if s.included and not (s.plan or {}).get("appendix")]


def code_issues(slides: list[Slide]) -> list[dict]:
    """What code can see for certain: one quantity with two values across slides, and the same layout twice
    in a row."""
    out: list[dict] = []
    seen: dict[tuple, tuple[Slide, facts.Fact]] = {}
    for s in slides:
        for f in r.slide_facts(s):
            if f.kind != "number" or f.value is None or not f.label.strip():
                continue
            words = " ".join(w for w in re.findall(r"[a-z]{4,}", f.label.lower()))
            if len(words.split()) < 2:
                continue
            key = (words, f.unit)
            if key in seen and seen[key][0].id != s.id and abs(seen[key][1].value - f.value) > 1e-9 * max(1, abs(f.value)):
                first, ff = seen[key]
                out.append({"slide_ids": [s.id, first.id], "kind": "numbers", "source": "code",
                            "issue": f"Slide {_label(first)} says {ff.raw} and slide {_label(s)} says {f.raw} for "
                                     f"“{f.label.strip()}”.",
                            "fix": f"Slide {_label(first)} states this as {ff.raw}; use the same figure, or say why it differs."})
            else:
                seen.setdefault(key, (s, f))
    for a, b in zip(slides, slides[1:]):
        pa, pb = (a.plan or {}).get("pattern"), (b.plan or {}).get("pattern")
        if pa and pa == pb and pa not in ("section",):
            out.append({"slide_ids": [b.id, a.id], "kind": "flow", "source": "code",
                        "issue": f"Slides {_label(a)} and {_label(b)} use the same layout ({pa}) back to back.",
                        "fix": f"Use a different composition from the previous slide, which is also a {pa}."})
    return out


def consistency_messages(project: Project, slides: list[Slide]) -> list[dict]:
    brief = project.brief or {}
    parts = []
    for i, s in enumerate(slides, 1):
        plan = s.plan or {}
        figs = ", ".join(f.raw for f in r.slide_facts(s) if f.tier == "key")[:300]
        parts.append(f"### S{i} (slide {_label(s)}, {plan.get('pattern', '')})\n"
                     f"Headline: {plan.get('headline', '')}\nMessage: {plan.get('key_message', '')}\n"
                     f"On the slide: {_on_slide_text(s) or '(not designed yet)'}\nKey figures: {figs or '-'}")
    text = prompts.fill(read("consistency.md"), DECK_TITLE=project.deck_title or project.name,
                        AUDIENCE=brief.get("audience", ""), NARRATIVE=brief.get("narrative", ""),
                        DECK="\n\n".join(parts))
    return [prompts._review(), prompts._user(text)]


def parse_issues(data, slides: list[Slide]) -> list[dict]:
    hs = {f"S{i}": s for i, s in enumerate(slides, 1)}
    out = []
    for e in (data or {}).get("issues", []) if isinstance(data, dict) else []:
        if not isinstance(e, dict):
            continue
        ids = [hs[h].id for h in (str(x).strip() for x in e.get("slides") or []) if h in hs]
        if not ids or not str(e.get("issue", "")).strip():
            continue
        out.append({"slide_ids": ids, "kind": str(e.get("kind", "story"))[:20], "source": "model",
                    "issue": str(e["issue"])[:400], "fix": str(e.get("fix", ""))[:400]})
    return out[:8]


async def review_consistency(project_id: str) -> dict:
    p = await r._db(db.get, Project, project_id)
    slides = await r._db(_slides_for_review, project_id)
    await r.aset_project(project_id, stage_note="Reviewing the deck as a whole")
    issues = await r._db(code_issues, slides)
    note = ""
    try:
        if not settings().llm_mock and slides:
            msgs = await r._db(consistency_messages, p, slides)
            reply = await llm.chat(msgs, role=Role.review, temperature=0.2, max_tokens=2000, stage="consistency")
            issues += parse_issues(extract_json(reply.text), slides)
    except Exception as e:  # noqa: BLE001 — code's findings still stand without the model's
        log.warning("consistency review failed: %s", e)
        note = "The model review failed; only the checks code can do are shown."
    result = {"at": datetime.now(timezone.utc).isoformat(), "issues": issues, "note": note}
    p = await r._db(db.get, Project, project_id)
    await r.aset_project(project_id, stage_note="", brief={**(p.brief or {}), CONSISTENCY_KEY: result})
    r.emit(project_id, "slides")
    return result


# ------------------------------------------------------------------ readiness
def readiness(project_id: str) -> dict:
    """Everything worth knowing before the deck goes out, slide by slide. `block` items are wrong; `warn` items
    may be deliberate. Nothing here stops an export."""
    items: list[dict] = []
    unapproved: list[Slide] = []

    def add(s: Slide | None, severity: str, kind: str, message: str) -> None:
        items.append({"slide_id": s.id if s else None, "label": _label(s) if s else "", "severity": severity,
                      "kind": kind, "message": message})

    for s in _live(project_id):
        if not s.included:
            continue
        v = r.best_version(s)
        if v is None:
            add(s, "block", "undesigned", "No design yet — it will be left out of the export.")
            continue
        if s.status != "approved":
            unapproved.append(s)
        qa = v.qa or {}
        if qa.get("fatal"):
            add(s, "block", "fact", "Changes a figure from the source: " + "; ".join(qa["fatal"])[:240])
        codes = {f.get("code"): f for f in qa.get("findings") or []}
        for code in ("chart-changed", "chart-missing", "chart-scale", "chart-hidden"):
            if code in codes and not qa.get("fatal"):
                add(s, "block" if code == "chart-changed" else "warn", "chart", codes[code].get("message", "")[:240])
        if qa.get("passed") is False and not qa.get("fatal"):
            n = sum(1 for f in qa.get("findings") or [] if f.get("severity") == "error")
            add(s, "warn", "qa", f"{n} layout problem(s) the automatic repairs could not clear.")
        for code in ("image-small", "image-blurry", "misaligned", "margin"):
            if code in codes:
                add(s, "warn", "layout", codes[code].get("message", "")[:240])
        meta = (v.spec or {}).get("meta", {})
        if not [n for n in meta.get("notes") or [] if str(n).strip()]:
            add(s, "warn", "notes", "No speaker notes.")
        if r.slide_facts(s) and not str(meta.get("sources") or "").strip():
            add(s, "warn", "sources", "States figures but cites no source.")
        cited = str(meta.get("sources") or "").lower()
        uncited = [c for c in (s.plan or {}).get(r.DOC_SOURCES_KEY) or [] if str(c).split(", p.")[0].lower() not in cited]
        if uncited:
            add(s, "warn", "sources", "Shows figures from a reference document without citing it: " + "; ".join(uncited)[:200])
        stale = (s.plan or {}).get(r.DOC_STALE_KEY)
        if isinstance(stale, dict) and str(stale.get("at") or "") > (v.created_at.isoformat() if v.created_at else ""):
            add(s, "block", "fact", f"Designed with figures from “{stale.get('doc', 'a document')}”, which has since been "
                                    f"removed ({', '.join(stale.get('figures') or [])[:120]}). Redesign this slide.")
    if unapproved:  # one line, not one per slide: on a fresh deck that would be every slide
        names = ", ".join(_label(s) for s in unapproved[:12]) + ("…" if len(unapproved) > 12 else "")
        items.insert(0, {"slide_id": unapproved[0].id, "label": _label(unapproved[0]), "severity": "warn",
                         "kind": "unapproved", "message": f"{len(unapproved)} slide(s) not approved ({names}) — "
                                                          f"the best-scoring design of each will be used."})
    p = db.get(Project, project_id)
    cons = ((p.brief or {}).get(CONSISTENCY_KEY) or {}) if p else {}
    if cons.get("issues"):
        add(None, "warn", "consistency", f"{len(cons['issues'])} open consistency issue(s) across slides.")
    elif not cons:
        add(None, "warn", "consistency", "The deck hasn't had a consistency review.")
    blocks = sum(1 for i in items if i["severity"] == "block")
    return {"ready": blocks == 0, "blocks": blocks, "warnings": len(items) - blocks, "items": items}
