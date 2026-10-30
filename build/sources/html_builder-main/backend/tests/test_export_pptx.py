"""PowerPoint export: slide selection, the picture per slide, the notes, and the route around it."""
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from app import export_pptx as xp
from app import main
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide, Version

RAW = """<meta>{"pattern":"cards","title":"Spec title","steps":2,"notes":["say <b>this</b>","and this"],"sources":"IDC, 2025"}</meta>
<html><h1 class="title">Heading</h1></html>
<css>.title{color:#000}</css>
<script>function go(root, step){}</script>"""

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _deck(*, approved: bool = True, shots: bool = True, n: int = 2) -> Project:
    p = db.save(Project(name="deck", filename="deck.pptx", status="reviewing", deck_title="Q3 Review"))
    spec, _ = parse_spec(RAW, "s")
    for i in range(n):
        s = db.save(Slide(project_id=p.id, index=i + 1, position=i + 1, status="review", content={"index": i + 1}))
        v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready",
                            spec=spec.model_dump(), qa={"passed": True, "findings": []}, score=8.0))
        if shots:
            (db.version_dir(p.id, v.id) / "shot_final.png").write_bytes(_PNG)
        if approved:
            db.update(Slide, s.id, status="approved", approved_version_id=v.id)
    return p


def test_the_deck_is_one_slide_per_approved_version(tmp_path):
    p = _deck(n=3)
    pages = xp.deck_pages(p.id)
    assert [x.slide.index for x in pages] == [1, 2, 3]
    assert all(x.shot.exists() for x in pages)


def test_an_unapproved_slide_is_filled_or_left_out():
    p = _deck(approved=False, n=2)
    assert len(xp.deck_pages(p.id, fill_unapproved=True)) == 2
    assert xp.deck_pages(p.id, fill_unapproved=False) == []


def test_an_excluded_slide_never_reaches_the_file():
    p = _deck(n=2)
    db.update(Slide, db.slides_of(p.id)[0].id, included=False)
    assert [x.slide.index for x in xp.deck_pages(p.id)] == [2]


def test_notes_are_plain_text_with_the_sources_appended():
    p = _deck(n=1)
    notes = xp.deck_pages(p.id)[0].notes()
    assert notes.splitlines()[:2] == ["say this", "and this"]  # the inline <b> is stripped
    assert notes.endswith("Sources: IDC, 2025")


def test_write_pptx_makes_a_16_9_deck_with_a_full_bleed_picture_and_real_notes(tmp_path):
    p = _deck(n=2)
    pages = xp.deck_pages(p.id)
    out = xp.write_pptx([(x, x.shot) for x in pages], tmp_path / "deck.pptx")
    prs = Presentation(str(out))
    assert (prs.slide_width, prs.slide_height) == (xp.SLIDE_W, xp.SLIDE_H)
    assert round(prs.slide_width / prs.slide_height, 2) == 1.78
    assert len(prs.slides._sldIdLst) == 2
    for slide in prs.slides:
        pic = slide.shapes[0]
        assert (pic.left, pic.top) == (0, 0)
        assert (pic.width, pic.height) == (xp.SLIDE_W, xp.SLIDE_H)
        assert "say this" in slide.notes_slide.notes_text_frame.text


def test_a_version_without_a_screenshot_is_rendered(monkeypatch, tmp_path):
    p = _deck(shots=False, n=1)
    called: list[Path] = []

    async def fake_check(spec, slide_id, assets, out_dir, title="QA", prev_dir=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "shot_final.png").write_bytes(_PNG)
        called.append(out_dir)
        return type("R", (), {"findings": []})()

    monkeypatch.setattr(xp, "check_spec", fake_check)
    shots = asyncio.run(xp.slide_images(xp.deck_pages(p.id), tmp_path))
    assert len(shots) == 1 and called and called[0].parent == tmp_path


def test_one_unrenderable_slide_does_not_lose_the_others(monkeypatch, tmp_path):
    p = _deck(shots=False, n=3)

    async def boom(spec, slide_id, assets, out_dir, title="QA", prev_dir=None):
        if "001" in out_dir.name:
            raise RuntimeError("chromium went away")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "shot_final.png").write_bytes(_PNG)
        return type("R", (), {"findings": []})()

    monkeypatch.setattr(xp, "check_spec", boom)
    shots = asyncio.run(xp.slide_images(xp.deck_pages(p.id), tmp_path))
    assert len(shots) == 2


# ---------------------------------------------------------------- route
def test_export_pptx_route_downloads_a_real_pptx(client):
    p = _deck(n=2)
    r = client.get(f"/api/projects/{p.id}/export.pptx")
    assert r.status_code == 200
    assert r.headers["content-type"] == main.PPTX_MIME
    assert r.content[:2] == b"PK"  # an OOXML zip, not an HTML error page
    assert 'filename="Q3_Review.pptx"' in r.headers["content-disposition"]


