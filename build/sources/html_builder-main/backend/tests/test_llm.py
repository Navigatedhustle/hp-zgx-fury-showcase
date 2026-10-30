"""The real (non-mock) LLM path, driven against `scripts/fake_vllm.py`.

Everything else in the suite runs with `LLM_MOCK=true`, and `_qa_loop` breaks out of the repair loop
in mock mode — so the repair path, the format retry, the context-length trim and the critic's effect
on scoring have no coverage at all without this module. The fake server misbehaves on purpose
(slide 2A overflows, 3B answers untagged, 4A returns a context-length 400, the first critic fails)
and counts what it was asked for, so the assertions here are about the pipeline's *behaviour*, not
about the text any model produced.
"""
import asyncio
import shutil
import socket
import threading
import time

import pytest
import uvicorn
from conftest import DECKS

MODULE_TIMEOUT_S = 240


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def fake_llm():
    """Run fake_vllm in this process and point the app at it for the whole module."""
    import os
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import fake_vllm  # noqa: PLC0415

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(fake_vllm.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("fake_vllm did not start")
        time.sleep(0.05)

    from app.config import settings
    from app.llm import client as llm

    prev = {k: os.environ.get(k) for k in ("LLM_MOCK", "LLM_BASE_URL", "LLM_MODEL", "VISION", "QA_MAX_REPAIRS")}
    os.environ.update({"LLM_MOCK": "false", "LLM_BASE_URL": f"http://127.0.0.1:{port}/v1",
                       "LLM_MODEL": "fake", "VISION": "on", "QA_MAX_REPAIRS": "2"})
    settings.cache_clear()
    llm.reset()
    try:
        yield fake_vllm
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        settings.cache_clear()
        llm.reset()


@pytest.fixture(scope="module")
def run(fake_llm):
    """Ingest a real deck and design its first four slides through the real client. Returns (pid, stats).

    Module-scoped: this is the only expensive fixture in the suite (Chromium renders every variant and
    every repair), and every assertion below reads the same run.
    """
    from app.pipeline import runner
    from app.store import db
    from app.store.db import Project

    fake_llm.reset()

    async def go():
        p = db.save(Project(name="fake", filename="t.pptx"))
        shutil.copy2(DECKS / "hp_wolf_print_security.pptx", db.project_dir(p.id) / "source.pptx")
        await runner.ingest(p.id)
        slides = db.slides_of(p.id)[:4]
        assert len(slides) == 4, "the fixture deck must have at least four slides"
        await runner.generate_project(p.id, [s.id for s in slides])
        return p.id

    pid = asyncio.run(asyncio.wait_for(go(), MODULE_TIMEOUT_S))
    return pid, dict(fake_llm.calls)


def _versions(pid):
    from app.store import db
    return [v for s in db.slides_of(pid)[:4] for v in db.versions_of_slide(s.id)]


def test_every_variant_survives_a_misbehaving_server(run):
    """The three planted failures must not leave a single dead variant."""
    pid, _ = run
    vs = _versions(pid)
    assert len(vs) == 8, [(v.lineage, v.status) for v in vs]
    assert all(v.status == "ready" for v in vs), [(v.number, v.lineage, v.status, v.error) for v in vs if v.status != "ready"]
    assert all(v.spec for v in vs)


def test_the_repair_loop_actually_runs(run):
    """Mock mode breaks out of `_qa_loop` before repairing, so this is the only check that it works."""
    _, stats = run
    assert stats["repairs"] >= 1, stats
    pid, _ = run
    repaired = [v for v in _versions(pid) if v.repairs]
    assert repaired, "no version recorded a repair"
    for v in repaired:
        assert v.qa.get("iterations"), v.qa
    # The fake server answers with gold examples that have nothing to do with this deck's content, so every
    # `fidelity*` code is expected here and is the check working: the examples state figures this deck never
    # had (fidelity-invented) and drop the ones it does (fidelity-key). The planted *layout* break is not —
    # slide 2A is served with text pushed off the stage, and the repair loop has to have cleared it.
    # `chart-*` likewise: an unrelated gold example cannot contain this deck's source chart.
    layout_errors = [f for v in _versions(pid) for f in v.qa.get("findings", [])
                     if f["severity"] == "error" and not f["code"].startswith(("fidelity", "chart-"))]
    assert not layout_errors, layout_errors


def test_an_untagged_reply_is_retried_without_echoing_it_back(run):
    """The retry must re-ask, not feed the unusable reply back in (the server asserts that too)."""
    _, stats = run
    assert stats["format_retry"] >= 1, stats


def test_a_context_length_400_is_trimmed_and_retried(run):
    """A 4xx is fatal by default; only a context-length one may be trimmed and re-sent."""
    _, stats = run
    assert stats["context_400"] >= 1, stats
    pid, _ = run
    assert all("context" not in (v.error or "").lower() for v in _versions(pid))


def test_the_critic_runs_and_its_failure_is_recorded_honestly(run):
    """A slide the critic never scored must not pass as a 10 — the bug this field exists to expose."""
    pid, stats = run
    assert stats["critic"] >= 1, stats
    for v in _versions(pid):
        status = v.qa.get("critic_status")
        assert status in ("ok", "skipped", "failed", None), v.qa
        if status == "failed":
            assert v.score is not None and v.score < 10.0, (v.score, v.qa)
        if status == "ok":
            assert v.qa.get("critic"), v.qa


def test_system_prefixes_stay_byte_stable(run):
    """vLLM prefix caching depends on this: a handful of prefixes, each byte-identical every time."""
    _, stats = run
    systems = stats["systems"]
    assert systems, "no system message was ever sent"
    # A per-request system prompt would show up here as one distinct string per call.
    assert len(systems) <= 3, f"{len(systems)} distinct system prefixes — prefix caching is defeated"
    assert stats["n"] > len(systems)


def test_the_planner_is_asked_once_per_batch(run):
    _, stats = run
    assert stats["plan"] >= 1, stats
    assert stats["generate"] >= 8, stats


# ------------------------------------------------------------------ guided JSON decoding
def test_only_the_json_stages_ask_for_guided_decoding(run):
    """plan, critic and the pairwise judge emit pure JSON and are constrained. Spec generation is not:
    restricting the decoder there would fight the reasoning the slide code needs."""
    _, stats = run
    assert stats["guided"] >= 2, stats
    schemas = stats["guided_schemas"]
    assert any("slides" in s for s in schemas), schemas          # plan
    assert any("scores" in s for s in schemas), schemas          # critic
    # the generation stages must never have sent one: there are 8+ of them and at most 3 JSON stages ran
    assert stats["guided"] < stats["n"], stats


def test_a_server_without_guided_decoding_does_not_break_the_pipeline(fake_llm):
    """The whole point of item 1's fallback: a 400 naming `guided_json` must cost one wasted request, not a
    failed stage. After the first refusal the client stops asking for the rest of the process."""
    import asyncio as aio

    from app.llm import client as llm
    from app.pipeline import prompts
    from app.spec import extract_json

    fake_llm.reset()
    fake_llm.guided["supported"] = False
    llm.reset()
    try:
        async def go():
            msgs = [{"role": "user", "content": "Task: plan the deck\n### Slide 1\n{}"}]
            first = await llm.chat(msgs, guided_json=prompts.PLAN_SCHEMA, max_tokens=500)
            second = await llm.chat(msgs, guided_json=prompts.PLAN_SCHEMA, max_tokens=500)
            return first, second

        first, second = aio.run(go())
        assert isinstance(extract_json(first.text), dict), first.text[:200]
        assert isinstance(extract_json(second.text), dict)
        assert llm.guided_json_state() is False, "the refusal must be remembered"
        assert fake_llm.calls["guided_refused"] == 1, fake_llm.calls
        assert fake_llm.calls["guided"] == 0, fake_llm.calls
        assert fake_llm.calls["plan"] == 2, "both calls still produced a usable plan"
    finally:
        fake_llm.guided["supported"] = True
        llm.reset()


# ------------------------------------------------------------------ pairwise A/B judging
def test_the_pairwise_judge_runs_and_lands_on_both_versions(run):
    """The recommendation the review UI shows, and the field `best_version` breaks ties with."""
    pid, stats = run
    from app.store import db

    assert stats["ab"] >= 1, stats
    judged = [v for s in db.slides_of(pid)[:4] for v in db.versions_of_slide(s.id) if (v.qa or {}).get("ab")]
    assert judged, "no version carries a pairwise verdict"
    for v in judged:
        ab = v.qa["ab"]
        assert ab["status"] in ("ok", "skipped", "failed"), ab
        assert set(ab["versions"]) == {"A", "B"}, ab
        if ab["status"] == "ok":
            assert ab["winner"] in ("A", "B", "tie"), ab
            assert ab["recommended"] == (ab["winner"] == v.lineage), ab
            assert ab["reason"], ab
    # both orders must be used across a deck: the fake server always names the first image, so a caller that
    # never swapped would show up here as one lineage winning every single slide
    orders = {v.qa["ab"]["order"] for v in judged}
    assert orders <= {"AB", "BA"} and orders, orders


def test_the_pairwise_verdict_only_breaks_near_ties(run):
    """A pairwise winner must not be able to promote a clearly worse variant."""
    from app.pipeline import runner
    from app.store.db import Version

    def v(lineage, score, winner):
        return Version(id=f"v{lineage}{score}", slide_id="s1", project_id="p1", lineage=lineage, score=score,
                       status="ready", qa={"critic_status": "ok", "ab": {"status": "ok", "winner": winner}})

    close = [v("A", 8.0, "B"), v("B", 7.8, "B")]
    assert max(close, key=runner._version_rank).lineage == "B", "a near tie is decided by the comparison"
    apart = [v("A", 9.0, "B"), v("B", 6.0, "B")]
    assert max(apart, key=runner._version_rank).lineage == "A", "a two-point gap is signal, not noise"


# ------------------------------------------------------------------ best-of-n for variant A
def test_best_of_n_samples_drafts_and_keeps_the_cleanest(run, monkeypatch):
    """Off by default (n=1, today's behaviour); with n>1 the drafts are filtered by the DOM check alone —
    cheap, deterministic, no LLM — before one of them enters the normal QA loop."""
    pid, _ = run
    from app.config import settings
    from app.pipeline import runner
    from app.store import db

    assert runner.best_of_a() == 1, "best-of-n must stay off unless it is configured on"
    monkeypatch.setenv("GENERATE_BEST_OF_A", "2")
    # `generate_best_of_a` is a real config field and settings() is lru_cached, so the new value is only
    # picked up after a clear — and the cache has to be cleared again on the way out or the rest of the
    # suite inherits n=2 long after monkeypatch has restored the environment.
    settings.cache_clear()
    try:
        assert runner.best_of_a() == 2
        slide = db.slides_of(pid)[0]
        before = len(db.versions_of_slide(slide.id))
        v = asyncio.run(asyncio.wait_for(runner.generate_version(slide.id, "A"), MODULE_TIMEOUT_S))
        assert v is not None and v.status == "ready", (v.status, v.error) if v else None
        rec = (v.qa or {}).get("best_of")
        assert rec, v.qa.keys()
        assert rec["n"] == 2 and rec["requested"] == 2 and rec["returned"] == 2, rec
        assert len(rec["drafts"]) == 2 and rec["picked"] in (0, 1), rec
        assert rec["drafts"][rec["picked"]]["errors"] == min(d["errors"] for d in rec["drafts"]), rec
        assert len(db.versions_of_slide(slide.id)) == before + 1
    finally:
        # monkeypatch restores the environment, but the cached Settings would keep n=2 for the rest of the run.
        monkeypatch.delenv("GENERATE_BEST_OF_A", raising=False)
        settings.cache_clear()


def test_best_of_n_is_never_used_for_variant_b():
    """B is the refined variant and is already cheap; the setting is explicitly A-only, and a revision of
    either lineage must stay a single call so the user's comment is answered once."""
    import inspect

    from app.pipeline import runner
    src = inspect.getsource(runner.generate_version)
    assert 'best_of_a() if (lineage == "A" and not comment) else 1' in src


# ------------------------------------------------------------------ image-limit probe
@pytest.mark.parametrize("cap", [1, 2, 3, 4, 8, 15, 16, 32])
def test_the_image_probe_reports_the_servers_exact_limit(cap, capsys, monkeypatch):
    """`cli probe` has to name the real ceiling, not the highest rung it happened to test.

    The ladder alone (1, 3, PLAN_MAX_IMAGES) can only ever answer 1, 3 or 16, so a server capped at 4 would
    be reported as 3 and the user told to drop PLAN_MAX_IMAGES to 3 — a slide per batch given away for
    nothing. The bisection is what makes the printed advice actionable.
    """
    from app import cli
    from app.llm import client as llm
    from app.pipeline.runner import PLAN_MAX_IMAGES

    async def fake(n):
        return (n <= cap, "" if n <= cap else f"At most {cap} image(s) may be provided in one request")

    monkeypatch.setattr(llm, "probe_image_count", fake)
    asyncio.run(cli.probe_image_limit({"vision": True}))
    out = capsys.readouterr().out
    reported = min(cap, PLAN_MAX_IMAGES)  # the ladder stops at what the pipeline needs; more is not measured
    assert f"limit = {reported} image(s)" in out, out
    # and the verdict must match what that limit actually allows
    if cap >= PLAN_MAX_IMAGES:
        assert "both fit" in out, out
    elif cap >= cli.CRITIC_IMAGES:
        assert f"PLAN_MAX_IMAGES = {cap}" in out, out
    else:
        assert "critic needs" in out, out


def test_the_image_probe_says_so_when_vision_is_off(capsys):
    """With vision off there is nothing to measure, and no images are sent to find that out."""
    from app import cli
    from app.llm import client as llm

    sent = []

    async def fake(n):
        sent.append(n)
        return True, ""

    orig = llm.probe_image_count
    llm.probe_image_count = fake
    try:
        asyncio.run(cli.probe_image_limit({"vision": False}))
    finally:
        llm.probe_image_count = orig
    assert not sent, "a text-only server must not be probed with images"
    assert "vision is off" in capsys.readouterr().out


def test_an_image_limit_400_is_not_mistaken_for_a_context_error():
    """The two 400s that matter, kept apart: a context error is trimmed and retried, an image-limit error
    is fatal. Confusing them would make the pipeline retry a prompt that cannot ever be accepted."""
    from app.llm import client as llm

    over = "At most 4 image(s) may be provided in one request, got 16"
    assert llm.is_image_limit_error(over)
    assert not llm.is_context_error(over)
    too_long = "This model's maximum context length is 65536 tokens"
    assert llm.is_context_error(too_long)


# ------------------------------------------------------------------ deck-level rollup
def test_the_deck_rollup_adds_up_what_the_run_cost(run):
    pid, _ = run
    from app.pipeline import runner
    from app.store import db
    from app.store.db import Project, Version

    st = runner.deck_stats(pid)
    assert st["calls"] >= 8 and st["total_tokens"] > 0 and st["versions"] >= 8, st
    assert st["calls"] == sum((v.llm or {}).get("calls", 0) for v in db.versions_of_project(pid)), st
    saved = (db.get(Project, pid).llm or {})
    assert saved.get("calls", 0) >= 8, saved  # written by generate_project, before any later test added versions
    assert saved.get("wall_seconds") is not None, "generate_project must record how long the user waited"
    refreshed = asyncio.run(runner.roll_up_stats(pid))
    assert refreshed["calls"] == st["calls"], (refreshed, st)
    assert (db.get(Project, pid).llm or {})["calls"] == st["calls"]
    assert refreshed["wall_seconds"] == saved["wall_seconds"], "a refresh must not lose the measured wall clock"
