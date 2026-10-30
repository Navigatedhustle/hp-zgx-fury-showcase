"""The user's slide management: delete and restore, merge and unmerge, undo a split.

Testers wanted to combine two thin, related slides (8 and 17 of one deck), to throw one away, and to undo a
split the planner made when one slide would have done. Everything here is **reversible**, in the same spirit
as `content_edit` and the fact ledger: a converted slide is never destroyed, only taken out of the deck, so
"that was a mistake" is always one click.

- *Delete* a source slide → it leaves the deck (`plan.removed = "deleted"`) and can be restored. A slide the
  user made here (added, or merged) has no PowerPoint behind it, so deleting it really deletes it.
- *Merge* N slides → one new slide holding all of their content and the union of their fact ledgers; the
  originals leave the deck (`plan.removed = "merged"`) and come back on *unmerge*.
- *Merge the parts of one split slide* → that is *undo split*: the parts collapse back into part 0 with the
  whole ledger, and `plan.no_split` stops a re-plan from splitting it again.

Both kinds of removed slide keep their rows, so `runner.plan()` skips them and the UI lists them apart.
"""
from __future__ import annotations

import logging

from .. import facts
from ..ingest.pptx_parse import Paragraph, SlideContent, TextBlock
from ..store import db
from ..store.db import Project, Slide
from . import mock, prompts, reference
from . import runner as r

log = logging.getLogger(__name__)

MAX_MERGE = 4  # past this the content cannot fit one slide's density limits, and the merge would lose facts


class DeckOpError(ValueError):
    """A refused slide operation. The message is safe to show the user."""


def _composed(pid: str) -> bool:
    p = db.get(Project, pid)
    return p is not None and (p.source or "pptx") == "composed"


def _made_here(s: Slide) -> bool:
    """No PowerPoint behind it: added by the user, or merged from other slides."""
    plan = s.plan or {}
    return bool(plan.get(r.ADDED_KEY) or plan.get(r.MERGED_FROM_KEY))


def _live(pid: str) -> list[Slide]:
    return [s for s in db.slides_of(pid) if not r.is_removed(s)]


def _order_with_removed_last(pid: str, live: list[Slide]) -> list[Slide]:
    ids = {s.id for s in live}
    return live + [s for s in db.slides_of(pid) if s.id not in ids]


def _set_plan(slide_id: str, **changes) -> None:
    s = db.get(Slide, slide_id)
    plan = {**(s.plan or {})}
    for k, v in changes.items():
        if v is None:
            plan.pop(k, None)
        else:
            plan[k] = v
    r.set_slide(slide_id, plan=plan)


# ------------------------------------------------------------------ delete / restore
def delete_slide(slide_id: str) -> None:
    s = db.get(Slide, slide_id)
    if s is None:
        return
    live = _live(s.project_id)
    if len(live) <= 1 and not r.is_removed(s):
        raise DeckOpError("A deck needs at least one slide.")
    if _composed(s.project_id) or _made_here(s):
        # Deleting a merged slide must not strand its originals out of sight: they go to the removed list,
        # from where they can be restored one by one.
        for oid in (s.plan or {}).get(r.MERGED_FROM_KEY) or []:
            if db.get(Slide, oid):
                _set_plan(oid, **{r.REMOVED_KEY: "deleted", r.MERGED_INTO_KEY: None})
        r.remove_slide(slide_id)
        return
    r.set_slide(slide_id, included=False)
    _set_plan(slide_id, **{r.REMOVED_KEY: "deleted"})
    r.reposition(_order_with_removed_last(s.project_id, [x for x in live if x.id != slide_id]))


def restore_slide(slide_id: str, after: int | None = None) -> Slide:
    s = db.get(Slide, slide_id)
    if s is None:
        raise DeckOpError("No such slide.")
    if (s.plan or {}).get(r.MERGED_INTO_KEY):
        raise DeckOpError("This slide was merged into another — unmerge that one to bring it back.")
    _set_plan(slide_id, **{r.REMOVED_KEY: None})
    r.set_slide(slide_id, included=True)
    live = [x for x in _live(s.project_id) if x.id != slide_id]
    at = len(live) if after is None else max(0, min(after, len(live)))
    r.reposition(_order_with_removed_last(s.project_id, live[:at] + [db.get(Slide, slide_id)] + live[at:]))
    return db.get(Slide, slide_id)


