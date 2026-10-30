"""Grounding: how the ledger reaches the planner, the generator and the critic.

tests/test_facts.py covers what the ledger *is*. This covers the wiring — that the planner's tiers land
on the right facts, that the generator is told which values it may not change, and that the critic is
handed a worked checklist and a legible picture of the source instead of being asked to find things.
"""
from pathlib import Path

import pytest
from app import facts as F
from app.pipeline import prompts
from app.pipeline.runner import _tier_facts

SRC = {"title": "Q3 results",
       "text": [{"lines": ["Revenue grew to $4.2M", "Margin held at 40%", "12,500 seats on Z8 Fury G5"]}]}


def _ledger():
    return F.extract(SRC)


# ---------------------------------------------------------------- tiering
def test_the_planner_promotes_a_fact_it_names_exactly():
    fs = _tier_facts(_ledger(), ["$4.2M"])
    assert [f.tier for f in fs if f.raw == "$4.2M"] == ["key"]
    assert all(f.tier == "supporting" for f in fs if f.raw != "$4.2M")


def test_a_fact_named_inside_a_phrase_still_matches():
    """The planner writes free strings, so "$4.2M in revenue" has to find the "$4.2M" fact."""
    fs = _tier_facts(_ledger(), ["$4.2M in revenue this year"])
    assert any(f.tier == "key" and f.raw == "$4.2M" for f in fs)


def test_a_name_the_planner_paraphrases_still_matches():
    fs = _tier_facts(_ledger(), ["the Z8 Fury G5 workstation"])
    assert any(f.tier == "key" and "Z8 Fury" in f.raw for f in fs)


def test_a_fact_the_planner_invents_promotes_nothing():
    """The safe direction: the LLM may promote what the deterministic pass found, never add a requirement."""
    fs = _tier_facts(_ledger(), ["$9.9B in bookings", "Acme Corporation"])
    assert all(f.tier == "supporting" for f in fs)
    assert not any("9.9" in f.raw for f in fs)


def test_no_key_facts_leaves_every_tier_alone():
    fs = _ledger()
    for f in fs:
        f.tier = "key"
    assert all(f.tier == "key" for f in _tier_facts(fs, []))


def test_tiering_is_exclusive_so_a_replan_can_demote():
    fs = _tier_facts(_tier_facts(_ledger(), ["$4.2M"]), ["40%"])
    assert [f.raw for f in fs if f.tier == "key"] == ["40%"]


# ---------------------------------------------------------------- the generator's brief
def test_the_generator_is_told_values_are_fixed_and_framing_is_free():
    block = prompts.facts_block(_tier_facts(_ledger(), ["$4.2M"]))
    assert "not yours to change" in block
    assert "entirely yours" in block, "the brief must not read as a verbatim rule"
    assert "$4.2M" in block


def test_key_and_supporting_facts_are_asked_for_differently():
    block = prompts.facts_block(_tier_facts(_ledger(), ["$4.2M"]))
    visible, _, survive = block.partition("**Present and legible")
    assert "$4.2M" in visible and "$4.2M" not in survive
    assert "40%" in survive


def test_an_empty_ledger_adds_nothing_to_the_prompt():
    assert prompts.facts_block([]) == ""


def test_the_generate_prompt_carries_the_ledger(tmp_path):
    msgs = prompts.generate_messages(
        variant="B", position=1, total=3, brief={"deck_title": "T"}, plan={"pattern": "cards"}, content=SRC,
        prev_plan=None, next_plan=None, source_png=None, vision=False, ledger=_tier_facts(_ledger(), ["$4.2M"]))
    text = msgs[-1]["content"]
    assert "Facts this slide asserts" in text and "$4.2M" in text


# ---------------------------------------------------------------- the critic's worksheet
def _checks(rendered, notes=""):
    return F.ledger(_tier_facts(_ledger(), ["$4.2M"]), rendered, notes)


def test_the_critic_is_handed_the_answer_not_the_search():
    block = prompts.ledger_block(_checks("Revenue grew to $4.2M").checks, [])
    assert "confirm it, do not repeat it" in block
    assert "[KEY] $4.2M" in block and "on the slide" in block


def test_a_changed_value_reaches_the_critic_as_changed():
    lg = _checks("Revenue grew to $5.1M this year")
    block = prompts.ledger_block(lg.checks, lg.invented)
    assert "CHANGED" in block and "4.2" in block and "5.1" in block


def test_a_key_fact_hidden_in_the_notes_is_marked_as_such():
    block = prompts.ledger_block(_checks("Revenue grew", "Revenue grew to $4.2M").checks, [])
    assert "in the speaker notes only" in block


def test_the_critic_decides_whether_an_unlisted_figure_was_derived_or_invented():
    """Code cannot tell "3x faster" computed from the source apart from a fabrication; the critic can."""
    block = prompts.ledger_block([], ["3x", "92%"])
    assert "3x" in block and "arithmetic the audience could check" in block


