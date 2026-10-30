"""The usage ledger: every model call is recorded, billed to its deck, and priced against the cloud."""
import asyncio

import pytest
from app import usage
from app.config import Role
from app.llm import client as llm
from app.store import db
from app.store.db import LlmCall, Project
from sqlmodel import delete

PRICES = {
    "as_of": "2026-01-01",
    "frontier": [{"id": "big", "name": "Big", "vendor": "X", "input": 10.0, "cached": 1.0, "output": 50.0}],
    "same_size": [{"match": ["model3"], "name": "Qwen", "input": 0.5, "cached": 0.1, "output": 2.0}],
}


@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setattr(usage, "pricing", lambda: PRICES)
    with db.session() as s:
        s.exec(delete(LlmCall))
        s.commit()
    yield
    with db.session() as s:
        s.exec(delete(LlmCall))
        s.commit()


def _row(**kw):
    base = dict(model="model3", role="author", stage="generate", prompt_tokens=1_000_000, completion_tokens=100_000,
                system_tokens=0, seconds=10.0)
    with db.session() as s:
        s.add(LlmCall(**{**base, **kw}))
        s.commit()


def test_unknown_cache_is_not_an_estimated_discount(ledger):
    _row(system_tokens=400_000)   # estimated prefix must never become measured/billable cache
    out = usage.summary()
    # 1M * $10 + 100k * $50; no assumed cache discount
    assert out["totals"]["costs"]["big"] == pytest.approx(15.0)
    assert out["totals"]["costs"][usage.SAME_SIZE] == pytest.approx(0.5 + 0.2)
    assert out["totals"]["cache_reported"] is False


def test_a_reported_cache_hit_outranks_the_estimate(ledger):
    _row(system_tokens=400_000, cached_tokens=0)
    assert usage.summary()["totals"]["costs"]["big"] == pytest.approx(15.0)


def test_an_unknown_model_has_no_same_size_price_and_says_so(ledger):
    _row(model="someone-else/model")
    out = usage.summary()
    assert out["totals"]["costs"][usage.SAME_SIZE] == 0
    assert out["same_size_unpriced_tokens"] == 1_100_000


def test_rollups_by_model_stage_and_deck(ledger):
    p = db.save(Project(name="Q3 review", filename="q3.pptx"))
    _row(project_id=p.id)
    _row(project_id=p.id, model="model2", role="review", stage="critic", prompt_tokens=5000, completion_tokens=200,
         images=3, seconds=2.0)
    out = usage.summary()
    assert out["totals"]["calls"] == 2 and out["totals"]["images"] == 3 and out["totals"]["decks"] == 1
    assert {m["model"] for m in out["models"]} == {"model3", "model2"}
    assert out["models"][0]["name"] == "Qwen" and out["models"][0]["tok_s"] == 10_000
    assert {s["stage"] for s in out["stages"]} == {"generate", "critic"}
    assert out["decks"][0]["title"] == "Q3 review" and out["decks"][0]["calls"] == 2
    assert len(out["daily"]) == 1


class _Usage:
    prompt_tokens, completion_tokens = 1200, 300
    prompt_tokens_details = type("D", (), {"cached_tokens": 800})()


class _Reply:
    usage = _Usage()
    choices = [type("C", (), {"finish_reason": "stop",
                              "message": type("M", (), {"content": "ok", "reasoning_content": None})()})()]


class _Client:
    def __init__(self):
        async def create(**kw):
            return _Reply()
        self.chat = type("X", (), {"completions": type("Y", (), {"create": staticmethod(create)})()})()


def test_chat_records_every_call_against_the_running_deck(ledger, monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda ep=None: _Client())
    msgs = [{"role": "system", "content": "x" * 3600},
            {"role": "user", "content": [llm._tiny_image_part(), {"type": "text", "text": "hi"}]}]

    async def job():
        await llm.chat(msgs, role=Role.review, stage="critic")

    async def main():
        tok = usage.current_project.set("p-deck")
        try:
            t = asyncio.create_task(job())   # what runner.jobs.spawn does
        finally:
            usage.current_project.reset(tok)
        await t

    asyncio.run(main())
    with db.session() as s:
        (c,) = list(s.exec(db.select(LlmCall)))
    assert (c.project_id, c.stage, c.role) == ("p-deck", "critic", "review")
    assert (c.prompt_tokens, c.completion_tokens, c.cached_tokens, c.images) == (1200, 300, 800, 1)
    assert c.system_tokens > 900


def test_missing_api_usage_is_counted_as_unknown_not_zero_measured_tokens(ledger):
    _row(usage_known=False,prompt_tokens=0,completion_tokens=0)
    out=usage.summary()
    assert out['unknown_usage_calls']==1
    assert out['totals']['calls']==0
