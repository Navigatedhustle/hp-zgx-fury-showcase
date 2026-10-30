# Task: condense the deck

The user needs this deck shorter: **at most {{TARGET}} main slides** (it has {{COUNT}} now). Usually this is
because their slot is short. You decide which slides survive, which are combined, and which move to an appendix
of backup slides after the main deck. You are NOT writing slides now — a planner and a designer do that next.

## The user's guidance
{{GUIDANCE}}

## Slides the user said must stay in the main deck
{{KEEP}}

## Reference documents (background)
{{REFERENCE}}

## The deck, in order
Each slide has a handle (S1, S2, …). Use the handles, nothing else, to refer to slides.
{{DECK}}

## How to decide
- Serve the guidance first: who the audience is and what they must leave with decides what stays.
- Keep the story whole: an opening, the problem, the answer, the proof, the ask. Cutting the ask or the proof to
  keep a second agenda slide is wrong.
- **Combine** slides that make the same point or carry parts of one argument (a problem slide and its numbers;
  two feature slides about one product) into one main slide — at most {{MAX_MERGE}} slides per group. Combine only
  what one slide can really carry; a combined slide still has one message.
- Everything that does not make the main deck goes to `appendix`, in deck order. Nothing is deleted.
- Every must-stay slide is in `main`, alone or in a group.
- Keep the deck's order: groups and single slides appear in `main` in the order the story needs, usually the
  original order.
- Title and closing slides stay if the guidance leaves room; they are never combined with content slides.

## Output
Return ONLY a JSON object, no prose, no fences:
{"main": [{"from": ["S3", "S5"], "headline": str, "why": str}], "appendix": ["S7", "S9"], "why": str}
- `main`: at most {{TARGET}} entries. `from` lists the handles combined into that slide (one handle = kept as is).
- `headline`: the assertion the resulting slide will make (≤ 55 characters).
- `why`: one short sentence for the user, per entry and for the whole plan.
- Every handle S1…S{{COUNT}} appears **exactly once** across `main` and `appendix`.
