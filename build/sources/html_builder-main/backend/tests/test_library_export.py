"""Library export: picture mode end to end, the fallback when PowerPoint is not there, and — only where
PowerPoint is installed — a real COM merge of two sample decks."""
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pptx import Presentation

from app import main
from app.config import settings
from app.library import common
from app.library import export as lx
from app.store import db
from app.store.db import LibDeck, LibSlide

from conftest import DECKS


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _deck(n: int = 3, *, project: str = "Acme", origin: str = "upload", renders: bool = True,
          source: Path | None = None) -> tuple[LibDeck, list[LibSlide]]:
    d = db.save(LibDeck(project=project, title=f"{project} deck", origin=origin, status="ready", slide_count=n))
    slides = []
    for i in range(1, n + 1):
        slides.append(db.save(LibSlide(deck_id=d.id, index=i, title=f"{project} slide {i}", notes=f"notes {project} {i}")))
        if renders:
            p = common.render_path(d.id, i)
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (160, 90), (i * 40, 0, 0)).save(p)
    if source is not None:
        shutil.copy(source, common.source_pptx(d.id))
    return d, slides


def _read(resp, tmp_path: Path) -> Presentation:
    f = tmp_path / "out.pptx"
    f.write_bytes(resp.content)
    return Presentation(str(f))


def _notes(prs: Presentation) -> list[str]:
    return [s.notes_slide.notes_text_frame.text if s.has_notes_slide else "" for s in prs.slides]


def test_picture_mode_keeps_order_count_and_notes(client, tmp_path):
    _, a = _deck(3, project="Acme")
    ids = [a[2].id, a[0].id, a[1].id]
    r = client.post("/api/library/export.pptx", json={"slide_ids": ids, "mode": "picture"})
    assert r.status_code == 200, r.text
    assert r.headers["x-export-mode"] == "picture"
    assert r.headers["x-export-fallback"] == ""
    prs = _read(r, tmp_path)
    assert len(prs.slides) == 3
    assert _notes(prs) == ["notes Acme 3", "notes Acme 1", "notes Acme 2"]
    pic = prs.slides[0].shapes[0]
    assert (pic.width, pic.height) == (prs.slide_width, prs.slide_height)   # 16:9 render = full bleed
    cd = r.headers["content-disposition"]
    assert 'filename="Acme - selected slides.pptx"' in cd
    assert unquote(cd.split("filename*=UTF-8''")[1]) == "Acme - selected slides.pptx"


def test_slides_from_several_projects_are_named_library_and_unrendered_ones_still_count(client, tmp_path):
    _, a = _deck(1, project="Acme")
    _, b = _deck(1, project="Ünïcode 项目", renders=False)
    r = client.post("/api/library/export.pptx", json={"slide_ids": [b[0].id, a[0].id], "mode": "picture"})
    assert r.status_code == 200
    assert 'filename="Library - selected slides.pptx"' in r.headers["content-disposition"]
    prs = _read(r, tmp_path)
    assert len(prs.slides) == 2
    assert "Ünïcode 项目 slide 1" in prs.slides[0].shapes[0].text_frame.text


def test_original_mode_falls_back_to_pictures_without_powerpoint(client, tmp_path, monkeypatch):
    _, a = _deck(2, project="Acme", source=DECKS / "hp_wolf_print_security.pptx")
    _, g = _deck(1, project="Acme", origin="generated")
    monkeypatch.setattr(lx, "com_available", lambda: False)
    ids = [a[1].id, g[0].id, a[0].id]
    r = client.post("/api/library/export.pptx", json={"slide_ids": ids, "mode": "original"})
    assert r.status_code == 200
    assert r.headers["x-export-mode"] == "picture"
    assert r.headers["x-export-fallback"].split(",") == ids
    assert _notes(_read(r, tmp_path)) == ["notes Acme 2", "notes Acme 1", "notes Acme 1"]


def test_original_mode_falls_back_when_powerpoint_fails(client, tmp_path, monkeypatch):
    _, a = _deck(2, source=DECKS / "hp_wolf_print_security.pptx")
    monkeypatch.setattr(lx, "com_available", lambda: True)

    def boom(job, timeout):
        raise RuntimeError("PowerPoint did not respond")
    monkeypatch.setattr(lx, "run_merge", boom)
    r = client.post("/api/library/export.pptx", json={"slide_ids": [s.id for s in a], "mode": "original"})
    assert r.status_code == 200
    assert r.headers["x-export-mode"] == "picture"
    assert len(_read(r, tmp_path).slides) == 2


