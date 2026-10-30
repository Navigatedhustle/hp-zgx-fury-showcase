"""The direct-manipulation editor's HTTP surface: outline, edit -> new version, QA re-check."""
import asyncio

import pytest
from fastapi import HTTPException

from app import main
from app.edit import EditRequest, check_style, parse_ops
from app.ingest.pptx_parse import SlideContent
from app.pipeline import runner
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide, Version

RAW = """<meta>{"pattern":"cards","title":"T","steps":2}</meta>
<html>
<h1 class="title">Heading</h1>
<div class="grid">
  <div class="card appear"><h3>One</h3></div>
  <div class="card appear"><h3>Two</h3></div>
</div>
</html>
<css>.card{padding:10px}</css>
<script>function go(root, step){ H.reveal(root, '.card', step); }</script>"""


def _setup() -> tuple[Project, Slide, Version]:
    p = db.save(Project(name="edit", filename="edit.pptx"))
    s = db.save(Slide(project_id=p.id, index=1, position=1, status="review",
                      content=SlideContent(index=1, title="Heading").model_dump()))
    spec, _ = parse_spec(RAW, s.id)
    v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready",
                        spec=spec.model_dump(), qa={"passed": True, "findings": []}, score=9.0))
    return p, s, v


def _outline(vid: str) -> list[dict]:
    return asyncio.run(main.version_outline(vid))["elements"]


def _eid(vid: str, *, tag: str = "", cls: str = "", text: str = "") -> str:
    for e in _outline(vid):
        if tag and e["tag"] != tag:
            continue
        if cls and cls not in e["classes"]:
            continue
        if text and text not in e["text"]:
            continue
        return e["eid"]
    raise AssertionError(f"no element for tag={tag} cls={cls} text={text}")


def _edit(vid: str, ops: list[dict]) -> dict:
    """Call the route and let any QA job it spawned finish before the loop closes."""
    async def run():
        try:
            return await main.version_edit(vid, EditRequest(ops=parse_ops(ops)))
        finally:
            pending = [t for ts in runner.jobs.tasks.values() for t in ts if not t.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    return asyncio.run(run())


@pytest.fixture
def no_qa(monkeypatch):
    """Record QA re-checks instead of starting Chromium."""
    calls: list[tuple[str, list[str]]] = []

    async def fake(vid: str, reasons: list[str]) -> None:
        calls.append((vid, reasons))

    monkeypatch.setattr(main, "qa_recheck", fake)
    return calls


# ---------------------------------------------------------------- outline
def test_outline_persists_the_stamped_ids():
    _, _, v = _setup()
    assert "data-eid" not in db.get(Version, v.id).spec["html"]
    before = db.get(Version, v.id).updated_at

    eids = [e["eid"] for e in _outline(v.id)]
    stored = db.get(Version, v.id).spec["html"]
    assert eids and all(f'data-eid="{e}"' in stored for e in eids)
    # a quiet write: `updated_at` is the preview's cache key, and reloading the iframe would
    # throw away the editing session that just asked for the outline
    assert db.get(Version, v.id).updated_at == before
    assert [e["eid"] for e in _outline(v.id)] == eids  # idempotent, and stable across calls


def test_outline_reports_what_the_server_would_refuse():
    _, _, v = _setup()
    by_eid = {e["eid"]: e for e in _outline(v.id)}
    grid = next(e for e in by_eid.values() if "grid" in e["classes"])
    card = next(e for e in by_eid.values() if "card" in e["classes"])
    assert card["deletable"] and card["locks"] == []  # two cards: the script still finds one
    assert card["has_children"] and card["editable_text"]
    # the grid carries every .card the script selects, so deleting it would be refused
    assert grid["locks"] == ["script:.card"] and not grid["deletable"]


def test_outline_404s_and_400s():
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.version_outline("nope"))
    assert e.value.status_code == 404
    p, s, _ = _setup()
    empty = db.save(Version(slide_id=s.id, project_id=p.id, lineage="B", number=1, status="queued"))
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.version_outline(empty.id))
    assert e.value.status_code == 400


