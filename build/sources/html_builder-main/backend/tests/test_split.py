"""Splitting one dense source slide into two or three designed slides.

The density limits (~170 words, 6 cards, 8 table rows) and "keep every fact" cannot both be met by a
source slide that carries more than one slide's worth of content. The model used to resolve that
contradiction by dropping facts. Splitting removes the contradiction instead, so the thing these tests
protect is that no fact falls down the gap between the parts.
"""
import pytest
from app import facts as F
from app.pipeline.runner import MAX_SLIDE_PARTS, _split_facts

SRC = {"title": "Regional results",
       "text": [{"lines": ["EMEA revenue grew to $4.2M", "APAC revenue grew to $6.8M",
                           "Margin held at 40%", "12,500 seats on Z8 Fury G5"]}]}


def _ledger():
    return F.extract(SRC)


def _ids(groups):
    return [sorted(f.id for f in g) for g in groups]


# ---------------------------------------------------------------- the invariant
def test_every_fact_lands_on_exactly_one_part():
    """The failure splitting exists to prevent: a fact that belongs to neither half."""
    ledger = _ledger()
    groups = _split_facts(ledger, [{"key_facts": ["$4.2M"], "headline": "EMEA"},
                                   {"key_facts": ["$6.8M"], "headline": "APAC"}])
    placed = [f.id for g in groups for f in g]
    assert sorted(placed) == sorted(f.id for f in ledger)
    assert len(placed) == len(set(placed)), "a fact may not be on two parts"


def test_a_fact_no_part_claims_is_still_placed():
    """The planner forgetting to claim a figure must not be how the deck loses it."""
    groups = _split_facts(_ledger(), [{"key_facts": [], "headline": "EMEA"},
                                      {"key_facts": [], "headline": "APAC"}])
    assert sum(len(g) for g in groups) == len(_ledger())


def test_an_unclaimed_fact_goes_to_the_part_that_talks_about_it():
    groups = _split_facts(_ledger(), [{"key_facts": [], "headline": "EMEA revenue", "key_message": "EMEA grew"},
                                      {"key_facts": ["$6.8M"], "headline": "APAC", "key_message": "APAC grew"}])
    emea = next(f for g in groups for f in g if f.raw == "$4.2M")
    assert emea in groups[0]


def test_a_claimed_fact_is_key_on_its_own_part_only():
    groups = _split_facts(_ledger(), [{"key_facts": ["$4.2M"], "headline": "EMEA"},
                                      {"key_facts": ["$6.8M"], "headline": "APAC"}])
    a = next(f for f in groups[0] if f.raw == "$4.2M")
    b = next(f for f in groups[1] if f.raw == "$6.8M")
    assert a.tier == "key" and b.tier == "key"
    assert not any(f.raw == "$4.2M" for f in groups[1])


def test_two_parts_claiming_the_same_fact_do_not_duplicate_it():
    groups = _split_facts(_ledger(), [{"key_facts": ["$4.2M"], "headline": "One"},
                                      {"key_facts": ["$4.2M"], "headline": "Two"}])
    hits = [f for g in groups for f in g if f.raw == "$4.2M"]
    assert len(hits) == 1 and hits[0] in groups[0], "first claim wins, and it is claimed only once"


# ---------------------------------------------------------------- the unsplit case
def test_a_single_part_behaves_exactly_as_before():
    groups = _split_facts(_ledger(), [{"key_facts": ["40%"]}])
    assert len(groups) == 1 and len(groups[0]) == len(_ledger())
    assert [f.tier for f in groups[0] if f.raw == "40%"] == ["key"]


def test_no_parts_at_all_returns_the_ledger_untouched():
    ledger = _ledger()
    assert _split_facts(ledger, []) == [ledger]


# ---------------------------------------------------------------- three-way
def test_three_parts_still_place_everything():
    groups = _split_facts(_ledger(), [{"key_facts": ["$4.2M"], "headline": "EMEA"},
                                      {"key_facts": ["$6.8M"], "headline": "APAC"},
                                      {"key_facts": ["40%"], "headline": "Margin"}])
    assert len(groups) == 3
    assert sum(len(g) for g in groups) == len(_ledger())


def test_the_cap_matches_what_the_planner_was_told():
    """skill/deck_plan.md names the same number; a mismatch silently truncates a legal plan."""
    from app.skillpack import read
    assert "more than 3 entries" in read("deck_plan.md")
    assert MAX_SLIDE_PARTS == 3