def test_source_number_skips_hidden_slides(tmp_path):
    src = tmp_path / "h.pptx"
    p = Presentation(str(DECKS / "hp_wolf_print_security.pptx"))
    p.slides[1]._element.set("show", "0")
    p.save(str(src))
    d, s = _deck(4, source=src)
    items = lx._items([x.id for x in s])
    assert [it.number for it in items] == [1, 3, 4, 5]
    db.update(LibSlide, s[0].id, content={"source_number": 2})   # the ingest's own mapping wins
    assert lx._items([s[0].id])[0].number == 2


def test_bad_requests(client):
    assert client.post("/api/library/export.pptx", json={"slide_ids": [], "mode": "picture"}).status_code == 400
    assert client.post("/api/library/export.pptx", json={"slide_ids": ["nope"], "mode": "picture"}).status_code == 400
    many = [f"x{i}" for i in range(lx.MAX_SLIDES + 1)]
    assert client.post("/api/library/export.pptx", json={"slide_ids": many, "mode": "picture"}).status_code == 400
    assert client.post("/api/library/export.pptx", json={"slide_ids": ["a"], "mode": "bogus"}).status_code == 422


def _powerpoint_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "PowerPoint.Application"))
        import win32com.client  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _powerpoint_installed(), reason="PowerPoint is not installed")
def test_original_mode_merges_real_slides_with_powerpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "renderer", "powerpoint")
    _, wolf = _deck(5, project="Mix", source=DECKS / "hp_wolf_print_security.pptx")
    _, z = _deck(10, project="Mix", source=DECKS / "hp_z_workstations_genai.pptx")
    _, g = _deck(1, project="Mix", origin="generated")
    ids = [z[2].id, wolf[1].id, g[0].id, z[0].id]
    r = client.post("/api/library/export.pptx", json={"slide_ids": ids, "mode": "original"})
    assert r.status_code == 200, r.text
    assert r.headers["x-export-mode"] == "original"
    assert r.headers["x-export-fallback"] == g[0].id
    prs = _read(r, tmp_path)
    assert len(prs.slides) == 4

    def text(s):
        return " ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame)
    assert "Challenges with cloud-only AI" in text(prs.slides[0])
    assert "The risk" in text(prs.slides[1])
    assert text(prs.slides[2]) == ""                               # the generated slide, as a picture
    assert "HP Z Workstations for Generative AI" in text(prs.slides[3])
    notes = _notes(prs)
    assert notes[0].startswith("Pause on the 240% number")        # speaker notes came along with the slide
    assert notes[2] == "notes Mix 1"
    assert notes[3].startswith("Welcome.")
    # most originals are 16:9, so the page is (PowerPoint rounds it to whole points) …
    assert abs(prs.slide_width - Presentation(str(DECKS / "hp_z_workstations_genai.pptx")).slide_width) < 12700
    # … and the one 4:3 slide is fitted onto it: reported, and laid out as it was, centred — not hugging the left
    assert r.headers["x-export-resized"] == wolf[1].id
    src = Presentation(str(DECKS / "hp_wolf_print_security.pptx"))
    title_src = src.slides[1].shapes[0]
    title_out = prs.slides[1].shapes[0]
    offset = (prs.slide_width - src.slide_width) / 2
    assert abs(title_out.left - (title_src.left + offset)) < 12700 and abs(title_out.width - title_src.width) < 12700


def test_page_size_follows_most_of_the_original_slides():
    _, wolf = _deck(5, project="Mix", source=DECKS / "hp_wolf_print_security.pptx")
    _, z = _deck(10, project="Mix", source=DECKS / "hp_z_workstations_genai.pptx")
    four_three = lx._slide_size_pt(DECKS / "hp_wolf_print_security.pptx")
    wide = lx._slide_size_pt(DECKS / "hp_z_workstations_genai.pptx")
    assert lx.page_size(lx._items([z[0].id, wolf[0].id, wolf[1].id])) == four_three   # 2 of 3 are 4:3
    assert lx.page_size(lx._items([wolf[0].id, z[0].id, z[1].id])) == wide
    assert lx.page_size(lx._items([wolf[0].id, z[0].id])) == four_three                # a tie: the first one's
