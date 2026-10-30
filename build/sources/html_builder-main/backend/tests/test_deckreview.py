"""Redesign with a reason, and the deck-level work: one instruction for every slide, the consistency review, and
the pre-export readiness checklist."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import compose, facts, main
from app.pipeline import deckreview, runner
from app.spec import parse_spec
from app.store import db
from app.store.db import Feedback, Project, Slide, Version
from sqlmodel import select

SPEC = ('<meta>{{"pattern":"{p}","title":"{t}","steps":0,"notes":{n},"sources":"{src}"}}</meta>'
        '<html><h1 class="title">{t}</h1><div class="grid-3"><div class="card">x</div></div></html><css></css><script></script>')


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _spec(title="T", pattern="cards", notes='["say this"]', src="IDC 2025"):
    spec, _ = parse_spec(SPEC.format(p=pattern, t=title, n=notes, src=src), "s")
    return spec.model_dump()


def _deck(lines: list[str], patterns: list[str] | None = None, approve=True) -> Project:
    p = db.save(Project(name="deck", filename="d.pptx", status="reviewing", deck_title="Deck"))
    for i, line in enumerate(lines, 1):
        c = compose.blank(i, title=f"Slide {i}", lines=[line])
        s = db.save(Slide(project_id=p.id, index=i, position=i, content=c.model_dump(), status="review",
                          facts=facts.dump(facts.extract(c.for_prompt(), prefix=f"s{i}f")),
                          plan={"pattern": (patterns or ["cards"] * len(lines))[i - 1], "headline": f"h{i}",
                                runner.PART_KEY: [0, 1]}))
        v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready",
                            spec=_spec(f"Slide {i}"), qa={"passed": True, "findings": []}, score=8.0))
        db.save(Version(slide_id=s.id, project_id=p.id, lineage="B", number=1, status="ready",
                        spec=_spec(f"Slide {i}", pattern="specs"), qa={"passed": True, "findings": []}, score=7.0))
        if approve:
            db.update(Slide, s.id, status="approved", approved_version_id=v.id)
    return p


def _drain(pid=None):
    """Wait for the jobs the route spawned on the TestClient's loop (they can't be awaited from here)."""
    import time
    for _ in range(250):
        if not any(runner.jobs.busy(x) for x in ([pid] if pid else list(runner.jobs.tasks))):
            return
        time.sleep(0.02)
    raise AssertionError("jobs never finished")


# ---------------------------------------------------------------- redesign with a reason
def test_redesign_note_names_the_reasons_and_the_rejected_compositions():
    p = _deck(["Revenue grew to $4.2M"])
    s = db.slides_of(p.id)[0]
    note, label, rejected = runner.redesign_note(s.id, ["too-dense", "chart-wrong"], "the chart hides Q4")
    assert "Too dense" in note and "Chart is wrong" in note and "the chart hides Q4" in note
    assert "rejected variant A" in note and "rejected variant B" in note, "the designs being replaced are described"
    assert label.startswith("Redesign: Too dense, Chart is wrong")
    assert len(rejected) == 2


def test_the_redesign_route_records_why_and_can_change_the_layout(client, monkeypatch):
    p = _deck(["Revenue grew to $4.2M"])
    s = db.slides_of(p.id)[0]
    seen = {}

    async def fake(sid, lineages=("A", "B"), redesign="", comment=""):
        seen.update(redesign=redesign, comment=comment)

    monkeypatch.setattr(runner, "generate_slide", fake)
    r = client.post(f"/api/slides/{s.id}/regenerate", json={"reasons": ["off-story"], "note": "lead with cost",
                                                            "pattern": "compare"})
    assert r.status_code == 200
    _drain()
    assert db.get(Slide, s.id).plan["pattern"] == "compare"
    assert "Off-story" in seen["redesign"] and "`compare` pattern" in seen["redesign"]
    assert seen["comment"].startswith("Redesign:")
    with db.session() as ses:
        fb = ses.exec(select(Feedback).where(Feedback.slide_id == s.id)).one()
    assert fb.reasons == ["off-story", "wrong-layout"] and fb.note == "lead with cost" and len(fb.rejected) == 2


def test_a_plain_redesign_still_works_without_a_reason(client, monkeypatch):
    p = _deck(["x"])
    s = db.slides_of(p.id)[0]
    seen = {}

    async def fake(sid, lineages=("A", "B"), redesign="", comment=""):
        seen.update(redesign=redesign)

    monkeypatch.setattr(runner, "generate_slide", fake)
    assert client.post(f"/api/slides/{s.id}/regenerate").status_code == 200
    _drain()
    assert seen["redesign"] == ""


# ---------------------------------------------------------------- one instruction, every slide
def test_an_instruction_revises_the_scope_and_keeps_approvals_only_when_qa_passes(client, monkeypatch):
    p = _deck(["one", "two", "three"])
    s1, s2, s3 = db.slides_of(p.id)
    calls = []

    async def fake_revise(sid, base_id, comment):
        calls.append((sid, comment))
        ok = sid == s1.id
        v = db.save(Version(slide_id=sid, project_id=p.id, lineage="A", number=2, status="ready", parent_id=base_id,
                            comment=comment, spec=_spec(), qa={"passed": ok, "findings": []}))
        runner.set_slide(sid, status="review", approved_version_id=None)
        return v

    monkeypatch.setattr(runner, "revise", fake_revise)
    r = client.post(f"/api/projects/{p.id}/instruct", json={"instruction": "Less text everywhere",
                                                              "slide_ids": [s1.id, s2.id]})
    assert r.status_code == 200 and r.json()["slides"] == 2
    _drain()
    assert [c[0] for c in calls] == [s1.id, s2.id] and all(c[1] == "Less text everywhere" for c in calls)
    a, b = db.get(Slide, s1.id), db.get(Slide, s2.id)
    assert a.status == "approved" and db.get(Version, a.approved_version_id).number == 2
    assert b.status == "review", "a revision that fails QA waits for the user instead of replacing the approval"
    assert db.get(Slide, s3.id).status == "approved", "out of scope, untouched"


def test_an_empty_instruction_is_refused(client):
    p = _deck(["one"])
    assert client.post(f"/api/projects/{p.id}/instruct", json={"instruction": "  "}).status_code == 400


# ---------------------------------------------------------------- consistency
def test_code_finds_one_quantity_with_two_values_and_a_repeated_layout():
    p = _deck(["Annual cloud spend reached $4.2M", "Annual cloud spend reached $4.5M", "Something else"],
              patterns=["cards", "cards", "chart"])
    issues = deckreview.code_issues(db.slides_of(p.id))
    kinds = [i["kind"] for i in issues]
    assert "numbers" in kinds and "$4.2M" in next(i for i in issues if i["kind"] == "numbers")["issue"]
    assert "flow" in kinds


def test_model_issues_are_mapped_to_slides_and_junk_is_dropped():
    p = _deck(["a", "b"])
    slides = db.slides_of(p.id)
    got = deckreview.parse_issues({"issues": [
        {"slides": ["S2"], "kind": "terms", "issue": "Two names for one product", "fix": "Say Z8 Fury G5"},
        {"slides": ["S9"], "kind": "story", "issue": "unknown slide"},
        {"slides": ["S1"], "kind": "story", "issue": ""},
    ]}, slides)
    assert len(got) == 1 and got[0]["slide_ids"] == [slides[1].id] and got[0]["source"] == "model"


def test_the_review_is_stored_on_the_project(client):
    p = _deck(["Annual cloud spend reached $4.2M", "Annual cloud spend reached $4.5M"])
    assert client.post(f"/api/projects/{p.id}/consistency").status_code == 200
    _drain()
    stored = db.get(Project, p.id).brief[deckreview.CONSISTENCY_KEY]
    assert stored["issues"] and stored["at"]


# ---------------------------------------------------------------- readiness
def test_readiness_lists_what_would_go_out_wrong(client):
    p = _deck(["Revenue grew to $4.2M", "Margin held at 40%", "Headcount grew 18%"], approve=False)
    s1, s2, s3 = db.slides_of(p.id)
    for v in db.versions_of_slide(s1.id):
        db.update(Version, v.id, qa={"passed": False, "fatal": ["the slide says $5.1M"], "findings": []})
    for v in db.versions_of_slide(s2.id):
        db.update(Version, v.id, spec=_spec(notes="[]", src=""))
    with db.session() as ses:
        for v in ses.exec(select(Version).where(Version.slide_id == s3.id)):
            ses.delete(v)
        ses.commit()
    got = client.get(f"/api/projects/{p.id}/readiness").json()
    kinds = {(i["label"], i["kind"]) for i in got["items"]}
    assert ("1", "fact") in kinds and ("2", "notes") in kinds and ("2", "sources") in kinds
    assert ("3", "undesigned") in kinds and ("1", "unapproved") in kinds and ("", "consistency") in kinds
    assert got["ready"] is False and got["blocks"] == 2