# ------------------------------------------------------------------ merge
def _merge_content(rows: list[Slide], index: int) -> SlideContent:
    """One slide's worth of every row's content, in deck order. The first slide's title leads; the others'
    titles become bold lead-ins, so the planner still sees where each part came from."""
    parts = [r.merged_content(x) for x in rows]
    out = SlideContent(index=index, source_index=0, title=parts[0].title)
    seen_imgs: set[str] = set()
    for i, c in enumerate(parts):
        body = [t for t in c.texts if t.kind != "title"]
        if i and c.title:
            body = [TextBlock(kind="body", paragraphs=[Paragraph(text=c.title, bold=True)])] + body
        out.texts += [t.model_copy(update={"box": []}) for t in body]
        out.tables += c.tables
        out.charts += c.charts
        for img in c.images:
            if img.key not in seen_imgs:
                seen_imgs.add(img.key)
                out.images.append(img)
        out.warnings += c.warnings
    out.notes = "\n\n".join(c.notes.strip() for c in parts if c.notes.strip())
    return out


def _merge_facts(rows: list[Slide]) -> list[facts.Fact]:
    out: list[facts.Fact] = []
    ids: set[str] = set()
    raws: set[str] = set()
    for x in rows:
        for f in r.slide_facts(x):
            if f.id in ids or f.raw.lower() in raws:
                continue
            ids.add(f.id)
            raws.add(f.raw.lower())
            out.append(f)
    return out


def _label(s: Slide) -> str:
    total = (s.plan or {}).get(r.PART_KEY, [0, 1])[1]
    labels = (s.plan or {}).get(r.MERGED_LABELS_KEY)
    if labels:
        return "+".join(labels)
    return f"{s.index}{'abc'[s.part]}" if total > 1 and s.part < 3 else str(s.index)


def merge_slides(project_id: str, slide_ids: list[str]) -> Slide:
    rows = [db.get(Slide, i) for i in dict.fromkeys(slide_ids)]
    if any(x is None or x.project_id != project_id for x in rows):
        raise DeckOpError("Those slides aren't all in this deck.")
    if len(rows) < 2:
        raise DeckOpError("Pick at least two slides to merge.")
    if any(r.is_removed(x) for x in rows):
        raise DeckOpError("A slide that is out of the deck can't be merged — restore it first.")
    rows.sort(key=lambda x: x.position)
    if not _composed(project_id) and len({x.index for x in rows}) == 1 and not any(_made_here(x) for x in rows):
        return undo_split(rows)
    if len(rows) > MAX_MERGE:
        raise DeckOpError(f"Merge at most {MAX_MERGE} slides at once — more than that can't fit on one slide.")

    idx = r.next_index(project_id)
    content = _merge_content(rows, idx)
    first = rows[0]
    plan = {k: v for k, v in (first.plan or {}).items() if k not in r.STICKY_PLAN_KEYS and k != r.PART_KEY}
    plan.update({r.MERGED_FROM_KEY: [x.id for x in rows], r.MERGED_LABELS_KEY: [_label(x) for x in rows],
                 r.NO_SPLIT_KEY: True, r.PART_KEY: [0, 1]})
    # The ledger keeps every merged slide's facts, so it must keep citing where library ones came from. Not as
    # `library_source`: the merged slide is none of those library slides, and has no single original picture.
    lib = [s for x in rows for s in r.library_sources(x.plan)]
    if lib:
        plan[r.LIBRARY_SOURCES_KEY] = lib
    new = db.save(Slide(project_id=project_id, index=idx, part=0, position=first.position, content=content.model_dump(),
                        facts=facts.dump(_merge_facts(rows)), plan=plan, status="pending"))
    for x in rows:
        r.set_slide(x.id, included=False)
        _set_plan(x.id, **{r.REMOVED_KEY: "merged", r.MERGED_INTO_KEY: new.id})
    live = [x for x in _live(project_id) if x.id != new.id]
    at = next((i for i, x in enumerate(live) if x.position >= first.position), len(live))
    r.reposition(_order_with_removed_last(project_id, live[:at] + [new] + live[at:]))
    return db.get(Slide, new.id)


def undo_split(parts: list[Slide]) -> Slide:
    """Collapse the parts of one split source slide back into one. Part 0 keeps its row (and its versions)
    and takes the whole ledger back; `no_split` keeps a re-plan from splitting it again."""
    every = sorted([x for x in db.slides_of(parts[0].project_id) if x.index == parts[0].index and not r.is_removed(x)],
                   key=lambda x: x.part)
    keep, rest = every[0], every[1:]
    ledger = _merge_facts(every) if all(x.facts_edit is None for x in every) else None
    fields: dict = {"status": "pending" if not keep.approved_version_id else keep.status}
    if ledger is not None:
        fields["facts"] = facts.dump(ledger)
    r.set_slide(keep.id, **fields)
    _set_plan(keep.id, **{r.NO_SPLIT_KEY: True, r.PART_KEY: [0, 1]})
    for x in rest:
        r.remove_slide(x.id)
    return db.get(Slide, keep.id)


