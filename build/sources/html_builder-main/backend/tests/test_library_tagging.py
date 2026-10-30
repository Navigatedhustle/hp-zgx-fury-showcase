"""Library tagging: favourite → review-model tags and summary, user locks, the vocabulary and its endpoints."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.config import settings
from app.library import common, tagging, taxonomy
from app.llm.client import LLMResult
from app.skillpack import review_system_prompt
from app.store import db
from app.store.db import LibDeck, LibSlide, LibTag


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def reindexed(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(tagging.search, "reindex", lambda ids: calls.append(list(ids)))
    return calls


def _deck(**kw) -> LibDeck:
    return db.save(LibDeck(**{"project": "Fury launch", "title": "ZGX Fury briefing", "filename": "fury.pptx",
                              "status": "ready", "slide_count": 3, **kw}))


def _slide(d: LibDeck, index: int = 2, **kw) -> LibSlide:
    content = {"index": index, "title": kw.get("title", "Generative AI at the edge"),
               "texts": [{"kind": "body", "paragraphs": [{"text": "Edge computing runs inference next to the data."},
                                                          {"text": "Security and zero trust by default."}]}]}
    return db.save(LibSlide(**{"deck_id": d.id, "index": index, "title": "Generative AI at the edge",
                               "text": "Edge computing runs inference next to the data.\nSecurity and zero trust by default.",
                               "content": content, **kw}))


def _wait(slide_id: str, timeout: float = 10.0) -> LibSlide:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = db.get(LibSlide, slide_id)
        if s.ai_status in ("done", "error"):
            return s
        time.sleep(0.05)
    raise AssertionError(f"slide {slide_id} still {db.get(LibSlide, slide_id).ai_status}")


def _real_llm(monkeypatch, reply, *, vision: bool = False) -> list[list[dict]]:
    """Leave mock mode and answer every llm.chat with `reply` (a dict → JSON, or an exception to raise)."""
    seen: list[list[dict]] = []

    async def chat(messages, **kw):
        seen.append(messages)
        assert kw["role"] == "review" and kw["stage"] == tagging.STAGE and kw["guided_json"]["type"] == "object"
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=json.dumps(reply), model="fake")

    monkeypatch.setattr(tagging.llm, "chat", chat)
    monkeypatch.setattr(tagging.llm, "vision_enabled", lambda: asyncio.sleep(0, result=vision))
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    return seen


@pytest.fixture
def restore_mock(monkeypatch):
    yield
    monkeypatch.setenv("LLM_MOCK", "true")
    settings.cache_clear()


# ------------------------------------------------------------------ normalise

def test_normalise_and_aliases():
    m = taxonomy.alias_map()
    assert taxonomy.normalise("GenAI", m) == "generative-ai"
    assert taxonomy.normalise("gen-ai", m) == "generative-ai"
    assert taxonomy.normalise("  Gen AI ", m) == "generative-ai"
    assert taxonomy.normalise("Workstation", m) == taxonomy.normalise("workstations", m) == "workstations"
    assert taxonomy.normalise("Data Centres", m) == "data-center"
    assert taxonomy.normalise("KPIs", m) == "kpi"
    assert taxonomy.normalise("Strategies", m) == "strategy"
    assert taxonomy.normalise("Analytics Pipelines", m) == "analytics-pipelines"   # unknown: clean, not mangled
    assert taxonomy.normalise("R&D", m) == "innovation"
    assert taxonomy.normalise("", m) == ""
    assert taxonomy.base_form("analytics") == "analytics" and taxonomy.base_form("gpus") == "gpu"


def test_seed_is_idempotent_and_respects_deletes():
    taxonomy.ensure_seeded()
    n = len(taxonomy.all_tags())
    assert n >= 60 and taxonomy.seed() == 0
    with db.session() as s:
        s.delete(s.get(LibTag, "retail"))
        s.commit()
    assert taxonomy.seed() == 0 and db.get(LibTag, "retail") is None   # a deleted seed tag stays deleted
    db.save(LibTag(slug="retail", label="Retail", facet="topic"))


def test_taxonomy_endpoint(client):
    t = client.get("/api/library/taxonomy").json()
    assert "data-chart" in t["slide_types"] and "customer" in t["facets"] and "metric" in t["entity_types"]


# ------------------------------------------------------------------ mock flow

def test_favourite_triggers_tagging(client, reindexed):
    d = _deck()
    s = _slide(d)
    r = client.patch(f"/api/library/slides/{s.id}", json={"favourite": True}).json()
    assert r["favourite"] and r["favourited_at"] and r["ai_status"] in ("pending", "done")
    done = _wait(s.id)
    assert done.ai_status == "done", done.ai_error
    assert "generative-ai" in done.tags and "edge-computing" in done.tags and len(done.tags) <= 4
    assert done.summary.startswith("Generative AI at the edge")
    assert done.slide_type in taxonomy.SLIDE_TYPES
    assert [s.id] in reindexed


def test_user_edits_survive_retag(client, reindexed):
    d = _deck()
    s = _slide(d)
    r = client.patch(f"/api/library/slides/{s.id}", json={"tags": ["Gen AI", "My Own Topic"], "summary": "Mine."}).json()
    assert r["tags"] == ["generative-ai", "my-own-topic"] and r["tags_user"] and r["summary_user"]
    assert db.get(LibTag, "my-own-topic").approved
    client.post(f"/api/library/slides/{s.id}/retag")
    done = _wait(s.id)
    assert done.ai_status == "done"
    assert done.tags == ["generative-ai", "my-own-topic"] and done.summary == "Mine."
    assert done.slide_type   # the unlocked fields were still written
    # an empty summary hands it back to the model
    r = client.patch(f"/api/library/slides/{s.id}", json={"summary": ""}).json()
    assert not r["summary_user"]
    assert client.patch(f"/api/library/slides/{s.id}", json={"slide_type": "nonsense"}).status_code == 400


def test_bulk(client, reindexed):
    d = _deck()
    a, b = _slide(d, 1), _slide(d, 2, tags=["security"])
    r = client.post("/api/library/slides/bulk", json={"slide_ids": [a.id, b.id], "add_tags": ["roadmap"],
                                                      "remove_tags": ["Cybersecurity"]}).json()
    assert r["updated"] == 2
    assert db.get(LibSlide, a.id).tags == ["roadmap"] and db.get(LibSlide, b.id).tags == ["roadmap"]
    assert db.get(LibSlide, b.id).tags_user
    r = client.post("/api/library/slides/bulk", json={"slide_ids": [a.id, b.id], "favourite": True}).json()
    assert r["updated"] == 2
    for x in (a, b):
        got = _wait(x.id)
        assert got.favourite and got.ai_status == "done" and got.tags == ["roadmap"]   # locked by the bulk edit


def test_tag_all(client, reindexed):
    d = _deck()
    ids = [_slide(d, i).id for i in (1, 2, 3)]
    assert client.post(f"/api/library/decks/{d.id}/tag-all").json() == {"queued": 3}
    assert all(_wait(i).ai_status == "done" for i in ids)
    assert client.post("/api/library/decks/nope/tag-all").status_code == 404


# ------------------------------------------------------------------ vocabulary

def test_tags_crud_merge_approve_delete(client, reindexed):
    d = _deck()
    s1 = _slide(d, 1, tags=["cloud", "storage"])
    s2 = _slide(d, 2, tags=["hybrid-cloud"], tags_user=True)
    assert client.post("/api/library/tags", json={"label": "Fury Program", "facet": "project"}).json()["slug"] == "fury-program"
    assert client.post("/api/library/tags", json={"label": "fury programs"}).status_code == 409
    assert client.post("/api/library/tags", json={"label": "x", "facet": "nope"}).status_code == 400
    t = client.patch("/api/library/tags/fury-program", json={"label": "Fury programme", "aliases": ["ZGX Fury"]}).json()
    assert t["label"] == "Fury programme" and t["aliases"] == ["zgx-fury"]
    assert client.patch("/api/library/tags/fury-program", json={"aliases": ["Storage"]}).status_code == 409

    # merge rewrites every slide and keeps the old spelling as an alias
    m = client.post("/api/library/tags/merge", json={"from": ["hybrid-cloud"], "into": "cloud"}).json()
    assert m["slug"] == "cloud" and "hybrid-cloud" in m["aliases"] and m["count"] >= 2
    assert db.get(LibTag, "hybrid-cloud") is None
    assert db.get(LibSlide, s1.id).tags == ["cloud", "storage"] and db.get(LibSlide, s2.id).tags == ["cloud"]
    assert taxonomy.normalise("Hybrid Cloud") == "cloud"
    assert s2.id in sum(reindexed, [])

    # approve: applied where suggested, except on hand-tagged slides
    db.save(LibTag(slug="quantum-computing", label="Quantum computing", approved=False))
    db.update(LibSlide, s1.id, suggested=["quantum-computing"])
    db.update(LibSlide, s2.id, suggested=["quantum-computing"])
    a = client.post("/api/library/tags/quantum-computing/approve").json()
    assert a["approved"] and a["count"] == 1
    assert "quantum-computing" in db.get(LibSlide, s1.id).tags and db.get(LibSlide, s1.id).suggested == []
    assert "quantum-computing" not in db.get(LibSlide, s2.id).tags and db.get(LibSlide, s2.id).suggested == []

    # delete removes it from every slide
    r = client.delete("/api/library/tags/storage").json()
    assert r["slides"] >= 1 and db.get(LibTag, "storage") is None
    assert "storage" not in db.get(LibSlide, s1.id).tags
    db.save(LibTag(slug="storage", label="Storage", facet="topic"))

    listed = {t["slug"]: t for t in client.get("/api/library/tags").json()}
    assert listed["cloud"]["count"] >= 2 and listed["fury-program"]["facet"] == "project"


# ------------------------------------------------------------------ the real model path

def test_model_reply_validated(monkeypatch, restore_mock, reindexed, tmp_path):
    d = _deck()
    s = _slide(d, 2, tags_user=True, tags=["security"])
    png = common.render_path(d.id, 2)
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), "white").save(png)
    reply = {"summary": "This slide shows edge inference keeping data local, " + "cutting latency " * 30,
             "slide_type": "Architecture Diagram",
             "topic_tags": ["gen-ai", "edge-computing", "made-up-topic"],
             "entities": [{"name": "ZGX Fury", "type": "product"}, {"name": "zgx fury", "type": "product"},
                          {"name": "the cloud", "type": "nonsense"}],
             "new_tag_suggestions": ["Sovereign AI", "Zero Trust", "third", "fourth"]}
    seen = _real_llm(monkeypatch, reply, vision=True)
    asyncio.run(tagging.tag_slide(s.id))
    got = db.get(LibSlide, s.id)
    assert got.ai_status == "done", got.ai_error
    assert got.tags == ["security"]                        # locked: the model's tags were not applied
    assert got.slide_type == "architecture-diagram"
    assert got.entities == [{"name": "ZGX Fury", "type": "product"}]
    assert got.suggested == ["made-up-topic", "sovereign-ai"]   # ≤2, never applied
    assert db.get(LibTag, "sovereign-ai").approved is False and db.get(LibTag, "sovereign-ai").label == "Sovereign AI"
    assert got.summary.startswith("Edge inference") and len(got.summary.split()) <= 40
    msgs = seen[0]
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == review_system_prompt()
    user = msgs[1]["content"]
    assert user[0]["type"] == "image_url" and "generative-ai — Generative AI" in user[1]["text"]
    assert "Fury launch" in user[1]["text"] and "Edge computing runs inference" in user[1]["text"]

    # unlocked: the validated tags land
    s2 = _slide(d, 3)
    asyncio.run(tagging.tag_slide(s2.id))
    assert db.get(LibSlide, s2.id).tags == ["generative-ai", "edge-computing", "zero-trust"]
    assert seen[1][0]["content"] == seen[0][0]["content"]   # the system prefix is byte-identical
    assert "sovereign-ai" not in tagging.schema(taxonomy.approved_slugs())["properties"]["topic_tags"]["items"]["enum"]


def test_model_failure_recorded(monkeypatch, restore_mock, reindexed):
    s = _slide(_deck())
    seen = _real_llm(monkeypatch, RuntimeError("GB300 unreachable"))
    asyncio.run(tagging.tag_slide(s.id))
    got = db.get(LibSlide, s.id)
    assert got.ai_status == "error" and "GB300 unreachable" in got.ai_error
    assert len(seen) == tagging.ATTEMPTS


def test_recover_interrupted(monkeypatch):
    s = _slide(_deck(), ai_status="pending")
    queued: list[str] = []
    monkeypatch.setattr(tagging, "_kick", lambda: queued.extend(tagging._queue))
    monkeypatch.setattr(tagging, "_queue", [])
    assert tagging.recover_interrupted() >= 1 and s.id in queued