# ---------------------------------------------------------------- editing
def test_a_text_edit_creates_a_new_version_and_leaves_the_original_alone(no_qa):
    _, s, v = _setup()
    eid = _eid(v.id, tag="h1")
    before = db.get(Version, v.id).spec["html"]

    out = _edit(v.id, [{"op": "set_text", "eid": eid, "text": "Edited heading"}])
    assert out["ok"] and out["changed"]
    nv = db.get(Version, out["version"]["id"])
    assert nv.id != v.id and nv.parent_id == v.id and nv.lineage == "A" and nv.number == 2
    assert nv.origin == "edit" and nv.status == "ready" and "text change" in nv.comment
    assert "Edited heading" in nv.spec["html"] and "Heading</h1>" not in nv.spec["html"]
    assert out["version"]["origin"] == "edit"

    old = db.get(Version, v.id)
    assert old.spec["html"] == before and old.origin == "llm"  # history is preserved: revert = show the parent
    assert [x.id for x in db.versions_of_slide(s.id)] == [v.id, nv.id]
    assert main.version_out(old)["origin"] == "llm"


def test_a_rejected_op_returns_400_and_creates_no_version(no_qa):
    _, s, v = _setup()
    grid = _eid(v.id, cls="grid")
    title = _eid(v.id, tag="h1")
    before = db.get(Version, v.id).spec["html"]

    with pytest.raises(HTTPException) as e:
        # the good op must not survive the bad one: apply_ops is atomic and so is the route
        _edit(v.id, [{"op": "set_text", "eid": title, "text": "fine"},
                     {"op": "set_text", "eid": grid, "text": "discards markup"}])
    assert e.value.status_code == 400
    d = e.value.detail
    assert d["error_code"] == "has-children" and d["failed_index"] == 1 and d["op"] == "set_text" and d["eid"] == grid
    assert isinstance(d["message"], str) and d["message"]
    assert len(db.versions_of_slide(s.id)) == 1
    assert db.get(Version, v.id).spec["html"] == before

    with pytest.raises(HTTPException) as e:
        _edit(v.id, [])
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        _edit(v.id, [{"op": "set_style", "eid": title, "style": {"position": "absolute"}}])
    assert e.value.detail["error_code"] == "style-prop"
    assert len(db.versions_of_slide(s.id)) == 1


def test_an_edit_that_changes_nothing_does_not_branch(no_qa):
    _, s, v = _setup()
    eid = _eid(v.id, tag="h1")
    out = _edit(v.id, [{"op": "set_text", "eid": eid, "text": "Heading"}])
    assert out["ok"] and not out["changed"] and out["version"]["id"] == v.id
    assert len(db.versions_of_slide(s.id)) == 1


def test_editing_the_approved_version_moves_the_approval(no_qa):
    _, s, v = _setup()
    runner.choose(s.id, v.id)
    eid = _eid(v.id, tag="h1")
    out = _edit(v.id, [{"op": "set_text", "eid": eid, "text": "Edited heading"}])
    after = db.get(Slide, s.id)
    assert after.approved_version_id == out["version"]["id"]  # the deck follows the edit
    assert after.status == "approved"


# ---------------------------------------------------------------- QA re-check
def test_structural_edits_re_run_qa_and_cosmetic_ones_do_not(no_qa):
    _, _, v = _setup()
    title = _eid(v.id, tag="h1")

    out = _edit(v.id, [{"op": "set_style", "eid": title, "style": {"color": "#ff0000"}}])
    assert out["changed"] and not out["qa_recommended"] and no_qa == []  # a recolour is not worth Chromium + a VLM
    assert db.get(Version, out["version"]["id"]).qa["edit"]["checked"] is False

    card = _eid(v.id, cls="card")
    out = _edit(v.id, [{"op": "delete", "eid": card}])
    assert out["qa_recommended"] and out["qa_reasons"]
    assert [c[0] for c in no_qa] == [out["version"]["id"]]
    assert no_qa[0][1] == out["qa_reasons"]
    assert db.get(Version, out["version"]["id"]).stage_note  # the UI can say a check is running
    # the engine's warnings reach the client so it can explain the side effect
    assert any(w["code"] == "step-order" for w in out["warnings"])