def unmerge(slide_id: str) -> list[Slide]:
    s = db.get(Slide, slide_id)
    if s is None:
        raise DeckOpError("No such slide.")
    ids = (s.plan or {}).get(r.MERGED_FROM_KEY) or []
    if not ids:
        raise DeckOpError("This slide wasn't made by a merge.")
    back = [x for x in (db.get(Slide, i) for i in ids) if x is not None]
    for x in back:
        _set_plan(x.id, **{r.REMOVED_KEY: None, r.MERGED_INTO_KEY: None})
        r.set_slide(x.id, included=True)
    pid, pos = s.project_id, s.position
    db.delete_slide(slide_id)
    live = [x for x in _live(pid) if x.id not in {b.id for b in back}]
    at = next((i for i, x in enumerate(live) if x.position >= pos), len(live))
    r.reposition(_order_with_removed_last(pid, live[:at] + [db.get(Slide, b.id) for b in back] + live[at:]))
    return [db.get(Slide, b.id) for b in back]


# ------------------------------------------------------------------ planning one slide
MERGED_NOTE = ("The user merged the slides below into ONE slide, because on their own each was too thin. Plan it as a "
               "single slide: return exactly one entry for it, never split it, and choose a pattern that carries all "
               "of its content together. Keep the deck's existing vocabulary (see 'Deck so far').")
ADDED_NOTE = ("The user added this slide to an existing deck. Plan exactly one entry for it, consistent with the deck "
              "so far (see 'Deck so far').")


USER_PLAN_FIELDS = ("headline", "pattern", "key_message")


async def plan_slides(project_id: str, slide_ids: list[str], extra_note: str = "") -> None:
    """Plan just these slides, in the context of the deck's existing plan. Used after a merge, and for a slide
    the user added — re-planning the whole deck for one slide would throw away every other slide's plan."""
    from ..config import settings

    proj = await r._db(db.get, Project, project_id)
    if proj is None:
        return
    await r.aset_project(project_id, stage_note="Planning the new slide")
    try:
        brief = {"deck_title": proj.deck_title, **(proj.brief or {})}
        for sid in slide_ids:
            s = await r._db(db.get, Slide, sid)
            if s is None:
                continue
            item = {"index": s.index, "content": r._content(s)}
            fallback = mock.plan([item])["slides"][0]
            got: dict = {}
            if not settings().llm_mock:
                others = [x.plan for x in await r._db(_live, project_id) if x.id != sid and x.plan]
                note = MERGED_NOTE if (s.plan or {}).get(r.MERGED_FROM_KEY) else ADDED_NOTE
                if extra_note:
                    note += "\n\n" + extra_note
                data = await r._plan_call([{"index": s.index, "content": prompts.plan_content(item["content"])}],
                                          thumbs={}, summary=prompts.deck_summary(brief, others), note=note,
                                          reference=await r._db(reference.planner_reference, project_id))
                entries = [e for e in (data or {}).get("slides", []) if isinstance(e, dict)]
                got = {k: v for k, v in (entries[0] if entries else {}).items() if v not in (None, "")}
            plan = fallback | got
            if (s.plan or {}).get(r.ADDED_KEY):
                # On a slide the user added, anything already in its plan was typed by them in the plan view.
                plan.update({k: v for k, v in (s.plan or {}).items() if k in USER_PLAN_FIELDS and v})
            plan.update({k: v for k, v in (s.plan or {}).items() if k in r.STICKY_PLAN_KEYS})
            plan[r.PART_KEY] = [0, 1]
            plan[r.HEURISTIC_KEY] = "llm" if got else "heuristic"
            fields: dict = {"plan": plan, "included": True, "status": "pending"}
            if s.facts_edit is None:
                fields["facts"] = facts.dump(r._tier_facts(facts.load(s.facts), plan.get("key_facts") or []))
            await r.aset_slide(sid, **fields)
    finally:
        await r.aset_project(project_id, stage_note="")
        r.emit(project_id, "slides")


# ------------------------------------------------------------------ condense
# "Cut this 15-slide deck to 7 for a 10-minute slot." The model proposes; code checks every rule it can
# (coverage, the target, must-keep, group size) and falls back to a deterministic plan rather than apply a
# broken one; the user reviews the proposal before anything changes; and applying it is undoable in one step,
# because it is made of the same reversible merges as everything else in this module.
APPENDIX_KEY = r.APPENDIX_KEY        # Slide.plan: a backup slide, shown after the main deck
PROPOSAL_KEY = "condense_proposal"   # Project.brief: the proposal the user is reviewing
UNDO_KEY = "condense_undo"           # Project.brief: what "Undo condense" puts back
CONDENSE_TOKENS = 3000


