"""The measurement plumbing: human-choice logging, the eval's calibration harness, and the startup recovery.

None of this generates a slide, and all of it decides whether the numbers the project reports mean anything:

  * `runner.choose` is the only place the product learns which variant a person actually wanted. If that record
    is wrong or missing, judge-human agreement is unmeasurable and there is no corpus to fine-tune on later.
  * `run_eval.calibration` turns those records into the report's headline agreement figure — and has to say
    "unknown" rather than print a number when there is nothing to compute it from.
  * `runner.recover_interrupted` runs on every server start and rewrites statuses across three tables. Nothing
    verified it before this file.
"""
import asyncio
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from app.pipeline import runner
from app.store import db
from app.store.db import Choice, Project, Slide, Version

ROOT = Path(__file__).resolve().parents[2]


def _load_run_eval():
    """evals/run_eval.py is a script, not a package. conftest has already pinned DATA_DIR, so importing it is
    side-effect free (the isolated output directory is only created inside main())."""
    spec = importlib.util.spec_from_file_location("run_eval_under_test", ROOT / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_eval = _load_run_eval()


def _slide_with_two_variants(*, a_score=8.0, b_score=7.9, ab_winner="B"):
    p = db.save(Project(name="choices", filename="c.pptx", deck_title="Choice deck"))
    s = db.save(Slide(project_id=p.id, index=1, position=1, plan={"pattern": "cards"}))
    ab = {"status": runner.AB_OK, "winner": ab_winner, "confidence": 80, "reason": "clearer hierarchy",
          "order": "AB", "versions": {}}
    vs = {}
    for lineage, score in (("A", a_score), ("B", b_score)):
        vs[lineage] = db.save(Version(
            slide_id=s.id, project_id=p.id, lineage=lineage, status="ready", score=score,
            spec={"meta": {"title": lineage}},
            qa={"critic_status": "ok", "critic": {"scores": {k: score for k in runner.criteria()}},
                "ab": {**ab, "recommended": ab_winner == lineage}}))
    ab["versions"] = {"A": vs["A"].id, "B": vs["B"].id}
    return p, s, vs


# ------------------------------------------------------------------ item 4: log every human choice
def test_choosing_a_variant_records_what_was_rejected_too():
    p, s, vs = _slide_with_two_variants()
    before = len(db.choices())
    runner.choose(s.id, vs["B"].id)
    rows = db.choices(p.id)
    assert len(db.choices()) == before + 1
    c = rows[-1]
    assert (c.chosen_version_id, c.chosen_lineage, c.chosen_score) == (vs["B"].id, "B", 7.9)
    assert (c.rejected_version_id, c.rejected_lineage, c.rejected_score) == (vs["A"].id, "A", 8.0)
    assert c.deck == "Choice deck" and c.pattern == "cards" and c.slide_index == 1
    assert c.chosen_critic == 7.9 and c.rejected_critic == 8.0
    assert c.candidates == 2 and c.source == "user"
    # the two signals the calibration is built from
    assert c.judge_winner == "B" and c.judge_agrees is True
    assert c.score_agrees is False, "the higher pointwise score was the one the human passed over"


def test_a_choice_survives_its_project_being_deleted():
    """The record is the calibration corpus; it carries no slide content and must outlive the project."""
    p, s, vs = _slide_with_two_variants()
    runner.choose(s.id, vs["A"].id)
    db.delete_project(p.id)
    assert db.get(Project, p.id) is None
    kept = db.choices(p.id)
    assert len(kept) == 1 and kept[0].chosen_lineage == "A"


def test_a_choice_with_nothing_to_compare_against_is_still_recorded():
    p = db.save(Project(name="single", filename="c.pptx"))
    s = db.save(Slide(project_id=p.id, index=1, position=1))
    v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", status="ready", score=7.0, spec={"meta": {}}))
    runner.choose(s.id, v.id)
    c = db.choices(p.id)[-1]
    assert c.rejected_version_id == "" and c.judge_agrees is None and c.score_agrees is None


def test_a_broken_record_never_blocks_the_approval(monkeypatch):
    p, s, vs = _slide_with_two_variants()
    monkeypatch.setattr(db, "log_choice", lambda **_: (_ for _ in ()).throw(RuntimeError("disk full")))
    slide = runner.choose(s.id, vs["A"].id)
    assert slide.status == "approved" and slide.approved_version_id == vs["A"].id


# ------------------------------------------------------------------ item 5: the calibration harness
def test_agreement_is_reported_as_unknown_when_there_is_nothing_to_measure(tmp_path):
    rows, why = run_eval.read_choices(tmp_path / "missing.db")
    assert rows == [] and "no application database" in why
    out = run_eval.calibration(rows, why)
    assert out["judge_agreement"] is None and out["judge_agreement_n"] == 0
    assert out["note"] == why, "the report must say why, not print a zero"
    summary, md = run_eval.summarize([], out)
    assert summary["judge_agreement_pct"] is None
    assert "Judge agreement is unknown" in md and why in md


def test_an_empty_choice_table_says_so_rather_than_claiming_zero(tmp_path):
    path = tmp_path / "empty.db"
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE choice ({', '.join(c + ' TEXT' for c in run_eval.CHOICE_COLUMNS)})")
    con.commit()
    con.close()
    rows, why = run_eval.read_choices(path)
    assert rows == [] and "no human A/B choices" in why
    assert run_eval.calibration(rows, why)["judge_agreement"] is None


def test_agreement_is_computed_from_real_records(tmp_path):
    p, s, vs = _slide_with_two_variants()
    runner.choose(s.id, vs["B"].id)  # judge said B, human said B  -> judge agrees, score does not
    p2, s2, vs2 = _slide_with_two_variants(a_score=9.0, b_score=6.0, ab_winner="B")
    runner.choose(s2.id, vs2["A"].id)  # judge said B, human said A -> judge disagrees, score does
    rows, why = run_eval.read_choices(Path(db.engine().url.database))
    assert not why, why
    out = run_eval.calibration([r for r in rows if r["chosen_lineage"]], "")
    assert out["judge_agreement_n"] >= 2
    assert 0 <= out["judge_agreement"] <= 100
    assert out["human_picked_A"] >= 1 and out["human_picked_B"] >= 1
    assert "directional" in out["note"], "a handful of picks must not be presented as a measurement"


def test_a_small_sample_is_flagged_and_a_large_one_is_not():
    rows = [{"chosen_lineage": "A", "judge_agrees": True, "score_agrees": True} for _ in range(40)]
    rows[0]["judge_agrees"] = False
    out = run_eval.calibration(rows, "")
    assert out["judge_agreement"] == 97.5 and out["judge_agreement_n"] == 40
    assert out["score_agreement"] == 100.0
    assert out["note"] == ""


# ------------------------------------------------------------------ item 3: position-swap debiasing
def test_the_two_orderings_of_a_pair_are_combined():
    agree = run_eval.combine_judgements({"relative_quality": 90, "better": "candidate", "gaps": ["x"]},
                                        {"relative_quality": 80, "better": "candidate", "gaps": ["y"]})
    assert agree["relative_quality"] == 85.0 and agree["better"] == "candidate"
    assert agree["position_flip"] is False and agree["position_delta"] == 10.0
    assert agree["gaps"] == ["x", "y"] and len(agree["runs"]) == 2

    flip = run_eval.combine_judgements({"relative_quality": 95, "better": "candidate", "gaps": []},
                                       {"relative_quality": 60, "better": "reference", "gaps": []})
    assert flip["better"] == "tie", "a verdict that reverses with the image order is not a verdict"
    assert flip["position_flip"] is True and flip["position_delta"] == 35.0

    half = run_eval.combine_judgements({"relative_quality": 70, "better": "reference", "gaps": []}, None)
    assert half["relative_quality"] == 70 and half["position_flip"] is None
    assert run_eval.combine_judgements(None, None) is None


def test_the_pairwise_prompt_names_the_order_it_actually_sends(tmp_path):
    from PIL import Image

    from app.pipeline import prompts

    a, b = tmp_path / "shot_a.png", tmp_path / "shot_b.png"
    for f in (a, b):
        Image.new("RGB", (8, 8), (2, 74, 216)).save(f)
    for swapped in (False, True):
        msgs = prompts.ab_messages(plan={"pattern": "cards"}, content={"title": "t"}, shot_a=a, shot_b=b,
                                   steps_a=3, steps_b=1, swapped=swapped)
        text = msgs[-1]["content"] if isinstance(msgs[-1]["content"], str) else \
            " ".join(p.get("text", "") for p in msgs[-1]["content"])
        assert f"image 1 = variant {'B' if swapped else 'A'}" in text
        assert "{{" not in text


def test_the_ab_order_alternates_across_slides():
    orders = {runner._ab_order_swapped(f"s{i:08x}") for i in range(32)}
    assert orders == {True, False}, "every slide judged in the same order inherits one position bias"


# ------------------------------------------------------------------ item 9: recover_interrupted
def test_recover_interrupted_fails_in_flight_work_and_leaves_finished_work_alone():
    p_gen = db.save(Project(name="gen", filename="a.pptx", status="generating", stage_note="Generating"))
    p_plan = db.save(Project(name="plan", filename="b.pptx", status="planning", stage_note="Planning"))
    p_done = db.save(Project(name="done", filename="c.pptx", status="complete"))
    s_busy = db.save(Slide(project_id=p_gen.id, index=1, position=1, status="generating"))
    s_rev = db.save(Slide(project_id=p_gen.id, index=2, position=2, status="revising"))
    s_ok = db.save(Slide(project_id=p_gen.id, index=3, position=3, status="approved"))
    in_flight = [db.save(Version(slide_id=s_busy.id, project_id=p_gen.id, lineage="A", status=st))
                 for st in ("queued", "generating", "qa", "repairing")]
    ready = db.save(Version(slide_id=s_ok.id, project_id=p_gen.id, lineage="B", status="ready", score=8.0))

    runner.recover_interrupted()

    for v in in_flight:
        after = db.get(Version, v.id)
        assert after.status == "failed" and after.error == "Interrupted by server restart" and after.stage_note == ""
    assert db.get(Version, ready.id).status == "ready", "a finished version must not be touched"
    assert db.get(Slide, s_busy.id).status == "error" and db.get(Slide, s_rev.id).status == "error"
    assert db.get(Slide, s_ok.id).status == "approved"
    # a deck that was mid-generation still has usable slides: it goes back to review, not to an error
    assert db.get(Project, p_gen.id).status == "reviewing" and db.get(Project, p_gen.id).stage_note == ""
    assert db.get(Project, p_plan.id).status == "error" and "re-upload" in db.get(Project, p_plan.id).error
    assert db.get(Project, p_done.id).status == "complete"


def test_recover_interrupted_is_idempotent():
    p = db.save(Project(name="twice", filename="d.pptx", status="ingesting"))
    runner.recover_interrupted()
    first = db.get(Project, p.id).status
    runner.recover_interrupted()
    assert db.get(Project, p.id).status == first == "error"


# ------------------------------------------------------------------ item 9: small ones
def test_the_job_registry_does_not_keep_a_key_per_project_forever():
    async def go():
        for i in range(5):
            await runner.jobs.spawn(f"p{i}", asyncio.sleep(0))
        assert runner.jobs.tasks == {}, runner.jobs.tasks
        assert not runner.jobs.busy("p0")

    asyncio.run(go())


def test_the_criterion_list_comes_from_the_prompt_not_a_copy():
    from app import skillpack
    from app.pipeline import prompts

    keys = skillpack.criteria()
    md = skillpack.read("critic.md")
    assert set(keys) == set(skillpack.CRITERIA_FALLBACK), keys
    for k in keys:
        assert f'"{k}"' in md
    assert list(prompts.critic_schema()["properties"]["scores"]["properties"]) == list(keys)


@pytest.mark.parametrize("schema,name", [("PLAN_SCHEMA", "plan"), ("JUDGE_SCHEMA", "judge"), ("AB_SCHEMA", "ab")])
def test_every_json_stage_has_a_schema_that_matches_its_prompt(schema, name):
    from app.pipeline import prompts

    s = getattr(prompts, schema)
    assert s["type"] == "object" and s["required"] and s["additionalProperties"] is False
    assert set(s["required"]) <= set(s["properties"]), name
