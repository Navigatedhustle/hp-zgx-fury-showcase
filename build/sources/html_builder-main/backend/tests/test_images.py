"""The user's own images: uploading one, putting it on a slide, swapping it in the editor, and the margin trim
that keeps a diagram from arriving as a small island in a wide white frame."""
import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import main
from app.edit import apply_ops, ensure_ids, outline, parse_ops
from app.images import ImageRefused, store_upload, trim_margins
from app.ingest.pptx_parse import SlideContent
from app.pipeline import runner
from app.qa.render_check import check_spec
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide, Version


def _png(w=800, h=600, frame=200, bg=(255, 255, 255), alpha=False) -> bytes:
    """A dark block inside a `frame`-px margin of flat background."""
    mode = "RGBA" if alpha else "RGB"
    im = Image.new(mode, (w, h), (0, 0, 0, 0) if alpha else bg)
    ImageDraw.Draw(im).rectangle([frame, frame, w - frame, h - frame], fill=(20, 40, 90, 255) if alpha else (20, 40, 90))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _jpeg_with_exif() -> bytes:
    im = Image.new("RGB", (300, 200), (10, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


# ---------------------------------------------------------------- trimming
def test_a_white_frame_is_trimmed_to_the_content():
    im = Image.open(io.BytesIO(_png()))
    out = trim_margins(im)
    assert out.width < 500 and out.height < 300, out.size  # 400x200 block + a small pad


def test_a_transparent_frame_is_trimmed_too():
    out = trim_margins(Image.open(io.BytesIO(_png(alpha=True))))
    assert out.width < 500


def test_a_photo_without_a_uniform_frame_is_left_alone():
    im = Image.linear_gradient("L").convert("RGB").resize((400, 300))
    assert trim_margins(im).size == (400, 300)


def test_a_thin_margin_is_not_worth_nibbling():
    im = Image.open(io.BytesIO(_png(800, 600, frame=4)))
    assert trim_margins(im).size == (800, 600)


# ---------------------------------------------------------------- storing an upload
def test_upload_is_reencoded_without_exif(tmp_path):
    key, w, h = store_upload(_jpeg_with_exif(), "phone.jpg", tmp_path)
    assert key.startswith("u_") and (w, h) == (300, 200)
    f = next(tmp_path.glob(f"{key}.*"))
    with Image.open(f) as im:
        assert not im.getexif(), "EXIF (a phone photo's GPS position) must not travel into the deck"


def test_upload_is_downscaled_and_keyed_by_content(tmp_path):
    big = Image.new("RGB", (5000, 1000), (0, 0, 0))
    ImageDraw.Draw(big).ellipse([10, 10, 4990, 990], fill=(200, 10, 10))  # no flat frame to trim
    buf = io.BytesIO()
    big.save(buf, "PNG")
    k1, w, _ = store_upload(buf.getvalue(), "wide.png", tmp_path)
    k2, _, _ = store_upload(buf.getvalue(), "again.png", tmp_path)
    assert w <= 2400
    assert k1 == k2 and len(list(tmp_path.glob(f"{k1}.*"))) == 1


@pytest.mark.parametrize("name,blob,why", [
    ("x.svg", b"<svg onload='alert(1)'/>", "SVG"),
    ("x.bmp", b"BM....", "PNG, JPEG"),
    ("x.png", b"not an image", "readable"),
    ("x.png", b"", "empty"),
])
def test_upload_refuses_what_a_deck_cannot_carry(tmp_path, name, blob, why):
    with pytest.raises(ImageRefused, match=why):
        store_upload(blob, name, tmp_path)


# ---------------------------------------------------------------- set_src
IMG_SPEC = """<meta>{"pattern":"image-focus","title":"T","steps":1}</meta>
<html><h1 class="title">Stack</h1><figure class="figure"><img src="asset:img1" alt="stack"></figure></html>
<css></css><script>function go(root, step){}</script>"""


def _spec():
    spec, _ = parse_spec(IMG_SPEC, "s1")
    return ensure_ids(spec)


def _img_eid(spec) -> str:
    return next(e.eid for e in outline(spec) if e.tag == "img")


def test_outline_names_the_asset_an_image_shows():
    spec = _spec()
    assert next(e for e in outline(spec) if e.tag == "img").asset == "img1"


def test_set_src_swaps_the_picture_for_a_deck_asset():
    spec = _spec()
    r = apply_ops(spec, parse_ops([{"op": "set_src", "eid": _img_eid(spec), "key": "u_abc"}]), assets={"img1", "u_abc"})
    assert r.ok and 'src="asset:u_abc"' in r.spec.html


@pytest.mark.parametrize("key,code", [("u_missing", "unknown-asset"), ("https://x.y/a.png", "bad-asset"), ("hp", "bad-asset")])
def test_set_src_refuses_anything_but_a_deck_image(key, code):
    spec = _spec()
    r = apply_ops(spec, parse_ops([{"op": "set_src", "eid": _img_eid(spec), "key": key}]), assets={"img1"})
    assert not r.ok and r.error_code == code


def test_set_src_only_applies_to_images():
    spec = _spec()
    h1 = next(e.eid for e in outline(spec) if e.tag == "h1")
    r = apply_ops(spec, parse_ops([{"op": "set_src", "eid": h1, "key": "img1"}]), assets={"img1"})
    assert not r.ok and r.error_code == "not-image"


def test_resizing_an_image_may_lift_the_figure_cap():
    spec = _spec()
    r = apply_ops(spec, parse_ops([{"op": "set_style", "eid": _img_eid(spec),
                                    "style": {"width": "900px", "height": "auto", "max-width": "none",
                                              "max-height": "none", "object-fit": "contain"}}]))
    assert r.ok, r.error


# ---------------------------------------------------------------- the HTTP surface
@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _pptx_slide() -> tuple[Project, Slide]:
    p = db.save(Project(name="imgs", filename="imgs.pptx", status="ready"))
    s = db.save(Slide(project_id=p.id, index=1, position=1,
                      content=SlideContent(index=1, title="Our stack").model_dump()))
    return p, s


def test_upload_then_attach_puts_the_image_on_the_slide_content(client):
    p, s = _pptx_slide()
    up = client.post(f"/api/projects/{p.id}/assets", files={"file": ("stack.png", _png(), "image/png")})
    assert up.status_code == 200, up.text
    key = up.json()["key"]
    assert any(a["key"] == key and a["upload"] for a in client.get(f"/api/projects/{p.id}/assets").json())

    assert client.post(f"/api/slides/{s.id}/images", json={"key": key, "alt": "The stack"}).status_code == 200
    row = db.get(Slide, s.id)
    assert row.content.get("images", []) == [], "a converted slide's parse stays recoverable"
    imgs = runner.content_for_prompt(row)["images"]
    assert imgs[0]["key"] == key and imgs[0]["source"] == "upload" and imgs[0]["px"] != "0x0"
    assert not runner.Ctx(row).verbatim, "attaching a picture is not approving the copy word for word"

    client.post(f"/api/slides/{s.id}/images", json={"key": key, "detach": True})
    assert "images" not in runner.content_for_prompt(db.get(Slide, s.id))


def test_attach_refuses_an_image_the_deck_does_not_have(client):
    _, s = _pptx_slide()
    assert client.post(f"/api/slides/{s.id}/images", json={"key": "u_nope"}).status_code == 400


def test_upload_refusal_is_a_400_with_a_readable_reason(client):
    p, _ = _pptx_slide()
    r = client.post(f"/api/projects/{p.id}/assets", files={"file": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 400 and "SVG" in r.json()["detail"]


def test_revise_with_an_image_attaches_it_and_names_it(client, monkeypatch):
    p, s = _pptx_slide()
    spec, _ = parse_spec(IMG_SPEC, s.id)
    v = db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready", spec=spec.model_dump()))
    key = client.post(f"/api/projects/{p.id}/assets", files={"file": ("a.png", _png(), "image/png")}).json()["key"]
    seen = {}

    async def fake_revise(sid, vid, comment):
        seen["comment"] = comment

    monkeypatch.setattr(runner, "revise", fake_revise)
    r = client.post(f"/api/slides/{s.id}/revise", json={"base_version_id": v.id, "comment": "", "asset_keys": [key]})
    assert r.status_code == 200, r.text
    for _ in range(50):
        if seen:
            break
        asyncio.run(asyncio.sleep(0.01))
    assert f"asset:{key}" in seen["comment"]
    assert runner.content_for_prompt(db.get(Slide, s.id))["images"][0]["key"] == key


# ---------------------------------------------------------------- QA
def test_qa_warns_when_the_slide_subject_is_a_thumbnail(tmp_path):
    f = tmp_path / "big.png"
    Image.new("RGB", (1400, 900), (30, 60, 120)).save(f)
    raw = IMG_SPEC.replace("asset:img1", "asset:big").replace("<css></css>", "<css>.figure img{width:220px}</css>")
    spec, _ = parse_spec(raw, "t")
    rep = asyncio.run(check_spec(spec, "t", {"big": f}, tmp_path / "out"))
    assert "image-small" in {x.code for x in rep.findings}, [x.message for x in rep.findings]
