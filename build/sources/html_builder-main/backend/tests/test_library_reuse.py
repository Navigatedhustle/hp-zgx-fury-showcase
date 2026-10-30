"""The library inside the deck flows: stars on project slides, and slides inserted from the library."""
import asyncio
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import facts, main
from app.config import settings
from app.ingest.pptx_parse import parse_pptx
from app.library import common, ingest, reuse
from app.pipeline import prompts, runner
from app.store import db
from app.store.db import LibDeck, LibSlide, Project, Slide, Version

from conftest import DECKS

DECK = DECKS / "hp_wolf_print_security.pptx"
OTHER = DECKS / "hp_z_workstations_genai.pptx"   # slide 5 has a table, slide 6 a picture


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_library():
    def wipe():
        with db.session() as s:
            for m in (LibSlide, LibDeck):
                for o in s.exec(db.select(m)):
                    s.delete(o)
            s.commit()
        shutil.rmtree(common.library_dir(), ignore_errors=True)
    wipe()
    yield
    wipe()


def _settle(deck_id: str, tries: int = 400) -> LibDeck:
    for _ in range(tries):
        d = db.get(LibDeck, deck_id)
        if d is not None and d.status != "ingesting":
            return d
        time.sleep(0.05)
    raise AssertionError("library job never finished")


def _upload(client, path: Path = OTHER) -> dict:
    with path.open("rb") as f:
        r = client.post("/api/library/decks", files={"file": (path.name, f.read())}, data={"project": "Lib"})
    assert r.status_code == 200, r.text
    assert _settle(r.json()["id"]).status == "ready"
    return client.get(f"/api/library/decks/{r.json()['id']}").json()


def _converted(name: str = "Converted", path: Path = DECK) -> Project:
    p = db.save(Project(name=name, filename=path.name, status="ready", deck_title=name))
    pdir = db.project_dir(p.id)
    shutil.copy2(path, pdir / "source.pptx")
    deck = parse_pptx(pdir / "source.pptx", pdir / "assets", pdir / "renders")
    for sc in deck.slides:
        db.save(Slide(project_id=p.id, index=sc.index, position=sc.index, content=sc.model_dump(),
                      facts=facts.dump(facts.extract(sc.for_prompt(), prefix=f"s{sc.index}f"))))
    return p


def _composed(n: int = 3) -> Project:
    from app import compose
    p = db.save(Project(name="Typed", filename="", source="composed", status="ready", deck_title="Typed"))
    runner.replace_slides(p.id, [compose.blank(i, f"Typed {i}", [f"Line {i}"]) for i in range(1, n + 1)])
    return p


def _approve(p: Project, s: Slide, colour: str = "purple") -> Version:
    v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready", spec={}, qa={}))
    im = Image.new("RGB", (1600, 900), "white")
    ImageDraw.Draw(im).rectangle((100 + s.index * 40, 100, 900, 700), fill=colour)
    im.save(db.version_dir(p.id, v.id) / "shot_final.png")
    db.update(Slide, s.id, status="approved", approved_version_id=v.id)
    return v


def _star(client, sid: str, kind: str, fav: bool = True) -> dict:
    r = client.post("/api/library/project-favourite", json={"slide_id": sid, "kind": kind, "favourite": fav})
    assert r.status_code == 200, r.text
    return r.json()