def _main_deck(project_id: str) -> list[Slide]:
    return [s for s in _live(project_id) if not (s.plan or {}).get(APPENDIX_KEY)]


def _handles(live: list[Slide]) -> dict[str, Slide]:
    """S1, S2, … — labels can repeat ("new"), and a handle must name exactly one slide."""
    return {f"S{i}": s for i, s in enumerate(live, 1)}


def _slide_brief(s: Slide) -> dict:
    plan = s.plan or {}
    return {"headline": plan.get("headline", ""), "message": plan.get("key_message", ""),
            "pattern": plan.get("pattern", ""),
            "key_facts": [f.raw for f in r.slide_facts(s) if f.tier == "key"][:6],
            "content": prompts.plan_content(r.content_for_prompt(s))}


def condense_messages(live: list[Slide], target: int, keep: list[str], guidance: str, ref: str) -> list[dict]:
    from ..skillpack import read

    hs = _handles(live)
    back = {s.id: h for h, s in hs.items()}
    deck = "\n\n".join(f"### {h} (slide {_label(s)})\n{prompts._dump(_slide_brief(s))}" for h, s in hs.items())
    text = prompts.fill(read("condense.md"), TARGET=target, COUNT=len(live), MAX_MERGE=MAX_MERGE,
                        GUIDANCE=guidance.strip() or "(none — keep what carries the deck's argument)",
                        KEEP=", ".join(back[i] for i in keep if i in back) or "(none)",
                        REFERENCE=ref or "(none)", DECK=deck)
    return [prompts._system(), prompts._user(text)]


def validate_proposal(data, live: list[Slide], target: int, keep: list[str]) -> tuple[dict | None, str]:
    """(the proposal in slide ids, "") when every rule holds; (None, what broke) otherwise."""
    hs = _handles(live)
    if not isinstance(data, dict) or not isinstance(data.get("main"), list):
        return None, "the reply has no `main` list"
    seen: list[str] = []
    main = []
    for e in data["main"]:
        handles = [str(h).strip() for h in (e.get("from") or [])] if isinstance(e, dict) else []
        if not handles:
            return None, "a `main` entry has an empty `from`"
        if any(h not in hs for h in handles):
            return None, f"unknown handle in {handles}"
        if len(handles) > MAX_MERGE:
            return None, f"{handles} combines more than {MAX_MERGE} slides"
        seen += handles
        main.append({"ids": [hs[h].id for h in handles], "headline": str(e.get("headline", ""))[:80],
                     "why": str(e.get("why", ""))[:240]})
    app = [str(h).strip() for h in data.get("appendix") or []]
    if any(h not in hs for h in app):
        return None, "unknown handle in `appendix`"
    seen += app
    if len(seen) != len(set(seen)):
        return None, "a slide appears more than once"
    missing = [h for h in hs if h not in seen]
    if missing:
        return None, f"these slides appear nowhere: {', '.join(missing)}"
    if not 1 <= len(main) <= target:
        return None, f"`main` has {len(main)} entries; it must have 1 to {target}"
    in_main = {i for m in main for i in m["ids"]}
    lost = [h for h, s in hs.items() if s.id in keep and s.id not in in_main]
    if lost:
        return None, f"must-stay slides are not in `main`: {', '.join(lost)}"
    return {"main": main, "appendix": [hs[h].id for h in app], "why": str(data.get("why", ""))[:400]}, ""


def fallback_proposal(live: list[Slide], target: int, keep: list[str]) -> dict:
    """No model, or a model that broke the rules twice: keep the must-stay slides, then those carrying the most key
    facts, in deck order; the rest become backup. No merges — combining slides needs judgement code doesn't have."""
    def weight(s: Slide) -> tuple:
        return (s.id in keep, sum(1 for f in r.slide_facts(s) if f.tier == "key"), -s.position)
    chosen = {s.id for s in live if s.id in keep}
    for s in sorted(live, key=weight, reverse=True):
        if len(chosen) >= target:
            break
        chosen.add(s.id)
    return {"main": [{"ids": [s.id], "headline": (s.plan or {}).get("headline", ""), "why": "Kept."}
                     for s in live if s.id in chosen],
            "appendix": [s.id for s in live if s.id not in chosen],
            "why": "Kept the slides you marked and those carrying the most key figures; the rest are backup."}


