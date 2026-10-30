"""Decks written here rather than converted from a PowerPoint.

The claim this module has to keep honest is that there is only *one* pipeline: a composed deck produces
the same `SlideContent` the parser does, and everything from planning onwards — the planner, the fact
ledger, the critic, the exports — runs unchanged and unaware. So most of these tests are about the seam,
not about composing: what a converted deck's routes refuse, and what a composed deck's content looks like
by the time the planner sees it.
"""
import asyncio

import pytest
from app import compose, main
from app.ingest.pptx_parse import SlideContent
from app.pipeline import runner
from app.store import db
from app.store.db import Project, Slide
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def deck(client):
    """A blank composed project with three slides."""
    p = client.post("/api/projects/blank", json={"name": "Composed", "slides": 3}).json()
    return p["id"]


# ---------------------------------------------------------------- creating
def test_a_blank_deck_starts_ready_with_slides_to_type_into(client):
    p = client.post("/api/projects/blank", json={"name": "Q3 review", "slides": 2}).json()
    assert p["source"] == "composed"
    assert p["status"] == "ready", "there is nothing to ingest, so nothing to wait for"
    assert len(p["slides"]) == 2
    assert p["slides"][0]["content"] == {"title": ""} or not p["slides"][0]["content"].get("text")


def test_a_composed_deck_needs_no_file(client):
    p = client.post("/api/projects/blank", json={"name": "No file"}).json()
    assert p["filename"] == ""
    assert db.get(Project, p["id"]).source == "composed"


def test_an_uploaded_deck_is_still_marked_as_converted(client):
    p = db.save(Project(name="conv", filename="t.pptx"))
    assert (db.get(Project, p.id).source or "pptx") == "pptx"


# ---------------------------------------------------------------- typing
def test_typing_into_a_slide_becomes_the_content_the_planner_reads(client, deck):
    sid = client.get(f"/api/projects/{deck}").json()["slides"][0]["id"]
    client.post(f"/api/slides/{sid}/write", json={
        "title": "Adoption tripled after the toolkit launched",
        "body": "Seats grew from 4,200 to 12,500\n  Across eleven regions\n**The toolkit paid for itself**",
        "notes": "Open on the number, then the regions.",
    })
    s = db.get(Slide, sid)
    content = runner.content_for_prompt(s)
    assert content["title"] == "Adoption tripled after the toolkit launched"
    lines = content["text"][0]["lines"]
    assert lines[0] == "Seats grew from 4,200 to 12,500"
    assert lines[1] == "  Across eleven regions", "two leading spaces indent, as the plan view documents"
    assert lines[2] == "**The toolkit paid for itself**", "** marks emphasis, as the plan view documents"
    assert content["speaker_notes"].startswith("Open on the number")


def test_typed_content_is_the_source_not_an_overlay(client, deck):
    """A converted deck keeps `content_edit` so the PowerPoint stays recoverable. Here there is no
    PowerPoint to recover, so the typing IS the content."""
    sid = client.get(f"/api/projects/{deck}").json()["slides"][0]["id"]
    client.post(f"/api/slides/{sid}/write", json={"title": "Typed"})
    s = db.get(Slide, sid)
    assert s.content["title"] == "Typed"
    assert s.content_edit is None


def test_typing_extracts_a_fact_ledger(client, deck):
    """The whole grounding stack has to work on a composed deck too — the facts just come from typing."""
    sid = client.get(f"/api/projects/{deck}").json()["slides"][0]["id"]
    out = client.post(f"/api/slides/{sid}/write",
                      json={"title": "Revenue", "body": "Revenue grew to $4.2M at 40% margin"}).json()
    raws = {f["raw"] for f in out["facts"]}
    assert "$4.2M" in raws and "40%" in raws


def test_retyping_keeps_the_tiers_the_planner_chose(client, deck):
    sid = client.get(f"/api/projects/{deck}").json()["slides"][0]["id"]
    client.post(f"/api/slides/{sid}/write", json={"body": "Revenue grew to $4.2M"})
    s = db.get(Slide, sid)
    fs = runner.slide_facts(s)
    fs[0].tier = "key"
    db.update(Slide, sid, facts=[f.model_dump() for f in fs])
    client.post(f"/api/slides/{sid}/write", json={"body": "Revenue grew to $4.2M in the first year"})
    assert [f.tier for f in runner.slide_facts(db.get(Slide, sid)) if f.raw == "$4.2M"] == ["key"]


def test_a_converted_deck_refuses_the_write_route(client):
    """Its copy edits go through content_edit so the PowerPoint stays recoverable."""
    p = db.save(Project(name="conv", filename="t.pptx"))
    s = db.save(Slide(project_id=p.id, index=1, position=1, content=compose.blank(1, "x").model_dump()))
    r = client.post(f"/api/slides/{s.id}/write", json={"title": "no"})
    assert r.status_code == 400 and "content editor" in r.json()["detail"]


# ---------------------------------------------------------------- structure
def test_a_slide_can_be_added_at_the_end(client, deck):
    client.post(f"/api/projects/{deck}/slides", json={})
    slides = client.get(f"/api/projects/{deck}").json()["slides"]
    assert len(slides) == 4
    assert [s["position"] for s in slides] == [1, 2, 3, 4]


