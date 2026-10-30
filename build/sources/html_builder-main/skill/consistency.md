# Task: review the deck as a whole

Below is every slide of a finished deck, in order, with the words on it and the figures it states. Each slide
has already passed its own review; you are looking for what only shows up across slides. You are NOT redesigning.

## Deck
- Title: {{DECK_TITLE}}
- Audience: {{AUDIENCE}}
- Story: {{NARRATIVE}}

## Slides (use the handles S1, S2, … to refer to them)
{{DECK}}

## Look for
- **story**: a gap in the argument — a claim never supported, no clear ask or next step, a conclusion before its
  evidence, two slides making the same point.
- **numbers**: the same quantity stated differently on two slides (a total, a percentage, a date, a product name).
- **terms**: one thing called two names ("workstation" / "PC", "Z8 Fury" / "Z8 Fury G5") — pick one.
- **headlines**: headlines that break the deck's style (a topic label among assertions, a question among
  statements, wildly different lengths).
- **flow**: a slide in the wrong place, or a transition the audience cannot follow.

Report only real problems, most important first, at most 8. Each needs a concrete fix one slide can apply.

## Output
Return ONLY a JSON object, no prose, no fences:
{"issues": [{"slides": ["S3", "S7"], "kind": "story|numbers|terms|headlines|flow", "issue": str, "fix": str}]}
- `issue`: one sentence the user will read.
- `fix`: an instruction to the designer of the FIRST listed slide, written as a revision comment
  ("Call it 'Z8 Fury G5' as on slide 7, and ...").
- An empty list is a fine answer for a consistent deck.
