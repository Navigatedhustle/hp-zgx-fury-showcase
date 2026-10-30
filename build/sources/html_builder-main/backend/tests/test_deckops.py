"""Slide management: add to a converted deck, delete and restore, merge and unmerge, undo a split.

Tester feedback these protect: "slides 8 and 17 had related info and the deck was sparse — we wanted to combine
them"; "the planner split one slide into two when it didn't need to"; "let us add and delete slides".
Every operation on a converted deck must be undoable: the PowerPoint behind it is never destroyed.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import compose, facts
from app import main
from app.config import settings
from app.pipeline import deckops, runner
from app.store import db
from app.store.db import Project, Slide


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _deck(n: int = 4, source: str = "pptx") -> Project:
    """A converted deck whose slide i asserts one figure, "$i.5M"."""
    p = db.save(Project(name="ops", filename="ops.pptx", source=source, status="ready"))
    for i in range(1, n + 1):
        c = compose.blank(i, title=f"Slide {i}", lines=[f"Revenue was ${i}.5M"], notes=f"note {i}")
        db.save(Slide(project_id=p.id, index=i, position=i, content=c.model_dump(),
                      facts=facts.dump(facts.extract(c.for_prompt(), prefix=f"s{i}f")),
                      plan={"pattern": "cards", "headline": f"h{i}", runner.PART_KEY: [0, 1]}))
    return p


def _live(pid):
    return [s for s in db.slides_of(pid) if not runner.is_removed(s)]


# ---------------------------------------------------------------- add
def test_a_slide_can_be_added_to_a_converted_deck_without_moving_any_render(client):
    p = _deck(3)
    before = {s.id: s.index for s in db.slides_of(p.id)}
    new = client.post(f"/api/projects/{p.id}/slides", json={"after": 1}).json()
    assert new["label"] == "new"
    after = db.slides_of(p.id)
    assert [s.position for s in after] == [1, 2, 3, 4] and after[1].id == new["id"]
    assert all(s.index == before[s.id] for s in after if s.id in before), "a source slide's index names its render"
    assert after[1].index == 4, "the new slide takes an index no source slide uses"
    # and it is typed like a composed slide, because it has no PowerPoint behind it
    r = client.post(f"/api/slides/{new['id']}/write", json={"title": "Our roadmap", "body": "Launch in Q3"})
    assert r.status_code == 200 and db.get(Slide, new["id"]).content["title"] == "Our roadmap"


# ---------------------------------------------------------------- delete / restore
def test_deleting_a_source_slide_takes_it_out_and_restore_brings_it_back(client):
    p = _deck(3)
    sid = db.slides_of(p.id)[1].id
    client.delete(f"/api/slides/{sid}")
    out = client.get(f"/api/projects/{p.id}").json()
    assert out["counts"]["slides"] == 2 and out["counts"]["removed"] == 1
    assert [s["position"] for s in out["slides"] if not s["plan"].get("removed")] == [1, 2]

    client.post(f"/api/slides/{sid}/restore", json={"after": 1})
    live = _live(p.id)
    assert [s.id for s in live][1] == sid and db.get(Slide, sid).included


def test_the_last_live_slide_cannot_be_deleted(client):
    p = _deck(1)
    assert client.delete(f"/api/slides/{db.slides_of(p.id)[0].id}").status_code == 400


def test_an_added_slide_is_really_deleted(client):
    p = _deck(2)
    new = client.post(f"/api/projects/{p.id}/slides", json={}).json()
    client.delete(f"/api/slides/{new['id']}")
    assert db.get(Slide, new["id"]) is None


# ---------------------------------------------------------------- merge
def test_merging_two_non_adjacent_slides_makes_one_slide_holding_both(client):
    p = _deck(4)
    s1, _, s3, _ = db.slides_of(p.id)
    r = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": [s3.id, s1.id]})
    assert r.status_code == 200, r.text
    m = db.get(Slide, r.json()["id"])
    assert r.json()["label"] == "1+3"
    assert m.position == 1, "the merged slide takes the first slide's place"
    text = str(runner.content_for_prompt(m))
    assert "Slide 1" in text and "Slide 3" in text and "$1.5M" in text and "$3.5M" in text
    assert "note 1" in m.content["notes"] and "note 3" in m.content["notes"]
    assert {f.raw for f in runner.slide_facts(m)} >= {"$1.5M", "$3.5M"}, "no fact is lost in a merge"
    for o in (s1, s3):
        row = db.get(Slide, o.id)
        assert not row.included and row.plan["removed"] == "merged" and row.plan["merged_into"] == m.id
    assert [s.position for s in _live(p.id)] == [1, 2, 3]
    assert m.plan.get("no_split") and m.plan.get("pattern"), "planned as one slide"


def test_unmerge_restores_the_originals_where_they_were(client):
    p = _deck(3)
    ids = [s.id for s in db.slides_of(p.id)]
    m = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": ids[:2]}).json()
    assert client.post(f"/api/slides/{m['id']}/unmerge").status_code == 200
    assert db.get(Slide, m["id"]) is None
    assert [s.id for s in _live(p.id)] == ids
    assert all(s.included and not s.plan.get("merged_into") for s in db.slides_of(p.id))


def test_deleting_a_merged_slide_leaves_its_originals_restorable(client):
    p = _deck(3)
    ids = [s.id for s in db.slides_of(p.id)]
    m = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": ids[:2]}).json()
    client.delete(f"/api/slides/{m['id']}")
    for i in ids[:2]:
        row = db.get(Slide, i)
        assert row.plan["removed"] == "deleted" and "merged_into" not in row.plan
    assert client.post(f"/api/slides/{ids[0]}/restore", json={}).status_code == 200


@pytest.mark.parametrize("pick,why", [(lambda ids: ids[:1], "at least two"), (lambda ids: ids[:5], "at most")])
def test_merge_refuses_what_cannot_become_one_slide(client, pick, why):
    p = _deck(5)
    ids = [s.id for s in db.slides_of(p.id)]
    r = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": pick(ids)})
    assert r.status_code == 400 and why in r.json()["detail"]


def test_a_removed_slide_cannot_be_merged(client):
    p = _deck(3)
    ids = [s.id for s in db.slides_of(p.id)]
    client.delete(f"/api/slides/{ids[0]}")
    assert client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": ids[:2]}).status_code == 400


# ---------------------------------------------------------------- undo split
def _split_deck() -> tuple[Project, list[Slide]]:
    p = _deck(3)
    s2 = db.slides_of(p.id)[1]
    led = runner.slide_facts(s2)
    runner.set_slide(s2.id, plan={**s2.plan, runner.PART_KEY: [0, 2]}, facts=facts.dump(led[:0]))
    b = db.save(Slide(project_id=p.id, index=2, part=1, position=3, content=s2.content,
                      facts=facts.dump(led), plan={"pattern": "cards", runner.PART_KEY: [1, 2]}))
    db.update(Slide, db.slides_of(p.id)[-1].id, position=4) if db.slides_of(p.id)[-1].id != b.id else None
    return p, [db.get(Slide, s2.id), b]


def test_merging_the_parts_of_a_split_slide_undoes_the_split(client):
    p, (a, b) = _split_deck()
    r = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": [a.id, b.id]}).json()
    assert r["id"] == a.id, "part 0 keeps its row and its history"
    assert db.get(Slide, b.id) is None
    kept = db.get(Slide, a.id)
    assert kept.plan["no_split"] and kept.plan[runner.PART_KEY] == [0, 1]
    assert "$2.5M" in {f.raw for f in runner.slide_facts(kept)}, "the ledger comes back whole"
    assert r["label"] == "2"


# ---------------------------------------------------------------- through the planner
def _replan(monkeypatch, pid, entries_for):
    async def fake_call(batch, **kw):
        fake_call.notes.append(kw.get("note", ""))
        return {"deck_title": "D", "audience": "a", "tone": "t", "narrative": "n",
                "slides": [e for b in batch for e in entries_for(b["index"])]}
    fake_call.notes = []
    monkeypatch.setattr(runner, "_plan_call", fake_call)
    monkeypatch.setattr(runner.llm, "vision_enabled", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    try:
        asyncio.run(runner.plan(pid))
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    return fake_call.notes


def _entry(index, **kw):
    return {"index": index, "role": "evidence", "pattern": "cards", "eyebrow": "e", "headline": f"h{index}",
            "key_message": "m", "idea_a": "a", "idea_b": "b", "theme": "light", "include": True, "key_facts": [], **kw}


def test_a_replan_leaves_removed_slides_out_and_keeps_a_merge(monkeypatch, client):
    p = _deck(4)
    ids = [s.id for s in db.slides_of(p.id)]
    m = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": [ids[0], ids[2]]}).json()
    client.delete(f"/api/slides/{ids[3]}")
    _replan(monkeypatch, p.id, lambda i: [_entry(i), _entry(i)])  # a planner that wants to split everything
    live = _live(p.id)
    assert {s.id for s in live} >= {m["id"], ids[1]}
    assert not any(s.id in (ids[0], ids[2], ids[3]) for s in live), "deleted and merged-away slides stay out"
    merged = db.get(Slide, m["id"])
    assert merged.plan.get("merged_from") and merged.plan.get("no_split")
    assert len([s for s in live if s.index == merged.index]) == 1, "a merged slide is never re-split"
    positions = [s.position for s in db.slides_of(p.id)]
    assert len(positions) == len(set(positions)), "no two rows share a position"


def test_switching_splitting_off_keeps_one_slide_per_source(monkeypatch):
    p = _deck(3)
    runner.set_project(p.id, brief={"allow_split": False})
    notes = _replan(monkeypatch, p.id, lambda i: [_entry(i), _entry(i)])
    assert len(_live(p.id)) == 3
    assert all(runner.NO_SPLIT_NOTE in n for n in notes), "the planner is told, not only overruled"
    assert db.get(Project, p.id).brief.get("allow_split") is False, "a re-plan keeps the user's setting"


def test_generate_plans_an_added_slide_first(client, monkeypatch):
    p = _deck(2)
    new = client.post(f"/api/projects/{p.id}/slides", json={}).json()
    client.post(f"/api/slides/{new['id']}/write", json={"title": "Next steps", "body": "Pilot in Q1"})
    seen = []

    async def fake_generate(pid, slide_ids=None):
        seen.append(db.get(Slide, new["id"]).plan.get("pattern"))

    monkeypatch.setattr(runner, "generate_project", fake_generate)
    client.post(f"/api/projects/{p.id}/generate", json={"slide_ids": [new["id"]]})
    for _ in range(100):
        if seen:
            break
        asyncio.run(asyncio.sleep(0.01))
    assert seen and seen[0], "the added slide had a plan before it was designed"
