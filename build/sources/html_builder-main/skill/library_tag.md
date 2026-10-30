# Task: catalogue one slide for the slide library

A colleague will search a personal library of finished slides for this one later. Describe it so they find it:
what it claims, what kind of slide it is, what it is about, and the names on it. You are NOT judging its design.

## Deck it comes from
{{DECK}}

## The slide
{{IMAGE_NOTE}}
```json
{{CONTENT}}
```

## Tag vocabulary (slug — label), by facet
{{VOCAB}}

## Rules
- `summary`: at most 40 words, one or two sentences stating what the slide *claims or decides*, with its key
  figures as written ("Z8 Fury cuts render time 42% versus the prior generation; pilot customers ask for 200 units
  in Q3."). Never "This slide shows…", never a list of headings. A title or divider slide: say what the deck or
  section is about.
- `slide_type`: the one that best fits — {{SLIDE_TYPES}}.
- `topic_tags`: 1 to 4 slugs from the vocabulary, only for what is *central* to this slide — the subject a
  colleague would search for. A word that merely appears is not a topic. Fewer is better than loose.
- `entities`: the named things on the slide — products, customers, partners, technologies, metrics, people,
  teams — with the name exactly as written on the slide (keep model numbers and casing). At most 8. Types:
  {{ENTITY_TYPES}}. No generic nouns ("customers", "the cloud").
- `new_tag_suggestions`: at most 2 short topic names (1–3 words) for a central subject the vocabulary truly
  lacks. Usually empty. Never a synonym of a vocabulary tag, never a product or customer name.

## Output
Return ONLY a JSON object, no prose, no fences:
{"summary": str, "slide_type": str, "topic_tags": [slug], "entities": [{"name": str, "type": str}],
 "new_tag_suggestions": [str]}
