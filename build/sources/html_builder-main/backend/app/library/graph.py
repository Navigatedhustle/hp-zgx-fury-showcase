"""The library as a knowledge graph: slides linked to their project, their tags and the entities they mention.

One builder, two outputs: `GET /api/library/graph` (the Library's Graph tab) and the Obsidian vault
(`obsidian.py`), which renders the same `Graph` as Markdown notes so both show the same picture.

Node ids: `s:<slide id>`, `p:<project>`, `t:<tag slug>`, `e:<entity key>`. Edges point from the slide:
"in" (project), "tagged" (tag), "mentions" (entity). Decks are not nodes — a deck lives on its slides' data.
Tags and entities on fewer than `min_shared` slides are dropped with their edges, which is what keeps a few
hundred slides readable; projects are always kept. Superseded decks are left out. Everything is sorted, so the
same library gives the same graph (and the same vault, byte for byte).
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, Query
from sqlmodel import select

from ..store import db
from ..store.db import LibDeck, LibSlide, LibTag
from .schema import iso

router = APIRouter()

Scope = Literal["favourites", "all"]
NO_PROJECT = "No project"   # the label of the project node for decks filed under no project (id "p:")


@dataclass
class Node:
    id: str
    type: str                      # slide | project | tag | entity
    label: str
    degree: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def out(self) -> dict:
        return {"id": self.id, "type": self.type, "label": self.label, "degree": self.degree, "data": self.data}


@dataclass(frozen=True, order=True)
class Edge:
    source: str
    target: str
    type: str                      # in | tagged | mentions

    def out(self) -> dict:
        return {"source": self.source, "target": self.target, "type": self.type}


@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    # The rows behind the slide nodes, for renderers that need more than the API shape (obsidian.py).
    slides: dict[str, LibSlide] = field(default_factory=dict)
    decks: dict[str, LibDeck] = field(default_factory=dict)

    @property
    def stats(self) -> dict[str, int]:
        c = Counter(n.type for n in self.nodes)
        return {"slides": c["slide"], "projects": c["project"], "tags": c["tag"], "entities": c["entity"]}

    def by_id(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def out(self) -> dict:
        return {"nodes": [n.out() for n in self.nodes], "edges": [e.out() for e in self.edges], "stats": self.stats}


def entity_key(name: str) -> str:
    """The identity of an entity across slides: casefolded, whitespace collapsed ("HP  inc" = "hp inc")."""
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def _most_common(spellings: list[str]) -> str:
    """The most frequent spelling; ties go to the alphabetically first, so the label never flickers."""
    c = Counter(spellings)
    return min(c, key=lambda s: (-c[s], s))


def build_graph(scope: Scope = "favourites", project: str | None = None, min_shared: int = 2) -> Graph:
    min_shared = max(1, int(min_shared))
    with db.session() as s:
        decks = {d.id: d for d in s.exec(select(LibDeck)) if not d.superseded_by}
        if project is not None:
            decks = {i: d for i, d in decks.items() if (d.project or "").strip() == project.strip()}
        q = select(LibSlide).where(LibSlide.deck_id.in_(list(decks)))
        if scope == "favourites":
            q = q.where(LibSlide.favourite == True)  # noqa: E712 — SQL expression
        slides = sorted(s.exec(q), key=lambda x: x.id)
        tags = {t.slug: t for t in s.exec(select(LibTag))}

    nodes: dict[str, Node] = {}
    edges: set[Edge] = set()
    tag_slides: dict[str, set[str]] = defaultdict(set)
    ent_slides: dict[str, set[str]] = defaultdict(set)
    ent_names: dict[str, list[str]] = defaultdict(list)
    ent_types: dict[str, list[str]] = defaultdict(list)
    project_decks: dict[str, set[str]] = defaultdict(set)

    for sl in slides:
        d = decks[sl.deck_id]
        proj = (d.project or "").strip()
        sid, pid = f"s:{sl.id}", f"p:{proj}"
        v = iso(sl.updated_at)
        nodes[sid] = Node(sid, "slide", sl.title or f"Slide {sl.index}", data={
            "slide_id": sl.id, "deck_id": d.id, "deck": d.title or d.filename, "deck_date": iso(d.deck_date),
            "project": proj, "index": sl.index, "number": (sl.content or {}).get("source_number") or sl.index,
            "thumb": f"/api/library/slides/{sl.id}/image?thumb=true&v={v}",
            "summary": sl.summary, "slide_type": sl.slide_type, "favourite": sl.favourite,
        })
        project_decks[proj].add(d.id)
        edges.add(Edge(sid, pid, "in"))
        for slug in dict.fromkeys(t for t in (sl.tags or []) if isinstance(t, str) and t):
            tag_slides[slug].add(sl.id)
        for e in sl.entities or []:
            name = (e.get("name") if isinstance(e, dict) else e) or ""
            if not isinstance(name, str) or not (key := entity_key(name)):
                continue
            ent_names[key].append(re.sub(r"\s+", " ", name.strip()))
            if isinstance(e, dict) and e.get("type"):
                ent_types[key].append(str(e["type"]))
            ent_slides[key].add(sl.id)

    for proj, deck_ids in project_decks.items():
        nodes[f"p:{proj}"] = Node(f"p:{proj}", "project", proj or NO_PROJECT,
                                  data={"project": proj, "decks": len(deck_ids)})
    for slug, ids in tag_slides.items():
        if len(ids) < min_shared:
            continue
        t = tags.get(slug)
        nodes[f"t:{slug}"] = Node(f"t:{slug}", "tag", t.label if t else slug,
                                  data={"slug": slug, "facet": t.facet if t else "topic", "slides": len(ids)})
        edges |= {Edge(f"s:{i}", f"t:{slug}", "tagged") for i in ids}
    for key, ids in ent_slides.items():
        if len(ids) < min_shared:
            continue
        label = _most_common(ent_names[key])
        nodes[f"e:{key}"] = Node(f"e:{key}", "entity", label, data={
            "key": key, "name": label, "type": _most_common(ent_types[key]) if ent_types[key] else "",
            "slides": len(ids)})
        edges |= {Edge(f"s:{i}", f"e:{key}", "mentions") for i in ids}

    degree: Counter[str] = Counter()
    for e in edges:
        degree[e.source] += 1
        degree[e.target] += 1
    for n in nodes.values():
        n.degree = degree[n.id]
    return Graph(nodes=[nodes[k] for k in sorted(nodes)], edges=sorted(edges),
                 slides={x.id: x for x in slides}, decks={d.id: d for d in decks.values()
                                                         if d.id in {x.deck_id for x in slides}})


@router.get("/graph")
async def graph_endpoint(scope: Scope = "favourites", project: str | None = None,
                         min_shared: int = Query(default=2, ge=1, le=1000)) -> dict:
    """`{nodes: [{id, type, label, degree, data}], edges: [{source, target, type}], stats: {slides, projects, tags,
    entities}}` — see the module docstring for ids and edge types."""
    g = await asyncio.to_thread(build_graph, scope, project or None, min_shared)
    return g.out()
