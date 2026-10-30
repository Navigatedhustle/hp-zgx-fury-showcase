"""Prompt construction.

Two static system prefixes, both byte-stable so vLLM caches them:

  * `_system()`   — the authoring prefix (skill doc + brand + all gold examples). Plan, generate, repair, revise.
  * `_review()`   — the judgement prefix (brand rules + scoring discipline). Critic and eval judge.

Nothing that varies per request may ever be added to either. Everything about *this* slide, *this* deck or
*this* attempt belongs in the user message.

The JSON schemas below travel in the request body (`extra_body={"guided_json": ...}`), not in a prompt, so
guided decoding costs the cache nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..llm.client import image_part
from ..skillpack import criteria, read, review_system_prompt, system_prompt
from ..spec import SlideSpec, to_tagged

VARIANT_NAMES = {"A": "cinematic, highly interactive", "B": "refined, minimal interaction"}

# ------------------------------------------------------------------ JSON reply schemas (guided decoding)
# These mirror the "Output" section of the matching prompt file, and are handed to vLLM as
# `extra_body={"guided_json": ...}` by the three stages that emit pure JSON: plan, critic, judge. They are NOT
# used for spec generation — constraining the decoder there would fight the free-form reasoning the slide code
# needs, and the tagged <meta><html><css><script> format is not JSON anyway.
#
# Kept deliberately loose about *vocabulary* (pattern, role and theme stay plain strings) so the catalogue can
# grow in skill/deck_plan.md without the decoder refusing a legal answer. What they pin down is the shape: the
# keys, their types and the fact that the reply is an object — which is the part `extract_json` used to get wrong.
_STR = {"type": "string"}


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "deck_title": _STR, "audience": _STR, "tone": _STR, "narrative": _STR,
        "slides": {"type": "array", "items": {
            "type": "object",
            "properties": {"index": {"type": "integer"}, "role": _STR, "pattern": _STR, "eyebrow": _STR,
                           "headline": _STR, "key_message": _STR, "idea_a": _STR, "idea_b": _STR, "theme": _STR,
                           "include": {"type": "boolean"},
                           # The figures and names that carry this slide's message, copied from the source
                           # exactly. They tier the fact ledger (app/facts.py): a key fact must be *on* the
                           # slide, a supporting one may live in the speaker notes. The planner owns this
                           # because it is the stage that decides what the slide is for.
                           "key_facts": {"type": "array", "items": _STR},
                           # Optional: other slides this one is thin and related enough to share a slide with.
                           # Only ever a suggestion the user accepts or ignores in the plan view (deckops.merge).
                           "merge_with": {"type": "array", "items": {"type": "integer"}},
                           # Optional: figures copied exactly from the user's reference documents that this slide
                           # should carry. Kept only if verbatim in a document (pipeline/reference.doc_facts).
                           "doc_facts": {"type": "array", "items": _STR},
                           # Optional: the document sections this slide draws on ("D1.S3"), from the section list
                           # in the reference block. The generator is given passages from them first.
                           "doc_refs": {"type": "array", "items": _STR}},
            "required": ["index", "role", "pattern", "eyebrow", "headline", "key_message", "idea_a", "idea_b",
                         "theme", "include", "key_facts"],
            "additionalProperties": False}},
    },
    "required": ["deck_title", "audience", "tone", "narrative", "slides"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"relative_quality": {"type": "integer", "minimum": 0, "maximum": 100},
                   "better": {"type": "string", "enum": ["reference", "candidate", "tie"]},
                   "gaps": {"type": "array", "items": _STR}},
    "required": ["relative_quality", "better", "gaps"],
    "additionalProperties": False,
}

AB_SCHEMA = {
    "type": "object",
    "properties": {"winner": {"type": "string", "enum": ["A", "B", "tie"]},
                   "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                   "reason": _STR},
    "required": ["winner", "confidence", "reason"],
    "additionalProperties": False,
}


def critic_schema() -> dict:
    """Built from skillpack.criteria(), so it follows skill/critic.md rather than duplicating it."""
    leaves = list(criteria())
    score = {"type": "number", "minimum": 0, "maximum": 10}
    return {
        "type": "object",
        "properties": {
            "scores": {"type": "object", "properties": {k: score for k in leaves}, "required": leaves,
                       "additionalProperties": False},
            "branches": {"type": "object", "additionalProperties": score},
            "issues": {"type": "array", "items": {
                "type": "object",
                "properties": {"severity": {"type": "string", "enum": ["high", "medium", "low"]},
                               "area": {"type": "string", "enum": leaves + ["design"]}, "problem": _STR, "fix": _STR},
                "required": ["severity", "area", "problem", "fix"], "additionalProperties": False}},
            "verdict": {"type": "string", "enum": ["pass", "fix"]},
        },
        "required": ["scores", "issues", "verdict"],
        "additionalProperties": False,
    }

# Goes in the USER message only. The system prompt is the shared, byte-identical prefix vLLM caches;
# nothing conditional may ever be added to it.
VERBATIM_RULE = ("COPY RULE: the source content below is the user's approved copy, already signed off word for word. "
                 "Use it verbatim — lay it out, and shorten only where a line genuinely cannot fit. "
                 "Never reword, rephrase, summarise or invent text.")

THUMB_MAX_W = 480  # planner thumbnails: make_thumbs() already writes them at this size


def fill(tpl: str, **kw) -> str:
    """Substitute {{PLACEHOLDER}} tokens. An unknown placeholder becomes the empty string, never a literal."""
    def rep(m):
        k = m.group(1)
        return str(kw.get(k, ""))
    return re.sub(r"\{\{([A-Z_]+)\}\}", rep, tpl)


_fill = fill  # pre-existing private name, kept so callers outside this module keep working


_TASK_SPLIT = re.compile(r"(?m)^(?=# Task: )")


def task(file: str, name: str) -> str:
    """One `# Task: …` section of a prompt file. Some files hold more than one related task (judge.md holds both
    the eval's reference comparison and the pipeline's A-vs-B choice) so that the prompt pack keeps one file per
    *job*, not one per call site."""
    for block in _TASK_SPLIT.split(read(file)):
        if block.startswith(f"# Task: {name}"):
            return block.strip()
    raise KeyError(f"{file} has no '# Task: {name}' section")


def _variant_brief(v: str) -> str:
    txt = read("variants.md")
    m = re.search(rf"^## {v}\s*\n(.*?)(?=^## |\Z)", txt, re.S | re.M)
    return m.group(1).strip() if m else ""


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def assets_listing(content: dict) -> str:
    lines = []
    for img in content.get("images") or []:
        lines.append(f"- `asset:{img['key']}` — {img.get('alt') or 'image'} ({img.get('px', '?')} px, originally at {img.get('position') or '?'})")
    lines.append("- `asset:hp` — HP logo (the runtime already draws it in the corner stamp; use only on title/closing slides)")
    return "\n".join(lines)


def _system() -> dict:
    return {"role": "system", "content": system_prompt()}


def _review() -> dict:
    return {"role": "system", "content": review_system_prompt()}


def _user(text: str, images: list[Path] | None = None, max_w: int | None = None, *, readable: bool | None = None) -> dict:
    if not images:
        return {"role": "user", "content": text}
    parts = [image_part(p, max_w, readable=readable) for p in images if p and p.exists()]
    return {"role": "user", "content": parts + [{"type": "text", "text": text}]}


# ------------------------------------------------------------------ content trimming
# Two callers: the plan pass (which never needs a full table to decide "this is a table slide") and the
# context-overflow retry (which is the difference between a dead slide and a slightly abridged one).
PLAN_MAX_LINES = 10       # body lines per text block shown to the planner
PLAN_MAX_TABLE_ROWS = 4   # a table's shape is clear from its header plus a few rows
PLAN_MAX_NOTES = 400      # chars of speaker notes
TRIM_MAX_TABLE_ROWS = 15  # generation retry after a context-length 400
TRIM_MAX_LINES = 24
TRIM_MAX_NOTES = 600


def _trim_rows(rows: list, keep: int, label: str) -> list:
    if len(rows) <= keep + 1:
        return rows
    head, body = rows[:1], rows[1:]
    return head + body[:keep] + [[f"… {len(body) - keep} more {label} omitted"] + [""] * max(0, len(rows[0]) - 1)]


def _trim_text(value: str, keep: int) -> str:
    return value if len(value) <= keep else value[:keep].rstrip() + f" … (+{len(value) - keep} chars)"


def trim_content(content: dict, *, max_lines: int, max_rows: int, max_notes: int, drop_charts: bool = False) -> dict:
    """A smaller copy of one slide's `for_prompt()` content. Never silently loses a *kind* of content:
    what is dropped is always replaced by a visible "… N more" marker so the model knows more exists."""
    out = dict(content)
    if out.get("text"):
        blocks = []
        for b in out["text"]:
            lines = b.get("lines") or []
            if len(lines) > max_lines:
                lines = lines[:max_lines] + [f"… {len(lines) - max_lines} more lines omitted"]
            blocks.append({**b, "lines": lines})
        out["text"] = blocks
    if out.get("tables"):
        out["tables"] = [_trim_rows(t, max_rows, "rows") for t in out["tables"]]
    if out.get("charts"):
        if drop_charts:
            out["charts"] = [{"title": c.get("title", ""), "categories": len(c.get("categories") or []),
                              "series": [s.get("name", "") for s in c.get("series") or []]} for c in out["charts"]]
        else:
            charts = []
            for c in out["charts"]:
                cats = c.get("categories") or []
                keep = max(max_rows, 8)
                cc = dict(c)
                if len(cats) > keep:
                    cc["categories"] = cats[:keep] + [f"… +{len(cats) - keep}"]
                    cc["series"] = [{**s, "values": (s.get("values") or [])[:keep]} for s in c.get("series") or []]
                charts.append(cc)
            out["charts"] = charts
    if out.get("speaker_notes"):
        out["speaker_notes"] = _trim_text(out["speaker_notes"], max_notes)
    return out


def plan_content(content: dict) -> dict:
    """What the planner sees. It picks a pattern and two ideas — it needs the shape of the content and its
    headline facts, never every row of a 60-row table."""
    return trim_content(content, max_lines=PLAN_MAX_LINES, max_rows=PLAN_MAX_TABLE_ROWS, max_notes=PLAN_MAX_NOTES,
                        drop_charts=True)


def trimmed_for_retry(content: dict) -> dict:
    """Used once, after the server refused the prompt as too long."""
    return trim_content(content, max_lines=TRIM_MAX_LINES, max_rows=TRIM_MAX_TABLE_ROWS, max_notes=TRIM_MAX_NOTES)


# ------------------------------------------------------------------ plan
def plan_messages(slides: list[dict], *, thumbs: dict[int, Path] | None = None, deck_summary: str = "",
                  batch_note: str = "", reference: str = "") -> list[dict]:
    """One planning batch.

    `thumbs` maps slide index -> 480px thumbnail. When present the user message becomes a parts list with each
    slide's picture immediately before its text, so the planner sees whether a slide is a diagram, a photo
    composition or a wall of bullets instead of inferring it from extracted text. ~250-300 image tokens each.
    `deck_summary` carries what earlier batches already decided, so a chunked plan stays one deck.
    """
    header = _fill(read("deck_plan.md"), DECK="{{__DECK__}}", DECK_SUMMARY=deck_summary or "(this is the first batch — you are setting it)",
                   BATCH_NOTE=batch_note,
                   REFERENCE=reference or "(none — the user added no reference documents; ignore `doc_facts`)")
    before, _, after = header.partition("{{__DECK__}}")
    if not thumbs:
        deck = "\n\n".join(f"### Slide {s['index']}\n{_dump(s['content'])}" for s in slides)
        return [_system(), _user(before + deck + after)]
    parts: list[dict] = [{"type": "text", "text": before}]
    for s in slides:
        parts.append({"type": "text", "text": f"### Slide {s['index']}"})
        p = thumbs.get(s["index"])
        if p and Path(p).exists():
            parts.append({"type": "text", "text": f"Rendered slide {s['index']} as it looks today:"})
            parts.append(image_part(Path(p), THUMB_MAX_W))
        parts.append({"type": "text", "text": _dump(s["content"])})
    parts.append({"type": "text", "text": after})
    return [_system(), {"role": "user", "content": parts}]


def plan_line(p: dict | None) -> str:
    if not p:
        return "(none)"
    return f"\"{p.get('headline', '')}\" ({p.get('pattern', '')})"


def deck_summary(brief: dict, planned: list[dict]) -> str:
    """The running summary handed to every planning batch after the first."""
    lines = [f"- Deck title: {brief.get('deck_title', '')}", f"- Audience: {brief.get('audience', '')}",
             f"- Tone: {brief.get('tone', '')}", f"- Narrative: {brief.get('narrative', '')}"]
    if planned:
        lines.append("- Already planned, in order (keep the vocabulary and headline style consistent, and do not "
                     "repeat a pattern on adjacent slides):")
        for p in planned[-18:]:
            lines.append(f"  {p.get('index')}. [{p.get('pattern', '')}] {p.get('eyebrow', '')} — \"{p.get('headline', '')}\"")
    return "\n".join(lines)


# ------------------------------------------------------------------ generate
def facts_block(ledger: list) -> str:
    """The fact ledger as creative direction, not as a cage.

    Two lists, because they ask for different things. `must_be_visible` is what the plan says this slide is
    *for* — those figures should be the hero treatment, the count-up, the thing the audience remembers.
    `must_survive` has to reach the slide or its notes but need not compete for attention.

    The values are fixed; nothing about their presentation is. That distinction is the whole point: a deck
    that reworded "$4.2M" into "several million" lost the fact, and a deck that pasted "$4.2M" into a bullet
    list kept it and wasted it.
    """
    if not ledger:
        return ""
    from .. import facts as _facts
    view = _facts.for_prompt(ledger)
    out = ["## Facts this slide asserts",
           "Every value below comes from the source and is **not yours to change** — not reworded, not rounded, "
           "not re-scaled, not merged. How each one is presented is entirely yours: hero number, count-up, chart, "
           "callout, table cell, whatever the design needs.", ""]
    if view["must_be_visible"]:
        out += ["**On the slide, prominently** — these carry the message:",
                *(f"- {x}" for x in view["must_be_visible"]), ""]
    if view["must_survive"]:
        out += ["**Present and legible, or in the speaker notes** — supporting detail:",
                *(f"- {x}" for x in view["must_survive"]), ""]
    out.append("Any figure you state that is not listed above must follow from these by arithmetic the audience "
               "could check (\"90s to 30s\" is honestly \"3x faster\"). Never introduce a statistic, date, customer "
               "or claim that is not here.")
    return "\n".join(out)


def generate_messages(*, variant: str, position: int, total: int, brief: dict, plan: dict, content: dict,
                      prev_plan: dict | None, next_plan: dict | None, source_png: Path | None, vision: bool,
                      verbatim: bool = False, design_log: str = "", avoid: str = "", ledger: list | None = None,
                      reference: str = "", doc_sources: list | None = None, library_source: str = "") -> list[dict]:
    plan_view = {k: plan.get(k) for k in ("role", "pattern", "eyebrow", "headline", "key_message", "theme") if plan.get(k) is not None}
    plan_view["idea"] = plan.get("idea_a" if variant == "A" else "idea_b", "")
    img_note = ""
    images = None
    if vision and source_png and source_png.exists():
        images = [source_png]
        img_note = ("The attached image is the ORIGINAL PowerPoint slide. Use it to understand content, grouping and emphasis. "
                    "Do not copy its visual style — restyle it in the HP language.")
    text = _fill(read("generate.md"), POSITION=f"{position} of {total}", VARIANT=variant, DECK_TITLE=brief.get("deck_title", ""),
                 AUDIENCE=brief.get("audience", ""), TONE=brief.get("tone", ""), NARRATIVE=brief.get("narrative", ""),
                 PREV=plan_line(prev_plan), NEXT=plan_line(next_plan), PLAN=_dump(plan_view), CONTENT=_dump(content),
                 ASSETS=assets_listing(content), IMAGE_NOTE=img_note, VARIANT_BRIEF=_variant_brief(variant),
                 COPY_RULE=VERBATIM_RULE if verbatim else "", FACTS=facts_block(ledger or []),
                 DESIGN_LOG=design_log or "(this is the first slide designed in this deck — you are setting the conventions)",
                 AVOID_NOTE=avoid, REFERENCE=reference_block(reference, doc_sources or [], library_source))
    return [_system(), _user(text, images)]


def reference_block(excerpts: str, doc_sources: list, library_source: str = "",
                    gate: str = "the facts list above already contains it") -> str:
    """Passages from the user's reference documents that bear on this slide. Background, not content: a figure
    from here may appear only if the facts list above already holds it (it then came in through the ledger).

    `library_source` is the citation of a slide inserted from the slide library (runner.library_citation): its
    whole ledger came from that library deck, so — like a document figure — it must be cited in `sources`. In the
    user message, like everything per-slide, so the system prefix stays byte-stable."""
    lib = ""
    if library_source:
        lib = ("## Where this slide comes from\n"
               "This slide is reused from the user's slide library, and its facts come from there. Cite it in "
               f"`sources` as: {library_source}" + (" (alongside any document below)." if doc_sources else "."))
    if not excerpts and not doc_sources:
        return lib
    out = ([lib, ""] if lib else []) + ["## Background from the user's reference documents",
           "Use this to sharpen the framing and the speaker notes. Do NOT put a figure from it on the slide unless",
           f"{gate}."]
    if doc_sources:
        out.append(f"Figures in the facts list that came from these documents must be cited in `sources`: "
                   f"{'; '.join(doc_sources)}.")
    if excerpts:
        out += ["", excerpts]
    return "\n".join(out)


def contrast_note(other_variant: str, structure: str) -> str:
    """Handed to a regenerated B when the first B came out structurally the same as A."""
    return ("## This must not repeat the other variant\n"
            f"Variant {other_variant} for this same slide was built like this:\n{structure}\n"
            "Your first attempt at this variant came out structurally the same, which makes the A/B choice "
            "meaningless. Use a genuinely different composition: change the grid (split vs. full-bleed vs. stacked "
            "bands), change what carries the message (cards vs. table vs. one hero number vs. an image), and change "
            "where the eye lands first. Same facts, same plan, different design.")


# ------------------------------------------------------------------ critic
_STATUS_LINE = {
    "present": "on the slide",
    "notes": "in the speaker notes only",
    "missing": "NOT FOUND on the slide or in its notes",
    "changed": "CHANGED",
}


def ledger_block(checks: list, invented: list) -> str:
    """The fact ledger as a worked checklist for the critic.

    Handing the critic a list to verify rather than a picture to search is the whole point. Asking a model to
    find missing numbers across two images is OCR plus a set difference done from memory, which is exactly the
    task where it answers "looks right"; asking it to confirm eleven rows that code has already ticked is a
    task it can actually do.

    So the code's answer leads, and the critic is asked only for what code cannot decide: whether a figure
    that *is* present is presented honestly, and whether an unlisted figure follows from the source or was
    made up.
    """
    if not checks and not invented:
        return ""
    out = ["## Fact check (already run against the source — confirm it, do not repeat it)"]
    for c in checks:
        f = c.fact
        tier = "KEY" if f.tier == "key" else "supporting"
        line = f"- [{tier}] {f.raw}" + (f" — {f.label}" if f.label and f.label != f.raw else "")
        line += f"  ->  {_STATUS_LINE.get(c.status, c.status)}"
        if c.status == "changed":
            line += f": {c.detail}"
        out.append(line)
    if invented:
        out += ["", "Figures on the slide that no source fact accounts for: " + ", ".join(invented[:8]) + ".",
                'Decide for each whether it follows from the source by arithmetic the audience could check '
                '("90s to 30s" is honestly "3x faster") or whether it was invented. An invented figure is a '
                'high-severity fidelity issue; a sound derivation is not an issue at all.']
    out += ["", "Your fidelity score must agree with this table. Judge what the table cannot: is each figure "
                "presented so the audience actually takes it in, and does the wording around it still mean what "
                "the source meant?"]
    return "\n".join(out)


def critic_messages(*, variant: str, plan: dict, content: dict, qa_findings: list[dict], shots: list[Path],
                    source_png: Path | None, ledger=None) -> list[dict]:
    imgs = list(shots)
    names = []
    for p in shots:
        names.append("the generated slide at step 0 (what appears first)" if p.name == "shot_0.png" else "the generated slide at its final step")
    if source_png and source_png.exists():
        imgs.append(source_png)
        names.append("the original PowerPoint slide")
    findings = "\n".join(f"- [{f['severity']}] {f['message']}" for f in qa_findings) or "- none"
    text = _fill(read("critic.md"), IMAGES="; ".join(f"image {i + 1}: {n}" for i, n in enumerate(names)), VARIANT=variant,
                 VARIANT_NAME=VARIANT_NAMES[variant], PLAN=_dump(plan), CONTENT=_dump(content), QA_FINDINGS=findings,
                 FACT_CHECK=ledger_block(getattr(ledger, "checks", None) or [], getattr(ledger, "invented", None) or []))
    # readable=True: the source goes at native width, not the 1024px JPEG the planner gets. Checking whether a
    # figure survived means reading the figure, and a dense source table is illegible once downscaled.
    return [_review(), _user(text, imgs, readable=True)]


def judge_messages(*, content: dict, reference_shot: Path, candidate_shot: Path, reference_steps: int,
                   candidate_steps: int, swapped: bool = False) -> list[dict]:
    """Eval judge (evals/run_eval.py). Same short review prefix as the critic — scoring, not authoring.

    `swapped` reverses the two images (and the sentence naming them) so the same pair can be judged in both
    orders and the position bias averaged out; see evals/run_eval.py::judge.
    """
    order = ("Images: image 1 = CANDIDATE (final step), image 2 = REFERENCE (final step)." if swapped else
             "Images: image 1 = REFERENCE (final step), image 2 = CANDIDATE (final step).")
    text = fill(task("judge.md", "compare a candidate slide to a reference slide"),
                IMAGE_ORDER=order, CONTENT=json.dumps(content, ensure_ascii=False),
                CANDIDATE_STEPS=candidate_steps, REFERENCE_STEPS=reference_steps)
    shots = [candidate_shot, reference_shot] if swapped else [reference_shot, candidate_shot]
    return [_review(), _user(text, shots)]


def ab_messages(*, plan: dict, content: dict, shot_a: Path, shot_b: Path, steps_a: int, steps_b: int,
                swapped: bool = False) -> list[dict]:
    """Pairwise A-vs-B on one slide, for the review UI's recommendation.

    Pointwise absolute scores out of an LLM judge are noisy, and `critic_min_score` is a threshold on that noise.
    Comparing the two renderings side by side asks a much easier question, and it is the question the user is
    actually being asked in the review view. The pointwise critic stays where it earns its keep — the repair loop,
    which needs `issues[].problem/fix`, not a ranking.

    `swapped` puts B first; the caller alternates it per slide so a whole deck cannot inherit one position bias.
    """
    first, second = ("B", "A") if swapped else ("A", "B")
    order = (f"Images: image 1 = variant {first} ({VARIANT_NAMES[first]}), "
             f"image 2 = variant {second} ({VARIANT_NAMES[second]}) — both at their final step.")
    text = fill(task("judge.md", "choose between two variants of the same slide"),
                IMAGE_ORDER=order, PLAN=_dump(plan), CONTENT=_dump(content),
                STEPS=f"variant A has {steps_a} step(s), variant B has {steps_b}")
    shots = [shot_b, shot_a] if swapped else [shot_a, shot_b]
    return [_review(), _user(text, shots)]


# ------------------------------------------------------------------ repair / revise
def spec_for_prompt(spec: SlideSpec, slide_id: str) -> str:
    s = spec.model_copy(deep=True)
    s.css = s.css.replace(f".s-{slide_id} ", "").replace(f".s-{slide_id}", ".slide-root")
    return to_tagged(s)


def repair_history(attempts: list[list[str]]) -> str:
    """One line per earlier repair attempt: which issue codes it was given.

    Without this the model cannot tell attempt 2 from attempt 1 and can oscillate between two broken layouts
    until qa_max_repairs runs out.
    """
    if not attempts:
        return ""
    lines = []
    for i, codes in enumerate(attempts, start=1):
        seen = ", ".join(dict.fromkeys(codes)) or "unspecified"
        lines.append(f"- Attempt {i} was asked to fix: {seen}")
    lines.append("If a code above appears again in the issues below, your previous fix did not work: do not repeat "
                 "it. Change the layout at a structural level (fewer items, a different grid, shorter copy) rather "
                 "than nudging the same numbers again.")
    return "\n".join(lines)


def repair_messages(*, variant: str, position: int, plan: dict, content: dict, spec: SlideSpec, slide_id: str, issues: list[str],
                    shot: Path | None, vision: bool, verbatim: bool = False, history: str = "") -> list[dict]:
    text = _fill(read("repair.md"), POSITION=position, VARIANT=variant, VARIANT_NAME=VARIANT_NAMES[variant],
                 ISSUES="\n".join(f"{i + 1}. {x}" for i, x in enumerate(issues)), PLAN=_dump(plan), CONTENT=_dump(content),
                 ASSETS=assets_listing(content), SPEC=spec_for_prompt(spec, slide_id),
                 HISTORY=history or "(this is the first repair of this slide)")
    if verbatim:
        text = VERBATIM_RULE + "\n\n" + text
    if vision and shot and shot.exists():
        text = "The attached image is how your previous spec rendered at its final step.\n\n" + text
        return [_system(), _user(text, [shot])]
    return [_system(), _user(text)]


def revise_messages(*, variant: str, position: int, plan: dict, content: dict, spec: SlideSpec, slide_id: str, comment: str,
                    other: SlideSpec | None, other_id: str | None, shot: Path | None, vision: bool,
                    verbatim: bool = False, reference: str = "", doc_sources: list | None = None) -> list[dict]:
    """`reference`: document passages chosen with the comment in mind, so "bring in the point from the whitepaper"
    has the whitepaper to draw on. A revision carries no facts list, so the gate on figures names what it does have."""
    other_note = ""
    if other is not None and other_id:
        other_lineage = "B" if variant == "A" else "A"
        other_note = (f"For reference, the other variant ({other_lineage}, {VARIANT_NAMES[other_lineage]}) looked like this — the comment "
                      f"may ask you to borrow from it:\n{spec_for_prompt(other, other_id)}")
    text = _fill(read("revise.md"), POSITION=position, VARIANT=variant, VARIANT_NAME=VARIANT_NAMES[variant], COMMENT=comment.strip(),
                 SPEC=spec_for_prompt(spec, slide_id), OTHER_NOTE=other_note, PLAN=_dump(plan), CONTENT=_dump(content),
                 ASSETS=assets_listing(content),
                 REFERENCE=reference_block(reference, doc_sources or [],
                                           gate="the source content, the starting spec or the presenter's comment already gives it"))
    if verbatim:
        text = VERBATIM_RULE + "\n\n" + text
    if vision and shot and shot.exists():
        text = "The attached image is the current rendering of the starting spec.\n\n" + text
        return [_system(), _user(text, [shot])]
    return [_system(), _user(text)]


def format_retry_message(error: str, attempt: int = 1) -> dict:
    """Re-ask for the same task in the required format.

    The previous reply is deliberately NOT echoed back: it was unusable by definition, and up to 1.5k tokens of
    it only dilutes the instruction that follows. The task is still in the first user message, unchanged, so the
    cached prefix and the whole brief survive the retry.
    """
    harder = ("" if attempt < 2 else
              " This is your last chance: write the smallest correct slide that satisfies the task rather than "
              "risking the format again.")
    return {"role": "user", "content":
            f"Your previous reply could not be used: {error}.\n"
            "Ignore it completely and answer the task in the first message again, this time with ONLY the four "
            "tagged sections, in this order and nothing else — no prose, no explanation, no markdown fence:\n"
            "<meta>…</meta>\n<html>…</html>\n<css>…</css>\n<script>…</script>\n"
            "Every tag must be opened and closed. <meta> must be a valid JSON object." + harder}