def _links(client, pid: str) -> dict:
    r = client.get(f"/api/library/project-links/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def _settle_links(client, pid: str, kind: str) -> dict:
    for _ in range(400):
        out = _links(client, pid)
        if out[kind] and out[kind]["status"] == "ready":
            return out
        time.sleep(0.05)
    raise AssertionError("never ready")


# ---------------------------------------------------------------- stars on a converted deck
def test_source_star_creates_the_deck_once_and_maps_by_index(client):
    p = _converted()
    slides = db.slides_of(p.id)
    assert _links(client, p.id) == {"source": None, "generated": None, "favourites": {}}
    first = _star(client, slides[1].id, "source")
    assert first["pending"] and first["lib_slide_id"] is None and first["deck_id"]
    # a second star while the copy runs (or after) lands on the same deck
    second = _star(client, slides[3].id, "source")
    assert second["deck_id"] == first["deck_id"]
    out = _settle_links(client, p.id, "source")
    d = db.get(LibDeck, first["deck_id"])
    assert d.origin == "converted" and d.origin_project_id == p.id and not d.pending_favourites
    with db.session() as ses:
        assert len(list(ses.exec(db.select(LibDeck)))) == 1   # never duplicated
    rows = {r.index: r for r in ingest.slides_of(d.id)}
    assert rows[2].favourite and rows[4].favourite and not rows[1].favourite
    assert rows[2].content["origin_slide_id"] == slides[1].id
    assert out["favourites"] == {slides[1].id: rows[2].id, slides[3].id: rows[4].id}
    assert out["source"]["favourites"] == out["favourites"]
    # once ready, a star is applied at once and maps by index
    third = _star(client, slides[0].id, "source")
    assert third == {"lib_slide_id": rows[1].id, "deck_id": d.id, "pending": False}
    assert db.get(LibSlide, rows[1].id).favourite and db.get(LibSlide, rows[1].id).ai_status in ("pending", "done")
    # unfavourite never deletes
    off = _star(client, slides[0].id, "source", False)
    assert off["lib_slide_id"] == rows[1].id and not db.get(LibSlide, rows[1].id).favourite
    assert slides[0].id not in _links(client, p.id)["favourites"]
    # library slide_out links back to the project
    lib = client.get(f"/api/library/slides/{rows[2].id}").json()
    assert lib["origin_slide_id"] == slides[1].id and lib["deck"]["origin_project_id"] == p.id


def test_source_star_reuses_an_uploaded_copy_of_the_same_file(client):
    up = _upload(client, DECK)
    p = _converted()
    s = db.slides_of(p.id)[2]
    out = _star(client, s.id, "source")
    assert out["deck_id"] == up["deck"]["id"] and not out["pending"]
    assert db.get(LibSlide, out["lib_slide_id"]).index == s.index
    assert _links(client, p.id)["source"]["deck_id"] == up["deck"]["id"]
    with db.session() as ses:
        assert len(list(ses.exec(db.select(LibDeck)))) == 1


def test_source_star_refuses_slides_made_here_and_composed_decks(client):
    p = _converted()
    added = runner.add_slide(p.id)
    r = client.post("/api/library/project-favourite", json={"slide_id": added.id, "kind": "source"})
    assert r.status_code == 400
    c = _composed()
    r = client.post("/api/library/project-favourite", json={"slide_id": db.slides_of(c.id)[0].id, "kind": "source"})
    assert r.status_code == 400


# ---------------------------------------------------------------- stars on approved designs
def test_generated_star_stale_supersedes_and_carries_user_work(client):
    p = _converted("Made")
    s1, s2, s3 = db.slides_of(p.id)[:3]
    _approve(p, s1)
    _approve(p, s2)
    # not approved yet: refused
    assert client.post("/api/library/project-favourite",
                       json={"slide_id": s3.id, "kind": "generated"}).status_code == 400
    first = _star(client, s1.id, "generated")
    assert first["pending"]
    out = _settle_links(client, p.id, "generated")
    old = db.get(LibDeck, first["deck_id"])
    assert old.origin == "generated" and out["generated"]["stale_slide_ids"] == []
    rows = {r.content["origin_slide_id"]: r for r in ingest.slides_of(old.id)}
    assert rows[s1.id].favourite and rows[s1.id].content["origin_version_id"] == db.get(Slide, s1.id).approved_version_id
    assert out["favourites"] == {s1.id: rows[s1.id].id}
    # the user locks tags on it; then the design of s1 changes and s3 gets approved
    client.patch(f"/api/library/slides/{rows[s1.id].id}", json={"tags": ["security"]})
    _approve(p, db.get(Slide, s1.id), "teal")
    _approve(p, s3)
    out = _links(client, p.id)
    assert out["generated"]["stale_slide_ids"] == [s1.id] and out["generated"]["missing_slide_ids"] == [s3.id]
    # starring a stale slide saves a new deck that supersedes the old one
    second = _star(client, s2.id, "generated")
    assert second["pending"] is False and second["lib_slide_id"] == rows[s2.id].id   # s2 itself is current
    third = _star(client, s3.id, "generated")
    assert third["pending"] and third["deck_id"] != old.id
    out = _settle_links(client, p.id, "generated")
    new = db.get(LibDeck, third["deck_id"])
    assert new.supersedes_id == old.id and db.get(LibDeck, old.id).superseded_by == new.id
    assert new.project == old.project and new.title == old.title
    nrows = {r.content["origin_slide_id"]: r for r in ingest.slides_of(new.id)}
    assert set(nrows) == {s1.id, s2.id, s3.id}
    assert nrows[s1.id].favourite and nrows[s1.id].tags_user and nrows[s1.id].tags == db.get(LibSlide, rows[s1.id].id).tags
    assert nrows[s2.id].favourite and nrows[s3.id].favourite
    assert out["generated"]["deck_id"] == new.id and out["generated"]["stale_slide_ids"] == []
    assert set(out["favourites"]) == {s1.id, s2.id, s3.id}
    # unfavourite
    off = _star(client, s2.id, "generated", False)
    assert off["lib_slide_id"] == nrows[s2.id].id and not db.get(LibSlide, nrows[s2.id].id).favourite
    assert db.get(LibSlide, rows[s2.id].id) is not None   # nothing is ever deleted


def test_pending_favourites_are_applied_once_the_deck_is_ready():
    p = _converted("Pend")
    s = db.slides_of(p.id)[0]
    d = db.save(LibDeck(project="P", origin="converted", origin_project_id=p.id, status="ingesting",
                        pending_favourites=[s.id]))
    db.save(LibSlide(deck_id=d.id, index=s.index, content={"origin_slide_id": s.id}))
    assert ingest.apply_pending_favourites(d.id) == []          # not ready: left queued
    assert db.get(LibDeck, d.id).pending_favourites == [s.id]
    assert reuse._status(db.update(LibDeck, d.id, status="ready")) == "ingesting"   # ready only once applied
    assert len(ingest.apply_pending_favourites(d.id)) == 1      # applied, and the slide needs tagging
    assert db.get(LibDeck, d.id).pending_favourites == [] and reuse._status(db.get(LibDeck, d.id)) == "ready"
    assert [r.favourite for r in ingest.slides_of(d.id)] == [True]


# ---------------------------------------------------------------- insert
def _lib_rows(client) -> dict[int, dict]:
    deck = _upload(client, OTHER)
    return {s["index"]: s for s in deck["slides"]}


def test_insert_into_a_composed_deck(client):
    lib = _lib_rows(client)
    p = _composed(3)
    r = client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[5]["id"], lib[6]["id"]], "after": 1})
    assert r.status_code == 200, r.text
    got = r.json()["slides"]
    assert len(got) == 2
    order = db.slides_of(p.id)
    assert [s.position for s in order] == [1, 2, 3, 4, 5] and [s.index for s in order] == [1, 2, 3, 4, 5]
    assert [s.id for s in order[1:3]] == [g["id"] for g in got]
    table, pic = order[1], order[2]
    src = table.plan["library_source"]
    assert src["lib_slide_id"] == lib[5]["id"] and src["index"] == 5 and src["label"].endswith("(slide library)")
    assert "added" not in table.plan
    assert table.content["tables"] and table.facts
    # facts present and unique across the project
    ids = [f["id"] for s in order for f in (s.facts or [])]
    assert len(ids) == len(set(ids))
    assert all(f["id"].startswith(table.id) for f in table.facts)
    # the picture came along under a key that resolves in this project
    key = pic.content["images"][0]["key"]
    assert key.startswith("l_") and key in db.asset_files(p.id)
    assert not any(order[0].id == g["id"] for g in got)