def test_qa_recheck_writes_findings_onto_the_edited_version(monkeypatch):
    """The job itself, with the renderer and the critic stubbed: it reports, it never repairs."""
    _, s, v = _setup()
    card = _eid(v.id, cls="card")
    out = _edit(v.id, [{"op": "delete", "eid": card}])
    nv_id = out["version"]["id"]
    spec_before = db.get(Version, nv_id).spec

    class Report:
        findings = []
        text = "Heading One"
        steps = 1
        shots = ["shot_final.png"]

    async def fake_check(spec, slide_id, assets, out_dir, title="QA"):
        assert slide_id == s.id
        return Report()

    monkeypatch.setattr(main, "check_spec", fake_check)
    monkeypatch.setattr(main, "ledger_findings", lambda *a, **k: [])
    asyncio.run(main.qa_recheck(nv_id, ["delete changes the layout"]))

    nv = db.get(Version, nv_id)
    assert nv.status == "ready" and not nv.stage_note
    assert nv.qa["edit"] == {"parent": v.id, "reasons": ["delete changes the layout"], "checked": True}
    assert nv.qa["passed"] is True and nv.qa["findings"] == []
    assert nv.spec == spec_before  # QA on a hand edit never rewrites the markup


def test_every_control_the_toolbar_offers_is_accepted():
    """The exact values in frontend/src/components/SlideEditor.tsx. A control that always 400s is
    worse than a control that isn't there, so the two lists are pinned together here."""
    offered = {
        "color": ["var(--ink)", "var(--blue)", "var(--mute)", "var(--paper)", "var(--sky)", "var(--good)", "var(--warn)", "var(--alert)", ""],
        "background-color": ["var(--tint)", "var(--track)", "var(--paper)", "var(--blue)", "var(--ink)", ""],
        "font-size": ["var(--t-hero)", "var(--t-title)", "var(--t-h2)", "var(--t-h3)", "var(--t-lede)",
                      "var(--t-body)", "var(--t-small)", "var(--t-micro)", ""],
        "font-weight": ["400", "600", "800", ""],
        "text-align": ["left", "center", "right"],
        "text-transform": ["uppercase"],
    }
    cats = {prop: {check_style(prop, v) for v in values} for prop, values in offered.items()}
    assert cats["font-size"] == {"layout"}  # so the UI is right to expect a QA re-check from it
    assert all(c == {"cosmetic"} for p, c in cats.items() if p != "font-size")

    _, _, v = _setup()
    title = _eid(v.id, tag="h1")
    for prop, values in offered.items():
        out = _edit(v.id, [{"op": "set_style", "eid": title, "style": {prop: values[0]}}])
        assert out["ok"], (prop, values[0])


def test_qa_recheck_survives_a_broken_render(monkeypatch):
    _, _, v = _setup()
    card = _eid(v.id, cls="card")
    nv_id = _edit(v.id, [{"op": "delete", "eid": card}])["version"]["id"]

    async def boom(*a, **k):
        raise RuntimeError("chromium went away")

    monkeypatch.setattr(main, "check_spec", boom)
    asyncio.run(main.qa_recheck(nv_id, ["delete changes the layout"]))
    nv = db.get(Version, nv_id)
    assert nv.status == "ready" and not nv.stage_note  # the edit stands even when the check can't run
    assert nv.qa["edit"]["checked"] is False and "chromium" in nv.qa["edit"]["error"]
