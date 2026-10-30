# Task: draft the content of a deck

You are writing the **content** of a presentation, not designing it. No HTML, no layout, no colours — those
come later, from the same skill, once a human has read and corrected what you write here.

## The brief
{{BRIEF}}

## Material to work from
{{SOURCE}}

## What to write

Draft about {{COUNT}} slides. Each one is a title, the lines that belong on it, and what the presenter says.

- **title** — an assertion, not a topic. "Adoption tripled after the toolkit launched", never "Adoption".
  Sentence case, under 55 characters, and true given the material.
- **content** — the lines that belong on the slide, one per array entry. Short: a slide carries at most
  five bullets or six cards, so write what fits. Indent a sub-point with two leading spaces. Wrap a line
  in `**` to mark it as the emphasis of that slide. No markdown otherwise.
- **notes** — what the presenter actually says, in two or three sentences. This is where detail that does
  not fit on the slide belongs.

## Rules

**Invent nothing.** Where the brief or the material gives a figure, a name, a date or a claim, use it exactly
as written — not reworded, not rounded, not re-scaled. Where they do not, write the slide without one rather
than supplying a plausible number. A deck built on invented figures is worse than a short one: every figure
here becomes a fact the finished slide is held to, and one you made up is one the presenter will be asked
about in the room.

Where the material is thin, say less. Ten honest slides beat twenty padded ones.

**Give the deck an arc.** Open by naming the problem or the opportunity, build the case in the middle, close
on what you want the audience to do. Cover the ground once — two slides making the same point means one of
them was not needed.

**Take the angle you are given.** When the brief has an `angle` ("Executive pitch", "Technical deep-dive",
"Financial case"), it decides what the deck selects from the material and how far it goes into it: an
executive pitch leads with the outcome and the ask and leaves mechanism to the notes; a technical deep-dive
shows how it works and what was measured; a financial case follows the money. The facts are the same —
which of them make the slide is not.

**One idea per slide.** If a slide needs three sentences of body copy to make sense, it is two slides.

Include a title slide first and a closing slide last. Do not write an agenda unless the deck is long enough
to need one (twelve slides or more).

## Output

Return ONLY a JSON object, no prose, no fences:
{"deck_title": str, "audience": str, "tone": str, "narrative": str,
 "slides": [{"title": str, "content": [str], "notes": str}]}

`audience`, `tone` and `narrative` restate the brief in the form the rest of the pipeline uses — keep what the
brief already says and fill in only what it left out. `narrative` is two or three sentences naming the arc.
