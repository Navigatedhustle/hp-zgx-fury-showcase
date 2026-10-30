# Task: compare a candidate slide to a reference slide

You are judging an automated slide designer against a reference built by an expert for the same PowerPoint slide.
{{IMAGE_ORDER}}

Source content both were built from:
{{CONTENT}}

Judge the CANDIDATE relative to the REFERENCE on: layout quality, visual hierarchy, HP brand fit, faithfulness to the
source content, craft (typography, spacing, alignment), and how well any interaction serves the message
(the candidate's step count: {{CANDIDATE_STEPS}}; reference: {{REFERENCE_STEPS}}).

Judge what is in the pictures, not where they sit in this message. Which image came first says nothing about quality.

Return ONLY JSON:
{"relative_quality": n, "better": "reference|candidate|tie", "gaps": ["specific shortfall", "..."]}
`relative_quality` is 0–100: 100 means the candidate is as good as or better than the reference; 90 means a small but
visible gap; 70 means clearly weaker; 40 means broken or off-brand.

# Task: choose between two variants of the same slide

Two designs of the SAME slide, built from the same source content and the same plan, for a presenter to choose
between. Variant A is meant to be cinematic and highly interactive; variant B refined, with minimal interaction.
Neither is the "correct" answer and neither wins for being busier or for being simpler — pick the one that lands
this slide's message better in front of an audience.

{{IMAGE_ORDER}}

## The slide
- Plan: {{PLAN}}
- Source content: {{CONTENT}}
- Steps: {{STEPS}}

## How to choose
Compare the two directly, in this order of importance:
1. **Fidelity** — a variant that drops, invents or alters a number, name or fact loses, whatever else it does well.
2. **Static quality** — clipping, overflow, overlap, crowding, off-brand colour or shrunken type lose outright.
3. **Hierarchy** — which one states the plan's message in one glance, with a single focal point?
4. **Craft** — typography, spacing, alignment, rhythm between repeated elements.
5. **Fit to its own brief** — judge A as a cinematic variant and B as a refined one, not against each other's brief.

Judge only what is in the pictures. The order the images appear in this message carries no information: it is
alternated deliberately between slides.

## Output
Return ONLY JSON, no prose:
{"winner": "A|B|tie", "confidence": n, "reason": "one sentence naming the deciding difference"}
`confidence` is 0–100: 100 means one variant is plainly better, 50 means it was close, and use "tie" with a low
confidence when they are genuinely equivalent rather than inventing a separation.