# ---------------------------------------------------------------- labelling
@pytest.mark.parametrize("part, parts, want", [(0, 1, "4"), (0, 2, "4a"), (1, 2, "4b"), (2, 3, "4c")])
def test_a_split_slide_is_labelled_so_the_user_can_see_it(part, parts, want):
    from app.main import slide_label
    from app.pipeline.runner import PART_KEY
    from app.store.db import Slide
    s = Slide(project_id="p", index=4, part=part, position=1, plan={PART_KEY: [part, parts]})
    assert slide_label(s) == want


# ---------------------------------------------------------------- through the real plan writer
def _plan_with(monkeypatch, entries_for):
    """Run the planner against a fake reply. `entries_for(index)` returns that slide's plan entries."""
    import asyncio
    import shutil

    from app.config import settings
    from app.pipeline import runner
    from app.store import db
    from app.store.db import Project
    from conftest import DECKS

    async def go():
        p = db.save(Project(name="split", filename="t.pptx"))
        shutil.copy2(DECKS / "hp_wolf_print_security.pptx", db.project_dir(p.id) / "source.pptx")
        await runner.ingest(p.id)
        indexes = [s.index for s in db.slides_of(p.id)]

        async def fake_call(batch, **kw):
            return {"deck_title": "Split", "audience": "a", "tone": "t", "narrative": "n",
                    "slides": [e for b in batch for e in entries_for(b["index"])]}

        monkeypatch.setattr(runner, "_plan_call", fake_call)
        monkeypatch.setattr(runner.llm, "vision_enabled", lambda: asyncio.sleep(0, result=False))
        monkeypatch.setenv("LLM_MOCK", "false")
        settings.cache_clear()
        try:
            await runner.plan(p.id)
        finally:
            monkeypatch.setenv("LLM_MOCK", "true")
            settings.cache_clear()
        return p.id, indexes

    return asyncio.run(go())


def _entry(index, **kw):
    base = {"index": index, "role": "evidence", "pattern": "cards", "eyebrow": "e", "headline": f"h{index}",
            "key_message": "m", "idea_a": "a", "idea_b": "b", "theme": "light", "include": True, "key_facts": []}
    return {**base, **kw}


def test_a_split_creates_a_second_slide_sharing_the_source_render(monkeypatch):
    from app.store import db

    split_on = 2
    pid, indexes = _plan_with(monkeypatch, lambda i: (
        [_entry(i, headline="first half"), _entry(i, headline="second half")] if i == split_on else [_entry(i)]))
    slides = db.slides_of(pid)
    parts = [s for s in slides if s.index == split_on]
    assert len(parts) == 2, "the planner asked for two parts"
    assert [s.part for s in parts] == [0, 1]
    assert [s.plan["headline"] for s in parts] == ["first half", "second half"]
    # Both halves came from one PowerPoint slide, so they share its render and its parsed content.
    assert parts[0].content == parts[1].content
    assert len(slides) == len(indexes) + 1


def test_positions_stay_contiguous_and_ordered_across_a_split(monkeypatch):
    from app.store import db

    pid, _ = _plan_with(monkeypatch, lambda i: (
        [_entry(i), _entry(i)] if i == 2 else [_entry(i)]))
    slides = db.slides_of(pid)
    assert [s.position for s in slides] == list(range(1, len(slides) + 1))
    assert [(s.index, s.part) for s in slides] == sorted((s.index, s.part) for s in slides)


def test_replanning_with_fewer_parts_removes_the_orphan(monkeypatch):
    from app.store import db

    pid, indexes = _plan_with(monkeypatch, lambda i: ([_entry(i), _entry(i)] if i == 2 else [_entry(i)]))
    assert len(db.slides_of(pid)) == len(indexes) + 1

    import asyncio

    from app.config import settings
    from app.pipeline import runner

    async def fake_call(batch, **kw):
        return {"deck_title": "Split", "audience": "a", "tone": "t", "narrative": "n",
                "slides": [_entry(b["index"]) for b in batch]}

    monkeypatch.setattr(runner, "_plan_call", fake_call)
    monkeypatch.setattr(runner.llm, "vision_enabled", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    try:
        asyncio.run(runner.plan(pid))
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    assert len(db.slides_of(pid)) == len(indexes), "the second part is gone, not orphaned"
    assert all(s.part == 0 for s in db.slides_of(pid))


def test_the_cap_truncates_a_planner_that_asks_for_too_many(monkeypatch):
    from app.store import db

    pid, _ = _plan_with(monkeypatch, lambda i: ([_entry(i)] * 6 if i == 2 else [_entry(i)]))
    assert len([s for s in db.slides_of(pid) if s.index == 2]) == MAX_SLIDE_PARTS
