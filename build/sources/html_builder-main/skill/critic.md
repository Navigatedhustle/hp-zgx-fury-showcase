# Task: review a rendered slide

Images attached: {{IMAGES}}

## What the slide was meant to be
- Variant: {{VARIANT}} ({{VARIANT_NAME}})
- Plan: {{PLAN}}
- Source content: {{CONTENT}}

## Automated checks already found
{{QA_FINDINGS}}

{{FACT_CHECK}}

## Rubric

Work down the tree. Score the six **leaves** 0–10 using the anchors in your brief, then roll each branch up as the
**lowest** leaf under it — a branch is only as good as its weakest part, because that is what the audience sees.

**1. Intention — does this slide do the job it was planned to do?**
  - `fidelity` — the fact check above is the ground truth for *what* survived; score what it cannot judge.
    A KEY fact that reached only the notes, or did not survive at all, is high severity — it was the slide's
    message. A changed value is always high severity. Beyond the table: a figure that is technically present
    but set so small or so far from its label that the audience will not take it in has not really survived,
    and wording that no longer means what the source meant is a fidelity failure even when every digit matches.
  - `hierarchy` — eyebrow → assertion title → body reads in one glance; exactly one focal point; the headline
    states the plan's message rather than naming a topic; density within the limits.

**2. Static quality — does the still frame look like HP designed it?**
  - `layout` — nothing clipped, overflowing or overlapping; balanced use of the 1448 × 772 box; a clear grid; no
    awkward empty regions and no crowded corner; the bottom-right stamp area is clear.
  - `brand` — white/navy, HP blue as the single accent, red/green only where they carry meaning, Archivo +
    mono labels, clean bordered cards; no off-brand colours, emoji, or gradients on text.
  - `craft` — type sizes, alignment, spacing, contrast and image treatment look professionally designed; no text
    shrunk to fit; consistent rhythm between repeated elements.

**3. Dynamic behaviour — does it work as the variant it claims to be?**
  - `interaction` — variant A: the steps tell the story in order and the control is meaningful and still live at
    the end; variant B: calm, sensible reveals that read perfectly as a printed page. Score how well it fits
    **its own** variant brief, not how much movement it has.

## Output
Return ONLY JSON, no prose:
{"scores": {"layout": n, "hierarchy": n, "brand": n, "fidelity": n, "craft": n, "interaction": n},
 "branches": {"intention": n, "static_quality": n, "dynamic_behavior": n},
 "issues": [{"severity": "high|medium|low", "area": "layout|hierarchy|brand|fidelity|craft|interaction", "problem": "what is wrong, where", "fix": "specific change to make"}],
 "verdict": "pass|fix"}

`scores` must contain exactly those six keys and nothing else. (The code reads that key list straight out of the
`"scores": {…}` line above — `app/skillpack.py::criteria()` — so changing the rubric here changes the scoring,
the pass threshold and the guided-decoding schema with it. Keep it on one line, keys quoted.)
Each `branches` value is the minimum of its leaves:
intention = min(fidelity, hierarchy) · static_quality = min(layout, brand, craft) · dynamic_behavior = interaction.

Rules: be specific ("the 4th card's text is clipped at the bottom — reduce body copy to one sentence or use grid-3"),
list at most 6 issues, most severe first. "pass" only if every leaf score ≥ 7 and there is no high-severity issue.