def test_insert_into_a_converted_deck_keeps_index_and_marks_added(client):
    lib = _lib_rows(client)
    p = _converted()
    before = db.slides_of(p.id)
    r = client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[6]["id"], lib[5]["id"]], "after": 0})
    assert r.status_code == 200, r.text
    order = db.slides_of(p.id)
    assert [s.position for s in order] == list(range(1, len(before) + 3))
    a, b = order[0], order[1]
    assert a.plan["library_source"]["index"] == 6 and b.plan["library_source"]["index"] == 5
    assert a.plan["added"] and b.plan["added"]
    top = max(s.index for s in before)
    assert {a.index, b.index} == {top + 1, top + 2}
    # source slides keep their index (it names their render)
    assert [(s.id, s.index) for s in order[2:]] == [(s.id, s.index) for s in before]
    # appended at the end with after=None
    r = client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[1]["id"]]})
    assert db.slides_of(p.id)[-1].id == r.json()["slides"][0]["id"]
    # project slide payload
    assert r.json()["slides"][0]["label"] == "new"


def test_insert_refuses_bad_input(client):
    lib = _lib_rows(client)
    p = _composed(1)
    assert client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": []}).status_code == 400
    assert client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": ["lsnope"]}).status_code == 404
    assert client.post("/api/library/insert/pnope", json={"lib_slide_ids": [lib[1]["id"]]}).status_code == 404
    db.update(Project, p.id, status="planning")
    assert client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[1]["id"]]}).status_code == 409