def test_an_empty_ledger_adds_no_checklist():
    assert prompts.ledger_block([], []) == ""


def test_the_critic_sees_the_source_at_full_resolution(monkeypatch, tmp_path):
    """A dense source table downscaled to 1024px JPEG is illegible, and the critic then answers
    confidently about figures it cannot actually see."""
    seen: list[tuple[str, bool | None]] = []
    monkeypatch.setattr(prompts, "image_part",
                        lambda p, max_w=None, readable=None: seen.append((Path(p).name, readable)) or {"type": "image_url"})
    shot = tmp_path / "shot_final.png"
    source = tmp_path / "003.png"
    for f in (shot, source):
        f.write_bytes(b"x")
    prompts.critic_messages(variant="A", plan={}, content=SRC, qa_findings=[], shots=[shot], source_png=source)
    assert seen and all(readable is True for _, readable in seen), seen
    assert {"shot_final.png", "003.png"} == {name for name, _ in seen}


# ---------------------------------------------------------------- correcting the ledger
@pytest.fixture
def client():
    from app import main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _slide_with_facts(client):
    """A project whose first slide has a ledger, through the real API."""
    import shutil

    from app.store import db
    from app.store.db import Project
    from conftest import DECKS

    p = db.save(Project(name="ledger", filename="t.pptx"))
    shutil.copy2(DECKS / "hp_wolf_print_security.pptx", db.project_dir(p.id) / "source.pptx")
    import asyncio

    from app.pipeline import runner
    asyncio.run(runner.ingest(p.id))
    slides = client.get(f"/api/projects/{p.id}").json()["slides"]
    return p.id, next(s for s in slides if s["facts"])


def test_the_plan_view_is_told_what_the_slide_must_carry(client):
    _, s = _slide_with_facts(client)
    assert s["facts"] and s["facts_edited"] is False
    assert {"id", "raw", "tier", "origin", "kind"} <= set(s["facts"][0])
    assert "label" in s and "part" in s and "parts" in s


def test_a_fact_can_be_retiered(client):
    pid, s = _slide_with_facts(client)
    fid = s["facts"][0]["id"]
    client.patch(f"/api/slides/{s['id']}", json={"facts": [{"id": fid, "tier": "key"}]})
    after = next(x for x in client.get(f"/api/projects/{pid}").json()["slides"] if x["id"] == s["id"])
    assert after["facts_edited"] is True
    assert next(f for f in after["facts"] if f["id"] == fid)["tier"] == "key"


def test_a_fact_can_be_struck_out(client):
    """A source slide can carry a figure that is a document reference, not a claim about the world."""
    pid, s = _slide_with_facts(client)
    fid = s["facts"][0]["id"]
    client.patch(f"/api/slides/{s['id']}", json={"facts": [{"id": fid, "drop": True}]})
    after = next(x for x in client.get(f"/api/projects/{pid}").json()["slides"] if x["id"] == s["id"])
    assert len(after["facts"]) == len(s["facts"]) - 1
    assert not any(f["id"] == fid for f in after["facts"])


def test_corrections_can_be_reverted(client):
    pid, s = _slide_with_facts(client)
    client.patch(f"/api/slides/{s['id']}", json={"facts": [{"id": s["facts"][0]["id"], "drop": True}]})
    client.patch(f"/api/slides/{s['id']}", json={"reset_facts": True})
    after = next(x for x in client.get(f"/api/projects/{pid}").json()["slides"] if x["id"] == s["id"])
    assert after["facts_edited"] is False and len(after["facts"]) == len(s["facts"])


def test_a_corrected_ledger_survives_a_replan(client):
    """The planner re-tiers on every plan; a correction the user made by hand must outrank that."""
    import asyncio

    from app.pipeline import runner
    from app.store import db

    pid, s = _slide_with_facts(client)
    client.patch(f"/api/slides/{s['id']}", json={"facts": [{"id": s["facts"][0]["id"], "drop": True}]})
    asyncio.run(runner.plan(pid))
    after = db.get(db.Slide, s["id"])
    assert after.facts_edit is not None
    assert len(runner.slide_facts(after)) == len(s["facts"]) - 1


def test_editing_the_copy_re_extracts_the_ledger(client):
    """The copy decides what the slide claims, so a ledger from the old copy would hold the design to
    figures the user has just removed."""
    pid, s = _slide_with_facts(client)
    client.patch(f"/api/slides/{s['id']}", json={"content": {"blocks": ["Margin held at 40%"]}})
    after = next(x for x in client.get(f"/api/projects/{pid}").json()["slides"] if x["id"] == s["id"])
    raws = {f["raw"] for f in after["facts"]}
    assert "40%" in raws