def test_a_slide_can_be_inserted_in_the_middle(client, deck):
    client.post(f"/api/projects/{deck}/slides", json={"after": 1})
    slides = db.slides_of(deck)
    assert [s.position for s in slides] == [1, 2, 3, 4]
    assert [s.index for s in slides] == [1, 2, 3, 4], "index and position never disagree on a composed deck"


def test_a_slide_can_be_deleted_and_the_rest_renumber(client, deck):
    slides = client.get(f"/api/projects/{deck}").json()["slides"]
    client.delete(f"/api/slides/{slides[0]['id']}")
    after = db.slides_of(deck)
    assert len(after) == 2 and [s.position for s in after] == [1, 2] and [s.index for s in after] == [1, 2]


def test_the_last_slide_cannot_be_deleted(client):
    p = client.post("/api/projects/blank", json={"name": "One", "slides": 1}).json()
    r = client.delete(f"/api/slides/{p['slides'][0]['id']}")
    assert r.status_code == 400


def test_a_converted_decks_slide_is_taken_out_not_destroyed(client):
    """The PowerPoint stays recoverable: a deleted source slide leaves the deck and can be restored."""
    p = db.save(Project(name="conv", filename="t.pptx"))
    for i in (1, 2):
        db.save(Slide(project_id=p.id, index=i, position=i, content=compose.blank(i).model_dump()))
    first = db.slides_of(p.id)[0].id
    assert client.delete(f"/api/slides/{first}").status_code == 200
    row = db.get(Slide, first)
    assert row is not None and not row.included and row.plan["removed"] == "deleted"


def test_a_slide_can_be_moved(client, deck):
    ids = [s["id"] for s in client.get(f"/api/projects/{deck}").json()["slides"]]
    client.post(f"/api/slides/{ids[2]}/move", json={"to": 0})
    assert [s.id for s in db.slides_of(deck)] == [ids[2], ids[0], ids[1]]
    assert [s.position for s in db.slides_of(deck)] == [1, 2, 3]


# ---------------------------------------------------------------- the outline draft
def test_the_outline_fills_the_deck_and_its_brief(client, deck):
    r = client.post(f"/api/projects/{deck}/outline", json={"about": "Why we should standardise on Z8", "slides": 6})
    assert r.status_code == 200
    _settle(deck)
    p = client.get(f"/api/projects/{deck}").json()
    assert len(p["slides"]) == 6
    assert p["deck_title"] and p["brief"].get("narrative")
    assert p["status"] == "ready"


def test_the_outline_replaces_whatever_was_there(client, deck):
    before = {s["id"] for s in client.get(f"/api/projects/{deck}").json()["slides"]}
    client.post(f"/api/projects/{deck}/outline", json={"slides": 4})
    _settle(deck)
    after = {s["id"] for s in client.get(f"/api/projects/{deck}").json()["slides"]}
    assert not (before & after), "a draft is a replacement, not an append"


def test_the_outline_is_refused_for_a_converted_deck(client):
    p = db.save(Project(name="conv", filename="t.pptx"))
    r = client.post(f"/api/projects/{p.id}/outline", json={})
    assert r.status_code == 400


def test_a_drafted_deck_carries_fact_ledgers(client, deck):
    client.post(f"/api/projects/{deck}/outline", json={"slides": 4})
    _settle(deck)
    for s in db.slides_of(deck):
        assert isinstance(s.facts, list), "every drafted slide is checkable like any other"


def _settle(pid: str, tries: int = 200) -> None:
    """Wait for the background outline job. It is spawned onto the app's loop, so poll the row."""
    import time
    for _ in range(tries):
        p = db.get(Project, pid)
        if p.status == "ready" and not runner.jobs.busy(pid):
            return
        time.sleep(0.05)


# ---------------------------------------------------------------- the seam
def test_outline_slides_are_the_same_shape_the_parser_produces():
    data = {"slides": [{"title": "A", "content": ["one", "  two"], "notes": "n"},
                       {"title": "", "content": [], "notes": "skipped"}]}
    out = compose.slides_from_outline(data)
    assert len(out) == 1, "a slide with neither title nor content is not a slide"
    assert isinstance(out[0], SlideContent)
    assert out[0].for_prompt()["text"][0]["lines"] == ["one", "  two"]


def test_an_unreadable_outline_entry_is_skipped_not_guessed_at():
    assert compose.slides_from_outline({"slides": ["nonsense", None, 7, {}]}) == []


def test_the_outline_is_capped():
    data = {"slides": [{"title": f"S{i}", "content": ["x"], "notes": ""} for i in range(100)]}
    assert len(compose.slides_from_outline(data)) <= compose.MAX_SLIDES


def test_the_planner_runs_on_a_composed_deck_unchanged(client, deck):
    """The point of the whole design: one pipeline. No source render, no ingest, same planner."""
    sid = db.slides_of(deck)[0].id
    client.post(f"/api/slides/{sid}/write", json={"title": "Costs fell", "body": "Spend fell to $2.8M"})
    asyncio.run(runner.plan(deck))
    for s in db.slides_of(deck):
        assert s.plan.get("pattern"), "every slide came back with a design plan"
    assert db.get(Project, deck).status == "ready"


def test_a_composed_slide_has_no_source_render_and_nothing_assumes_one(client, deck):
    s = db.slides_of(deck)[0]
    ctx = runner.Ctx(s)
    assert ctx.source_png is None, "the generator attaches the original only when there is one"
