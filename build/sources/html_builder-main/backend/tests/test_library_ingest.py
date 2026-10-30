"""The slide library's way in: upload, duplicates, versions, delete, images, save-from-project, backup."""
import io
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pptx import Presentation

from app import main
from app.ingest.pptx_parse import parse_pptx
from app.library import common, ingest
from app.library.fingerprint import also_in_counts, dhash, text_sha
from app.store import db
from app.store.db import LibDeck, LibSlide, Project, Slide, Version

from conftest import DECKS

DECK = DECKS / "hp_wolf_print_security.pptx"
OTHER = DECKS / "hp_z_workstations_genai.pptx"


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_library():
    """Every test starts from an empty library (the data dir is shared by the whole run)."""
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


def _upload(client, path: Path = DECK, project: str = "Wolf", **form):
    with path.open("rb") as f:
        return client.post("/api/library/decks", files={"file": (path.name, f.read())},
                           data={"project": project, **form})


def _settle(deck_id: str, tries: int = 400) -> LibDeck:
    for _ in range(tries):
        d = db.get(LibDeck, deck_id)
        if d is not None and d.status != "ingesting":
            return d
        time.sleep(0.05)
    raise AssertionError("library job never finished")


def _ready(client, path: Path = DECK, **kw) -> dict:
    r = _upload(client, path, **kw)
    assert r.status_code == 200, r.text
    d = _settle(r.json()["id"])
    assert d.status == "ready", d.error
    return client.get(f"/api/library/decks/{d.id}").json()


# ---------------------------------------------------------------- upload
def test_upload_ingests_slides_with_text_and_fingerprints(client):
    r = _upload(client)
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "ingesting" and out["project"] == "Wolf" and out["filename"] == DECK.name
    d = _settle(out["id"])
    assert d.status == "ready" and d.slide_count > 0 and d.title and d.renderer == "none"
    assert common.source_pptx(d.id).exists()
    full = client.get(f"/api/library/decks/{d.id}").json()
    assert full["deck"]["id"] == d.id and len(full["slides"]) == d.slide_count
    assert [s["index"] for s in full["slides"]] == list(range(1, d.slide_count + 1))
    rows = ingest.slides_of(d.id)
    assert any(s.text for s in rows) and any(s.title for s in rows)
    assert all(s.text_sha for s in rows if s.title or s.text)
    assert all(s.phash == "" for s in rows), "no renders under RENDERER=none"
    assert all(s.content.get("source_number") for s in rows)
    # the detail route carries the parse and the ledger
    det = client.get(f"/api/library/slides/{rows[0].id}").json()
    assert det["id"] == rows[0].id and "content" in det and isinstance(det["facts"], list)
    assert det["deck"]["id"] == d.id


def test_upload_needs_a_pptx_and_a_project(client):
    r = client.post("/api/library/decks", files={"file": ("x.pdf", b"%PDF")}, data={"project": "X"})
    assert r.status_code == 400
    r = _upload(client, project="  ")
    assert r.status_code == 400


def test_duplicate_is_refused_unless_forced(client):
    first = _ready(client)["deck"]
    r = _upload(client, project="Other")
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["code"] == "duplicate" and det["deck_id"] == first["id"] and det["message"]
    r = _upload(client, project="Other", force="true")
    assert r.status_code == 200
    second = _settle(r.json()["id"])
    assert second.status == "ready"
    # the same slides are now in two decks
    also = also_in_counts(ingest.slides_of(second.id))
    assert also and all(n == 1 for sid, n in also.items() if db.get(LibSlide, sid).text_sha)
    listed = client.get(f"/api/library/decks/{second.id}").json()["slides"]
    assert any(s["also_in"] == 1 for s in listed)


def test_supersede_then_delete_clears_the_link(client):
    old = _ready(client)["deck"]
    new = _ready(client, OTHER, supersedes=old["id"])["deck"]
    assert new["supersedes_id"] == old["id"]
    assert db.get(LibDeck, old["id"]).superseded_by == new["id"]
    old_slides = client.get(f"/api/library/decks/{old['id']}").json()["slides"]
    assert old_slides and all(s["superseded"] for s in old_slides)
    assert client.delete(f"/api/library/decks/{new['id']}").json() == {"ok": True}
    assert db.get(LibDeck, new["id"]) is None
    assert db.get(LibDeck, old["id"]).superseded_by == ""
    assert _upload(client, OTHER, supersedes="ldnope").status_code == 404


def test_delete_removes_rows_and_folder(client):
    deck = _ready(client)["deck"]
    folder = common.library_dir() / deck["id"]
    assert folder.exists()
    assert client.delete(f"/api/library/decks/{deck['id']}").status_code == 200
    assert not folder.exists()
    assert ingest.slides_of(deck["id"]) == []
    assert client.get(f"/api/library/decks/{deck['id']}").status_code == 404
    assert client.delete(f"/api/library/decks/{deck['id']}").status_code == 404