async def propose_condense(project_id: str, target: int, keep: list[str], guidance: str) -> dict:
    from ..config import settings
    from ..llm import client as llm
    from ..spec import extract_json

    live = await r._db(_main_deck, project_id)
    target = max(1, min(target, len(live)))
    await r.aset_project(project_id, stage_note=f"Proposing a {target}-slide version")
    # "offline": no model was asked (mock mode); "fallback": the model was asked and could not keep the rules.
    source, proposal = ("offline" if settings().llm_mock else "fallback"), None
    try:
        if not settings().llm_mock:
            ref = await r._db(reference.planner_reference, project_id)
            msgs = await r._db(condense_messages, live, target, keep, guidance, ref)
            for _ in range(2):
                reply = await llm.chat(msgs, temperature=0.3, max_tokens=CONDENSE_TOKENS,
                                       thinking=settings().thinking_plan, stage="condense")
                proposal, problem = validate_proposal(extract_json(reply.text), live, target, keep)
                if proposal:
                    source = "llm"
                    break
                log.warning("condense proposal rejected: %s", problem)
                msgs = msgs + [{"role": "assistant", "content": reply.text},
                               prompts._user(f"That breaks a rule: {problem}. Return the corrected JSON only.")]
    except Exception as e:  # noqa: BLE001 — a failed call still leaves the user a usable proposal
        log.warning("condense call failed: %s", e)
    if proposal is None:
        proposal = fallback_proposal(live, target, keep)
    proposal.update(target=target, guidance=guidance, keep=keep, source=source)
    p = await r._db(db.get, Project, project_id)
    await r.aset_project(project_id, stage_note="", brief={**(p.brief or {}), PROPOSAL_KEY: proposal})
    r.emit(project_id, "slides")
    return proposal


def apply_condense(project_id: str, proposal: dict) -> list[str]:
    """Make the deck match `proposal`. Returns the ids of the slides the merges created (to be planned next)."""
    live = _live(project_id)
    main_deck = [s.id for s in live if not (s.plan or {}).get(APPENDIX_KEY)]
    main = proposal.get("main") or []
    ids = [i for m in main for i in m.get("ids", [])] + list(proposal.get("appendix") or [])
    if not main or sorted(ids) != sorted(main_deck):
        raise DeckOpError("The deck has changed since this proposal was made — propose again.")
    undo = {"order": [s.id for s in live], "appendix": [s.id for s in live if (s.plan or {}).get(APPENDIX_KEY)],
            "created": []}
    main_ids = []
    for m in main:
        if len(m["ids"]) > 1:
            new = merge_slides(project_id, m["ids"])
            if m.get("headline"):
                _set_plan(new.id, headline=m["headline"])
            undo["created"].append(new.id)
            main_ids.append(new.id)
        else:
            main_ids.append(m["ids"][0])
    for sid in proposal.get("appendix") or []:
        _set_plan(sid, **{APPENDIX_KEY: True})
    order = [db.get(Slide, i) for i in main_ids + undo["appendix"] + list(proposal.get("appendix") or [])]
    r.reposition(_order_with_removed_last(project_id, [s for s in order if s is not None]))
    p = db.get(Project, project_id)
    brief = {k: v for k, v in (p.brief or {}).items() if k != PROPOSAL_KEY}
    r.set_project(project_id, brief={**brief, UNDO_KEY: undo})
    return undo["created"]


def undo_condense(project_id: str) -> None:
    p = db.get(Project, project_id)
    undo = (p.brief or {}).get(UNDO_KEY) if p else None
    if not undo:
        raise DeckOpError("There is no condense to undo.")
    for sid in undo.get("created", []):
        if db.get(Slide, sid) is not None:
            unmerge(sid)
    before = set(undo.get("appendix", []))
    for s in db.slides_of(project_id):
        if (s.plan or {}).get(APPENDIX_KEY) and s.id not in before:
            _set_plan(s.id, **{APPENDIX_KEY: None})
    order = [x for x in (db.get(Slide, i) for i in undo.get("order", [])) if x is not None and not r.is_removed(x)]
    known = {x.id for x in order}
    r.reposition(_order_with_removed_last(project_id, order + [s for s in _live(project_id) if s.id not in known]))
    p = db.get(Project, project_id)
    r.set_project(project_id, brief={k: v for k, v in (p.brief or {}).items() if k != UNDO_KEY})


# A deterministic divider between the main deck and its backup slides — no model, nothing to QA.
APPENDIX_SPEC = """<meta>{"pattern":"section","title":"Appendix","steps":0,"theme":"navy","notes":["Backup slides follow."]}</meta>
<html><div class="eyebrow">Backup</div><h1 class="title">Appendix</h1></html>
<css></css>
<script></script>"""
