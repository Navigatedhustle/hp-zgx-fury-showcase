"""Condensing a deck to N slides: the proposal's rules are checked by code, applying it is one reversible step, and
what doesn't make the cut becomes appendix slides after an "Appendix" divider."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import compose, facts, main
from app.config import settings
from app.pipeline import deckops, runner
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide, Version


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _deck(n: int = 8) -> Project:
    p = db.save(Project(name="long", filename="long.pptx", status="ready"))
    for i in range(1, n + 1):
        lines = [f"Metric {i} rose to {i * 10}%"] * (1 + i % 3)
        c = compose.blank(i, title=f"Slide {i}", lines=lines)
        db.save(Slide(project_id=p.id, index=i, position=i, content=c.model_dump(),
                      facts=facts.dump(facts.extract(c.for_prompt(), prefix=f"s{i}f")),
                      plan={"pattern": "cards", "headline": f"h{i}", runner.PART_KEY: [0, 1]}))
    return p


def _live(pid):
    return [s for s in db.slides_of(pid) if not runner.is_removed(s)]


def _h(pid):
    return {f"S{i}": s.id for i, s in enumerate(_live(pid), 1)}


# ---------------------------------------------------------------- the rules
def test_a_valid_proposal_is_translated_to_slide_ids():
    p = _deck(5)
    live = _live(p.id)
    prop, why = deckops.validate_proposal({"main": [{"from": ["S1"]}, {"from": ["S2", "S4"], "headline": "x"}],
                                           "appendix": ["S3", "S5"]}, live, 3, [])
    assert why == "" and prop["main"][1]["ids"] == [live[1].id, live[3].id]


@pytest.mark.parametrize("data,problem", [
    ({"main": [{"from": ["S1"]}], "appendix": ["S2", "S3", "S4"]}, "appear nowhere"),
    ({"main": [{"from": ["S1"]}, {"from": ["S1"]}], "appendix": ["S2", "S3", "S4", "S5"]}, "more than once"),
    ({"main": [{"from": ["S1"]}, {"from": ["S2"]}, {"from": ["S3"]}, {"from": ["S4"]}], "appendix": ["S5"]}, "1 to 3"),
    ({"main": [{"from": ["S9"]}], "appendix": []}, "unknown handle"),
    ({"main": [{"from": ["S1", "S2", "S3", "S4", "S5"]}], "appendix": []}, "combines more than"),
    ({"main": [{"from": ["S1"]}], "appendix": ["S2", "S3", "S4", "S5"]}, "must-stay"),
])
def test_a_broken_proposal_is_refused_with_the_rule_it_broke(data, problem):
    p = _deck(5)
    live = _live(p.id)
    keep = [live[4].id] if problem == "must-stay" else []
    prop, why = deckops.validate_proposal(data, live, 3, keep)
    assert prop is None and problem in why


def test_the_fallback_keeps_must_stay_slides_and_the_target():
    p = _deck(8)
    live = _live(p.id)
    prop = deckops.fallback_proposal(live, 3, [live[7].id])
    ids = [m["ids"][0] for m in prop["main"]]
    assert len(ids) == 3 and live[7].id in ids
    assert ids == [s.id for s in live if s.id in ids], "the main deck keeps the original order"
    assert sorted(ids + prop["appendix"]) == sorted(s.id for s in live)


def test_a_model_that_breaks_the_rules_is_corrected_once_then_replaced(monkeypatch):
    p = _deck(6)
    calls = []

    async def fake_chat(msgs, **kw):
        calls.append(msgs)
        return type("Reply", (), {"text": '{"main": [{"from": ["S1"]}], "appendix": []}'})()  # leaves S2–S6 out

    monkeypatch.setattr(runner.llm, "chat", fake_chat)
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    try:
        prop = asyncio.run(deckops.propose_condense(p.id, 3, [], "10-minute slot"))
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    assert len(calls) == 2 and "breaks a rule" in str(calls[1][-1])
    assert prop["source"] == "fallback" and len(prop["main"]) == 3
    assert db.get(Project, p.id).brief[deckops.PROPOSAL_KEY]["guidance"] == "10-minute slot"


# ---------------------------------------------------------------- apply and undo
def test_apply_merges_moves_leftovers_to_the_appendix_and_undo_puts_it_all_back(client):
    p = _deck(6)
    before = [s.id for s in _live(p.id)]
    h = _h(p.id)
    body = {"main": [{"ids": [h["S1"]]}, {"ids": [h["S2"], h["S5"]], "headline": "Two metrics, one story"},
                     {"ids": [h["S6"]]}],
            "appendix": [h["S3"], h["S4"]]}
    r = client.post(f"/api/projects/{p.id}/condense/apply", json=body)
    assert r.status_code == 200, r.text
    merged = r.json()["created"][0]
    live = _live(p.id)
    assert [s.id for s in live] == [h["S1"], merged, h["S6"], h["S3"], h["S4"]]
    assert [bool(s.plan.get("appendix")) for s in live] == [False, False, False, True, True]
    out = client.get(f"/api/projects/{p.id}").json()
    assert out["counts"]["appendix"] == 2 and out["counts"]["slides"] == 5

    assert client.post(f"/api/projects/{p.id}/condense/undo").status_code == 200
    assert [s.id for s in _live(p.id)] == before
    assert not any(s.plan.get("appendix") for s in db.slides_of(p.id))
    assert db.get(Slide, merged) is None


def test_apply_refuses_a_proposal_for_a_deck_that_has_since_changed(client):
    p = _deck(3)
    h = _h(p.id)
    client.delete(f"/api/slides/{h['S3']}")
    r = client.post(f"/api/projects/{p.id}/condense/apply",
                    json={"main": [{"ids": [h["S1"]]}], "appendix": [h["S2"], h["S3"]]})
    assert r.status_code == 400 and "propose again" in r.json()["detail"]


def test_propose_in_mock_mode_writes_a_proposal_the_ui_can_read(client):
    p = _deck(6)
    h = _h(p.id)
    client.post(f"/api/projects/{p.id}/condense/propose", json={"target": 2, "keep": [h["S6"]], "guidance": "CFO"})
    for _ in range(100):
        prop = client.get(f"/api/projects/{p.id}").json()["brief"].get(deckops.PROPOSAL_KEY)
        if prop:
            break
        asyncio.run(asyncio.sleep(0.02))
    assert prop["target"] == 2 and len(prop["main"]) == 2
    assert h["S6"] in {i for m in prop["main"] for i in m["ids"]}
    client.delete(f"/api/projects/{p.id}/condense/proposal")
    assert deckops.PROPOSAL_KEY not in client.get(f"/api/projects/{p.id}").json()["brief"]


# ---------------------------------------------------------------- the appendix in the deck
def test_the_deck_puts_an_appendix_divider_before_the_backup_slides(client):
    p = _deck(3)
    spec, _ = parse_spec('<meta>{"pattern":"cards","title":"T","steps":0}</meta><html><h1 class="title">x</h1></html>'
                         '<css></css><script></script>', "s")
    for s in db.slides_of(p.id):
        v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready", spec=spec.model_dump()))
        db.update(Slide, s.id, approved_version_id=v.id, status="approved")
    last = db.slides_of(p.id)[-1]
    runner.set_slide(last.id, plan={**last.plan, "appendix": True})
    html, _ = runner.build_deck(p.id)
    assert html.count('"id": "appendix"') + html.count('"id":"appendix"') == 1 or "Appendix" in html
    from app import export_pptx as xp
    pages = xp.deck_pages(p.id)
    assert [pg.slide.id for pg in pages][2] == runner.APPENDIX_DIVIDER_ID
    assert len(pages) == 4