def test_list_patch_and_projects(client):
    a = _ready(client, project="Wolf")["deck"]
    b = _ready(client, OTHER, project="Z")["deck"]
    listed = client.get("/api/library/decks").json()
    assert [d["id"] for d in listed] == [b["id"], a["id"]], "newest first"
    assert all(d["favourites"] == 0 for d in listed)
    db.update(LibSlide, ingest.slides_of(a["id"])[0].id, favourite=True)
    r = client.patch(f"/api/library/decks/{a['id']}", json={"project": "Z", "title": "Renamed", "deck_date": "2025-03-01"})
    assert r.status_code == 200
    assert r.json()["project"] == "Z" and r.json()["title"] == "Renamed" and r.json()["deck_date"].startswith("2025-03-01")
    assert r.json()["favourites"] == 1
    assert client.patch(f"/api/library/decks/{a['id']}", json={"deck_date": "soon"}).status_code == 400
    projects = client.get("/api/library/projects").json()
    assert projects == [{"project": "Z", "decks": 2, "slides": a["slide_count"] + b["slide_count"], "favourites": 1}]


def test_images_fall_back_to_a_placeholder(client):
    deck = _ready(client)
    sid = deck["slides"][0]["id"]
    r = client.get(f"/api/library/slides/{sid}/image?thumb=true")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content
    r = client.get(f"/api/library/decks/{deck['deck']['id']}/cover.jpg")
    assert r.status_code == 200 and b"<svg" in r.content
    # a real render is served as it is
    p = common.render_path(deck["deck"]["id"], 1)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), "red").save(p)
    r = client.get(f"/api/library/slides/{sid}/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/library/slides/lsnope/image").status_code == 404


def test_hidden_slides_keep_their_real_number(client, tmp_path):
    prs = Presentation(str(DECK))
    prs.slides[1]._element.set("show", "0")
    src = tmp_path / "hidden.pptx"
    prs.save(str(src))
    deck = _ready(client, src)
    rows = ingest.slides_of(deck["deck"]["id"])
    assert len(rows) == len(prs.slides) - 1
    assert [s.index for s in rows] == list(range(1, len(rows) + 1))
    assert [s.content["source_number"] for s in rows] == [1] + list(range(3, len(prs.slides) + 1))


# ---------------------------------------------------------------- fingerprints
def test_dhash_is_stable_and_discriminating(tmp_path):
    def picture(name: str, colour: str, size=(1600, 900)) -> Path:
        im = Image.new("RGB", (1600, 900), "white")
        ImageDraw.Draw(im).rectangle((200, 200, 900, 700), fill=colour)
        im = im.resize(size)
        p = tmp_path / name
        im.save(p)
        return p

    a, b = picture("a.png", "navy"), picture("b.png", "navy")
    assert dhash(a) == dhash(b) and len(dhash(a)) == 16
    assert dhash(picture("small.png", "navy", (480, 270))) == dhash(a), "survives a re-render at another size"
    other = tmp_path / "c.png"
    im = Image.new("RGB", (1600, 900), "white")
    ImageDraw.Draw(im).ellipse((900, 100, 1500, 800), fill="black")
    im.save(other)
    assert dhash(other) != dhash(a)
    blank = tmp_path / "blank.png"
    Image.new("RGB", (1600, 900), "white").save(blank)
    assert dhash(blank) == "", "a featureless slide must not match every other one"
    assert dhash(tmp_path / "missing.png") == ""


def test_text_sha_normalises():
    assert text_sha("Title", "Some  Words") == text_sha("title", "some words\n")
    assert text_sha("", "") == ""


# ---------------------------------------------------------------- from a project
def _converted_project(name: str = "Converted") -> Project:
    p = db.save(Project(name=name, filename="wolf.pptx", status="ready", deck_title="Wolf Security"))
    pdir = db.project_dir(p.id)
    shutil.copy2(DECK, pdir / "source.pptx")
    deck = parse_pptx(pdir / "source.pptx", pdir / "assets", pdir / "renders")
    for sc in deck.slides:
        db.save(Slide(project_id=p.id, index=sc.index, position=sc.index, content=sc.model_dump(), facts=[]))
    return p