def test_export_pptx_uses_a_private_working_directory_and_cleans_it_up(client, monkeypatch):
    seen: list[Path] = []
    real = xp.export_pptx

    async def spy(pid, out, **kw):
        seen.append(out)
        return await real(pid, out, **kw)

    monkeypatch.setattr(main, "export_pptx", spy)
    p = _deck(n=1)
    assert client.get(f"/api/projects/{p.id}/export.pptx").status_code == 200
    assert client.get(f"/api/projects/{p.id}/export.pptx").status_code == 200
    assert len({x.parent for x in seen}) == 2  # concurrent exports never share a path
    assert all(x.parent.name.startswith("pptx-") for x in seen)
    assert not any(x.parent.exists() for x in seen)  # dropped once the response was sent


def test_a_non_ascii_deck_title_does_not_break_the_download_header(client):
    p = _deck(n=1)
    db.update(Project, p.id, deck_title="日本語 デッキ")
    cd = client.get(f"/api/projects/{p.id}/export.pptx").headers["content-disposition"]
    cd.encode("latin-1")  # Starlette encodes headers as latin-1
    assert "filename*=UTF-8''%E6%97%A5" in cd and 'filename="deck.pptx"' in cd


def test_an_empty_deck_is_a_409_not_an_empty_file(client):
    p = db.save(Project(name="empty", filename="empty.pptx"))
    r = client.get(f"/api/projects/{p.id}/export.pptx")
    assert r.status_code == 409 and "No slides are ready" in r.json()["detail"]


def test_missing_project_is_404(client):
    assert client.get("/api/projects/nope/export.pptx").status_code == 404


# ---------------------------------------------------------------- the editable export
# These render in Chromium: the words and pictures are read back out of the finished slide.
EDITABLE = """<meta>{"pattern":"image-focus","title":"Stack","steps":1,"notes":["n"]}</meta>
<html>
<div class="eyebrow">ARCHITECTURE</div>
<h1 class="title">Our AI <b>stack</b></h1>
<div class="legend"><span><i class="s1"></i>Cloud GPU spend</span></div>
<figure class="figure"><img src="asset:stack" alt="The stack" style="width:600px;height:300px;object-fit:contain"></figure>
</html>
<css>.title{color:rgb(10, 10, 15)}</css>
<script>function go(root, step){}</script>"""


def _stack_png(path: Path) -> Path:
    from PIL import Image
    Image.new("RGB", (400, 400), (20, 40, 90)).save(path)
    return path


def test_a_slide_splits_into_background_text_and_pictures(tmp_path):
    from app.qa.extract_layout import extract_layout
    spec, _ = parse_spec(EDITABLE, "s")
    lay = asyncio.run(extract_layout(spec, "s", {"stack": _stack_png(tmp_path / "stack.png")}, tmp_path / "out", number=7))
    words = {"".join(r.text for r in t.runs) for t in lay.texts}
    assert {"ARCHITECTURE", "Our AI stack", "Cloud GPU spend"} <= words, words
    title = next(t for t in lay.texts if "".join(r.text for r in t.runs) == "Our AI stack")
    assert [r.weight >= 600 for r in title.runs if r.text.strip() == "stack"] == [True], "inline bold survives as a run"
    assert len(lay.pictures) == 1
    pic = lay.pictures[0]
    # object-fit:contain letterboxes: the placed picture is the square image, not the wide box around it
    assert abs(pic.w - pic.h) < 2 and pic.w < 590, (pic.w, pic.h)
    legend = next(t for t in lay.texts if "".join(r.text for r in t.runs) == "Cloud GPU spend")
    assert lay.background.exists()
    from PIL import Image
    with Image.open(lay.background) as bg:
        assert bg.size == (3200, 1800), "the background is shot at 2x for a projector"
    assert legend.x > 0


def test_the_editable_file_has_real_text_boxes_and_pictures(client, tmp_path):
    from app.qa.extract_layout import extract_layout
    spec, _ = parse_spec(EDITABLE, "s")
    lay = asyncio.run(extract_layout(spec, "s", {"stack": _stack_png(tmp_path / "stack.png")}, tmp_path / "out"))
    p = _deck(n=1)
    page = xp.deck_pages(p.id)[0]
    out = xp.write_editable_pptx([(page, lay)], tmp_path / "deck.pptx")
    slide = Presentation(str(out)).slides[0]
    texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
    assert "Our AI stack" in texts
    assert sum(1 for s in slide.shapes if s.shape_type == 13) == 1, "the picture is a picture, not part of the background"
    assert slide._element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}bg") is not None, \
        "the rest of the design is the slide background, so it can't be grabbed by mistake"
    run = next(s for s in slide.shapes if s.has_text_frame and s.text_frame.text == "Our AI stack").text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Archivo" and run.font.size is not None
    assert slide.notes_slide.notes_text_frame.text.startswith("say this")


def test_the_route_serves_the_editable_file(client):
    p = _deck(n=1)
    r = client.get(f"/api/projects/{p.id}/export.pptx?editable=true")
    assert r.status_code == 200
    import io
    slide = Presentation(io.BytesIO(r.content)).slides[0]
    assert any(s.has_text_frame and s.text_frame.text == "Heading" for s in slide.shapes)