def test_replan_keeps_inserted_facts_and_library_source(client):
    lib = _lib_rows(client)
    p = _composed(2)
    client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[5]["id"]]})
    ins = db.slides_of(p.id)[-1]
    before = {f["id"]: f["raw"] for f in ins.facts}
    assert before
    asyncio.run(runner.plan(p.id))
    after = db.get(Slide, ins.id)
    assert {f["id"]: f["raw"] for f in after.facts} == before
    assert after.plan["library_source"]["lib_slide_id"] == lib[5]["id"] and after.plan.get("pattern")
    # typing into it keeps its table (and so the table's facts)
    runner.write_slide(ins.id, title="Retitled")
    typed = db.get(Slide, ins.id)
    assert typed.content["tables"] and len(typed.facts) >= len([f for f in after.facts if f["origin"] == "table"])


def test_converted_insert_is_planned_by_plan_slides_and_keeps_facts(client):
    from app.pipeline import deckops
    lib = _lib_rows(client)
    p = _converted()
    r = client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[5]["id"]]})
    sid = r.json()["slides"][0]["id"]
    before = db.get(Slide, sid).facts
    asyncio.run(deckops.plan_slides(p.id, [sid]))
    s = db.get(Slide, sid)
    assert s.plan.get("pattern") and s.plan["library_source"] and s.plan["added"]
    assert [f["id"] for f in s.facts] == [f["id"] for f in before]


def test_generation_prompt_cites_the_library_deck(client, monkeypatch):
    lib = _lib_rows(client)
    p = _composed(1)
    client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[5]["id"]]})
    ins = db.slides_of(p.id)[-1]
    label = ins.plan["library_source"]["label"]
    seen: dict = {}
    real = prompts.generate_messages

    def capture(**kw):
        seen["msgs"] = real(**kw)
        raise RuntimeError("stop after the prompt")

    async def no_vision():
        return False

    monkeypatch.setattr(settings(), "llm_mock", False)
    monkeypatch.setattr(runner.prompts, "generate_messages", capture)
    monkeypatch.setattr(runner.llm, "vision_enabled", no_vision)
    v = asyncio.run(runner.generate_version(ins.id, "A"))
    assert v.status == "failed"
    user = seen["msgs"][-1]["content"]
    assert isinstance(user, str) and label in user and "slide library" in user
    # the system prefix is untouched (byte-stable)
    assert seen["msgs"][0]["content"] == prompts._system()["content"] and label not in seen["msgs"][0]["content"]


def test_library_render_stands_in_for_the_source_render(client):
    lib = _lib_rows(client)
    row = db.get(LibSlide, lib[2]["id"])
    rd = common.deck_dir(row.deck_id) / "renders"
    rd.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), "white").save(rd / f"{row.index:03d}.png")
    p = _composed(1)
    client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [row.id]})
    ins = db.slides_of(p.id)[-1]
    assert runner.Ctx(ins).source_png == rd / f"{row.index:03d}.png"
    # a generated library slide is already a design, not an original
    assert runner.library_render({**ins.plan, "library_source": {**ins.plan["library_source"], "origin": "generated"}}) is None
    assert runner.library_render({"library_source": {"deck_id": "../x", "index": 1}}) is None


def test_merging_inserted_slides_keeps_every_citation(client):
    lib = _lib_rows(client)
    p = _composed(1)
    client.post(f"/api/library/insert/{p.id}", json={"lib_slide_ids": [lib[5]["id"], lib[6]["id"]]})
    rows = db.slides_of(p.id)
    labels = [x.plan["library_source"]["label"] for x in rows[1:]]
    r = client.post(f"/api/projects/{p.id}/merge", json={"slide_ids": [x.id for x in rows]})
    assert r.status_code == 200, r.text
    merged = db.get(Slide, r.json()["id"])
    # cites both library slides, is neither of them (no badge, no single original picture), keeps their facts
    assert [s["lib_slide_id"] for s in merged.plan["library_sources"]] == [lib[5]["id"], lib[6]["id"]]
    assert "library_source" not in merged.plan and runner.library_render(merged.plan) is None
    assert runner.library_citation(merged.plan) == "; ".join(labels)
    assert {f["raw"] for x in rows[1:] for f in x.facts} <= {f["raw"] for f in merged.facts}
    # survives a re-plan like any sticky key
    asyncio.run(runner.plan(p.id))
    assert db.get(Slide, merged.id).plan["library_sources"] == merged.plan["library_sources"]