def test_from_project_source_copies_the_deck(client):
    p = _converted_project()
    rd = db.project_dir(p.id) / "renders"
    rd.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1600, 900), "white")
    ImageDraw.Draw(im).rectangle((100, 100, 800, 600), fill="teal")
    im.save(rd / "001.png")
    # a slide the user added here has no PowerPoint behind it and is not a source slide
    db.save(Slide(project_id=p.id, index=99, position=99, content={"index": 99, "title": "Mine"}, plan={"added": True}))
    r = client.post(f"/api/library/from-project/{p.id}", json={"kind": "source"})
    assert r.status_code == 200, r.text
    d = _settle(r.json()["id"])
    assert d.status == "ready" and d.origin == "converted" and d.origin_project_id == p.id
    assert d.project == "Converted" and d.title == "Wolf Security"
    rows = ingest.slides_of(d.id)
    n_source = len([s for s in db.slides_of(p.id) if s.index != 99])
    assert len(rows) == n_source and d.slide_count == n_source
    assert common.source_pptx(d.id).exists() and common.render_path(d.id, 1).exists()
    assert rows[0].phash and all(not s.phash for s in rows[1:])
    assert all(s.content.get("source_number") for s in rows)
    # saving the same project again is a duplicate
    r = client.post(f"/api/library/from-project/{p.id}", json={"kind": "source"})
    assert r.status_code == 409 and r.json()["detail"]["deck_id"] == d.id
    r = client.post(f"/api/library/from-project/{p.id}", json={"kind": "source", "force": True, "project": "Again"})
    assert r.status_code == 200 and r.json()["project"] == "Again"
    _settle(r.json()["id"])


def test_from_project_generated_uses_approved_screenshots(client):
    p = _converted_project("Made")
    slides = db.slides_of(p.id)
    assert client.post(f"/api/library/from-project/{p.id}", json={"kind": "generated"}).status_code == 400
    for s in slides[:2]:
        v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready", spec={}, qa={}))
        im = Image.new("RGB", (1600, 900), "white")
        ImageDraw.Draw(im).rectangle((100 + s.index * 50, 100, 900, 700), fill="purple")
        im.save(db.version_dir(p.id, v.id) / "shot_final.png")
        db.update(Slide, s.id, status="approved", approved_version_id=v.id)
    r = client.post(f"/api/library/from-project/{p.id}", json={"kind": "generated", "project": "Lib"})
    assert r.status_code == 200, r.text
    d = _settle(r.json()["id"])
    assert d.status == "ready" and d.origin == "generated" and d.slide_count == 2 and d.project == "Lib"
    assert d.title.endswith(" (generated)")  # never reads as the PowerPoint it was converted from
    rows = ingest.slides_of(d.id)
    assert [s.index for s in rows] == [1, 2] and all(s.phash for s in rows)
    assert common.render_path(d.id, 1, thumb=True).exists()
    assert rows[0].title == slides[0].content.get("title", "")
    assert client.post(f"/api/library/from-project/{p.id}", json={"kind": "generated"}).status_code == 409


def test_from_project_rejects_bad_input(client):
    assert client.post("/api/library/from-project/pnope", json={"kind": "source"}).status_code == 404
    p = db.save(Project(name="Typed", filename="", source="composed", status="ready"))
    assert client.post(f"/api/library/from-project/{p.id}", json={"kind": "source"}).status_code == 400
    assert client.post(f"/api/library/from-project/{p.id}", json={"kind": "nope"}).status_code == 400


# ---------------------------------------------------------------- backup / restore / restart
def test_backup_restore_roundtrip(client):
    deck = _ready(client)["deck"]
    sid = ingest.slides_of(deck["id"])[0].id
    db.update(LibSlide, sid, favourite=True, tags=["security"])
    r = client.get("/api/library/backup")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    blob = r.content
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert "library.json" in names and f"files/{deck['id']}/source.pptx" in names
    # restoring over a library that still has everything adds nothing
    r = client.post("/api/library/restore", files={"file": ("b.zip", blob)})
    assert r.json() == {"decks": 0, "slides": 0, "tags": 0}
    ingest.delete_deck_rows(deck["id"])
    assert db.get(LibDeck, deck["id"]) is None
    r = client.post("/api/library/restore", files={"file": ("b.zip", blob)})
    assert r.status_code == 200 and r.json()["decks"] == 1 and r.json()["slides"] == deck["slide_count"]
    back = db.get(LibDeck, deck["id"])
    assert back.status == "ready" and back.created_at is not None
    s = db.get(LibSlide, sid)
    assert s.favourite and s.tags == ["security"] and s.content
    assert common.source_pptx(deck["id"]).exists()
    assert client.post("/api/library/restore", files={"file": ("x.zip", b"not a zip")}).status_code == 400


def test_recover_interrupted_marks_stuck_imports():
    d = db.save(LibDeck(project="P", status="ingesting", stage_note="Rendering"))
    ingest.recover_interrupted()
    d = db.get(LibDeck, d.id)
    assert d.status == "error" and d.error and d.stage_note == ""


def test_file_name_alt_text_is_not_slide_text():
    """PowerPoint fills a picture's alt text with its file name; that must not reach search or snippets."""
    from app.library.ingest import _FILENAME_ALT
    assert all(_FILENAME_ALT.match(t) for t in ("fury.svg", "Picture 3", "chart of spend.JPG"))
    assert not any(_FILENAME_ALT.match(t) for t in ("HP ZGX Fury tower", "Server rack photo"))
