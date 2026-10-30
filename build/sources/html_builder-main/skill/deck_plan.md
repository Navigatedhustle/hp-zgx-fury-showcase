# Task: plan the deck

You are the creative director. Below is the extracted content of a PowerPoint deck, slide by slide, and — where a
render was available — a thumbnail of each slide as it looks today. You are NOT writing HTML now.

**Read the pictures, not just the text.** The extracted text cannot tell you whether a slide is a boxes-and-arrows
diagram, a photo composition, a dense table, a single hero number or a wall of bullets, and that shape decides the
pattern. A slide whose picture is a process diagram is a `process` or `timeline`, never `cards`, however its text
reads. Where a thumbnail and the extracted text disagree, the picture wins for *shape* and the text wins for *facts*.

{{BATCH_NOTE}}

## Deck so far
{{DECK_SUMMARY}}

## Reference documents
The user added these documents as background — digests, not the full text. Use them to understand what the deck is
for, who it is for and which points deserve the emphasis; they are context, never slides of their own. A long
document also lists its sections (`D1.S3`), each with notes on what it says.
{{REFERENCE}}

## Deck content
{{DECK}}

## What to decide
1. **Audience and tone** — infer from the content (e.g. "semiconductor fab executives; confident, evidence-led").
2. **Narrative** — 2–3 sentences: the arc the deck makes (problem → cost → solution → proof → action, or whatever fits).
3. **Splitting a dense slide — rarely.** One source slide becomes one designed slide. Splitting makes the deck
   longer, and a presenter notices a slide they did not write; so split ONLY when a hard limit cannot be met any
   other way: a table of more than 8 rows, more than 6 parallel items, or more key figures than one slide can
   show. Long prose, many bullets or two related points are NOT reasons to split — tighten the copy, regroup it
   and move detail to the speaker notes. When you must split, emit **two entries with the same `index`**, in
   reading order, each a complete slide with its own headline, pattern and facts. Never emit more than 3 entries
   for one source slide, and split at most one slide in eight.

   When you split, every figure and name in the source must be claimed by exactly one part's `key_facts` or
   clearly belong to one part's content. A fact no part claims is a fact the deck has lost.

4. **Per slide (per entry):**
   - `role`: title, agenda, section, hook, problem, solution, evidence, comparison, process, roadmap, team, quote, cta, closing, appendix, other.
   - `pattern`: one from the pattern catalogue (title, agenda, section, stat-hook, cards, problem-solution, specs, chart, compare, calculator, explorer, process, timeline, roadmap, quote, table, references, closing, image-focus).
     Choose by the SHAPE of the content: numbers that multiply → calculator; series → chart; A vs B → compare; ordered stages → process/timeline; 3–6 parallel items → cards; a diagram or a dominant photo → image-focus or process, not cards.
   - `eyebrow`: 2–5 word context label.
   - `headline`: an assertion (≤ 55 characters) that states the slide's message, using only facts in the slide. Not a topic.
   - `key_message`: one sentence — what the audience must remember.
   - `idea_a`: the ONE interaction for the cinematic variant (≤ 30 words). **Name the scene it uses** from the
     catalogue — `compare`, `calculator`, `chartFocus`, `explorer`, `timeline` or `build` — and say what the
     control does and what changes on screen, specific to THIS slide's content. Choose by what the content is:
     two states of the world → `compare`; a number that depends on the audience's own numbers → `calculator`;
     one series carrying the point → `chartFocus`; parallel items with detail behind them → `explorer`; an
     ordered process → `timeline`; a sequence of claims → `build`. Example: "compare: toggle between today's
     fleet and the Z8 rollout; the three cost figures count down."
   - `idea_b`: the layout for the refined variant (≤ 25 words). Also specific: name the composition, not "a clean grid".
   - `key_facts`: the 2–4 figures or names that carry this slide's message, **copied from the source exactly**
     as it writes them ("$4.2M", "40%", "Z8 Fury G5") — not reworded, not rounded, not invented. These are the
     facts the finished slide must show the audience; everything else in the source may sit in the speaker
     notes instead. Choose the ones `key_message` depends on. Empty list if the slide asserts no figures.
   - `doc_facts`: optional — at most 2 figures or names from the **reference documents** (not the slide) that make
     this slide's message stronger, copied character for character from a digest's FIGURES list. Only when the slide
     is about exactly that point; never to fill space. A figure you did not copy exactly is discarded. A section's
     FIGURES count as much as the digest's. A short statement with no figure in it ("ISO 27001 Type II certified
     across all regions") may be quoted the same way, when the slide's message rests on it. Where the documents
     disagree (listed at the end of the reference block), follow the instruction given there.
   - `doc_refs`: optional — at most 3 handles of the document sections this slide draws on (`"D1.S3"`, or `"D1"` for
     a document that lists no sections). The designer is then shown passages from those sections. Name a section
     only when its notes are about this slide's point; leave the list empty otherwise.
   - `theme`: light for most slides; navy for agenda/section; dark for closing or photo slides. At most ~20% non-light.
   - `include`: false only for slides that are empty, duplicate, or pure "thank you" filler already covered by another slide.
5. Keep the deck consistent: same eyebrow vocabulary, parallel headline style, no two adjacent slides with the same pattern unless the content demands it.
6. **Thin, related slides.** When a slide carries very little (a heading and one or two lines) and another slide
   in the deck covers the same subject — even far away, e.g. slide 8 and slide 17 — set `merge_with` on the
   earlier one to the other slide's `index`. It is a suggestion the user accepts or ignores; still plan both
   slides normally. Omit `merge_with` (or leave it empty) otherwise, and never suggest merging a title, agenda,
   section or closing slide.
7. `idea_a` and `idea_b` must differ from slide to slide. Two slides with the same idea means one of them was not planned.
   Two parts of the same split slide must differ from each other too, and must not repeat each other's content.

## Output
Return ONLY a JSON object, no prose, no fences:
{"deck_title": str, "audience": str, "tone": str, "narrative": str,
 "slides": [{"index": int, "role": str, "pattern": str, "eyebrow": str, "headline": str, "key_message": str,
             "idea_a": str, "idea_b": str, "theme": str, "include": bool, "key_facts": [str],
             "merge_with": [int]  (optional), "doc_facts": [str]  (optional), "doc_refs": [str]  (optional)}]}
There must be **at least one entry per input slide**, using the same `index` values, in order. Give a slide two
or three consecutive entries with the same `index` only to split it as described above; every input slide must
appear at least once.
