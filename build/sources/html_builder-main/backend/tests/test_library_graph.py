"""Library knowledge graph: node ids, edges, degrees, min_shared pruning, scope, superseded decks, entities."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlmodel import SQLModel

from app import main
from app.library import graph as G
from app.store import db
from app.store.db import LibDeck, LibSlide, LibTag


@pytest.fixture()
def lib(tmp_path):
    """A fresh, empty database: the rest of the suite shares one, and these assert exact graphs."""
    eng = create_engine(f"sqlite:///{tmp_path / 'lib.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _wal(conn, _):  # noqa: ANN001
        conn.execute("PRAGMA journal_mode=WAL")

    SQLModel.metadata.create_all(eng)
    old = db._engine
    db._engine = eng
    try:
        yield eng
    finally:
        db._engine = old
        eng.dispose()


def deck(project: str, title: str, **kw) -> LibDeck:
    return db.save(LibDeck(project=project, title=title, filename=f"{title}.pptx", status="ready", **kw))


def slide(d: LibDeck, index: int, title: str, **kw) -> LibSlide:
    return db.save(LibSlide(deck_id=d.id, index=index, title=title, text=f"{title} body", **kw))


@pytest.fixture()
def corpus(lib):
    db.save(LibTag(slug="generative-ai", label="Generative AI"))
    db.save(LibTag(slug="security", label="Security", facet="topic"))
    a = deck("Contoso", "AI pitch", deck_date=datetime(2025, 6, 1))
    b = deck("Fabrikam", "Print pitch")
    x = {
        "a1": slide(a, 1, "GPU spend", favourite=True, tags=["generative-ai", "security"], summary="Spend.",
                    entities=[{"name": "ZGX  Fury", "type": "product"}, {"name": "Contoso", "type": "customer"}]),
        "a2": slide(a, 2, "Cost table", favourite=True, tags=["generative-ai"],
                    entities=[{"name": "zgx fury", "type": "product"}]),
        "b1": slide(b, 1, "Print security", favourite=True, tags=["generative-ai"],
                    entities=[{"name": "ZGX Fury", "type": "product"}], content={"source_number": 3}),
        "b2": slide(b, 2, "Rollout", tags=["security"], entities=[{"name": "Contoso", "type": "customer"}]),
    }
    return a, b, x


def test_shape_ids_edges_degrees(corpus):
    a, b, x = corpus
    g = G.build_graph("favourites", None, 2).out()
    ids = [n["id"] for n in g["nodes"]]
    assert ids == sorted(ids)
    assert set(ids) == {f"s:{x['a1'].id}", f"s:{x['a2'].id}", f"s:{x['b1'].id}", "p:Contoso", "p:Fabrikam",
                        "t:generative-ai", "e:zgx fury"}   # security / Contoso: one favourite each → pruned
    edges = {(e["source"], e["target"], e["type"]) for e in g["edges"]}
    assert (f"s:{x['a1'].id}", "p:Contoso", "in") in edges
    assert (f"s:{x['b1'].id}", "t:generative-ai", "tagged") in edges
    assert (f"s:{x['a2'].id}", "e:zgx fury", "mentions") in edges
    assert all(e["target"] in ids and e["source"] in ids for e in g["edges"])
    assert len(edges) == len(g["edges"]) == 3 + 3 + 3
    nodes = {n["id"]: n for n in g["nodes"]}
    assert nodes["t:generative-ai"]["degree"] == 3 and nodes["t:generative-ai"]["label"] == "Generative AI"
    assert nodes["p:Contoso"]["degree"] == 2 and nodes["p:Contoso"]["data"]["decks"] == 1
    assert nodes[f"s:{x['a1'].id}"]["degree"] == 3
    s = nodes[f"s:{x['b1'].id}"]
    assert s["type"] == "slide" and s["label"] == "Print security"
    assert s["data"]["deck"] == "Print pitch" and s["data"]["project"] == "Fabrikam" and s["data"]["number"] == 3
    assert s["data"]["thumb"].startswith(f"/api/library/slides/{x['b1'].id}/image?thumb=true")
    assert nodes[f"s:{x['a1'].id}"]["data"]["deck_date"].startswith("2025-06-01")
    assert g["stats"] == {"slides": 3, "projects": 2, "tags": 1, "entities": 1}


def test_entity_normalisation(corpus):
    g = G.build_graph("favourites", None, 1)
    e = g.by_id()["e:zgx fury"]
    assert e.label == "ZGX Fury"            # most common spelling (whitespace collapsed); "zgx fury" once
    assert e.data["type"] == "product" and e.data["slides"] == 3
    assert G.entity_key("  HP\tInc ") == "hp inc" == G.entity_key("hp INC")
    assert G.entity_key("Straße") == G.entity_key("STRASSE")   # casefold, not lower


def test_min_shared_pruning(corpus):
    one = G.build_graph("favourites", None, 1)
    assert {"t:security", "e:contoso"} <= set(one.by_id())
    four = G.build_graph("favourites", None, 4)
    assert {n.type for n in four.nodes} == {"slide", "project"}   # projects always kept
    assert all(e.type == "in" for e in four.edges)


def test_scope_and_project(corpus):
    a, b, x = corpus
    every = G.build_graph("all", None, 2).by_id()
    assert f"s:{x['b2'].id}" in every and "t:security" in every and "e:contoso" in every
    only = G.build_graph("all", "Fabrikam", 1)
    assert {n.id for n in only.nodes if n.type == "project"} == {"p:Fabrikam"}
    assert only.stats["slides"] == 2


def test_superseded_excluded(corpus):
    a, b, x = corpus
    newer = deck("Contoso", "AI pitch v2", supersedes_id=a.id)
    a.superseded_by = newer.id
    db.save(a)
    g = G.build_graph("all", None, 1).by_id()
    assert f"s:{x['a1'].id}" not in g and f"s:{x['b1'].id}" in g
    assert "p:Contoso" not in g   # its only deck with slides is superseded


def test_deterministic_and_api(corpus):
    assert G.build_graph("all", None, 1).out() == G.build_graph("all", None, 1).out()
    with TestClient(main.app) as c:
        r = c.get("/api/library/graph", params={"scope": "all", "min_shared": 1})
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"nodes", "edges", "stats"} and body["stats"]["slides"] == 4
        assert body == G.build_graph("all", None, 1).out()
        assert c.get("/api/library/graph", params={"scope": "nope"}).status_code == 422
        assert c.get("/api/library/graph", params={"min_shared": 0}).status_code == 422
        empty = c.get("/api/library/graph", params={"project": "Nobody"}).json()
        assert empty == {"nodes": [], "edges": [], "stats": {"slides": 0, "projects": 0, "tags": 0, "entities": 0}}
