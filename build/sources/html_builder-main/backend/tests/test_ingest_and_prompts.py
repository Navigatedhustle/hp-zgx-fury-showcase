import io
import re

import pytest
from conftest import DECKS
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from app.ingest import pptx_parse, render, vector
from app.ingest.pptx_parse import STAGE_H, STAGE_W, SlideContent, _Ctx, _walk, parse_pptx
from app.pipeline import mock, prompts
from app import facts as F
from app.qa.render_check import ledger_findings
from app.skillpack import read, system_prompt

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
EMU_PER_STAGE_PX = 7620  # 13.333in x 7.5in over a 1600x900 stage
IMG = DECKS.parents[1] / "runtime" / "img" / "fury.svg"


# ------------------------------------------------------------------ fixtures built with python-pptx
def _widescreen() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def _xfrm(group):
    pr = group._element.find(qn("p:grpSpPr"))
    xf = pr.find(A + "xfrm")
    return xf if xf is not None else etree.SubElement(pr, A + "xfrm")


def _set_group_xfrm(group, off, ext, ch_off, ch_ext) -> None:
    """Move and scale a group the way a designer dragging it in PowerPoint does."""
    xf = _xfrm(group)
    for tag, (ax, ay), (vx, vy) in (("off", ("x", "y"), off), ("ext", ("cx", "cy"), ext),
                                    ("chOff", ("x", "y"), ch_off), ("chExt", ("cx", "cy"), ch_ext)):
        el = xf.find(A + tag)
        if el is None:
            el = etree.SubElement(xf, A + tag)
        el.set(ax, str(vx))
        el.set(ay, str(vy))


def _group_deck(path):
    prs = _widescreen()

    # slide 1: a group holding two text boxes, then moved to (500,250) on the stage and scaled 2x
    s = prs.slides.add_slide(prs.slide_layouts[6])
    grp = s.shapes.add_group_shape()
    for i, (x, y, text) in enumerate(((762000, 762000, "Grouped headline"), (1524000, 1143000, "Grouped detail"))):
        tb = grp.shapes.add_textbox(Emu(x), Emu(y), Emu(381000), Emu(190500))
        tb.text_frame.text = text
    _set_group_xfrm(grp, off=(3810000, 1905000), ext=(2286000, 1143000),
                    ch_off=(762000, 762000), ch_ext=(1143000, 571500))

    # slide 2: a small picture inside a group scaled 8x — tiny in child space, a hero image on the stage
    s = prs.slides.add_slide(prs.slide_layouts[6])
    g2 = s.shapes.add_group_shape()
    g2.shapes.add_picture(str(IMG), Emu(0), Emu(0), Emu(381000), Emu(190500))
    _set_group_xfrm(g2, off=(1524000, 1524000), ext=(3048000, 1524000), ch_off=(0, 0), ch_ext=(381000, 190500))

    # slide 3: a group inside a group, each with its own scale
    s = prs.slides.add_slide(prs.slide_layouts[6])
    outer = s.shapes.add_group_shape()
    inner = outer.shapes.add_group_shape()
    tb = inner.shapes.add_textbox(Emu(0), Emu(0), Emu(381000), Emu(190500))
    tb.text_frame.text = "Nested"
    _set_group_xfrm(inner, off=(0, 0), ext=(762000, 381000), ch_off=(0, 0), ch_ext=(381000, 190500))
    _set_group_xfrm(outer, off=(762000, 762000), ext=(1524000, 762000), ch_off=(0, 0), ch_ext=(762000, 381000))

    prs.save(str(path))
    return path


def _stage(emu: int) -> int:
    return round(emu / EMU_PER_STAGE_PX)


def _block(sc, text):
    return next(t for t in sc.texts if any(p.text == text for p in t.paragraphs))


# ------------------------------------------------------------------ existing coverage
def test_parse_workstation_deck(tmp_path):
    d = parse_pptx(DECKS / "hp_z_workstations_genai.pptx", tmp_path)
    assert len(d.slides) == 10
    s3, s4, s5, s6 = d.slides[2], d.slides[3], d.slides[4], d.slides[5]
    assert s3.title.startswith("Challenges") and s3.notes
    assert any(p.level == 1 for t in s3.texts for p in t.paragraphs)
    assert s4.charts and s4.charts[0].series[0].values == [180, 220, 310, 420, 530, 610]
    assert s5.tables and s5.tables[0].rows[-1] == ["3-year total", "$1,576,000", "$417,000"]
    assert s6.images and (tmp_path / f"{s6.images[0].key}.png").exists()
    assert d.slides[9].title == "Thank you"


def test_numbers_and_fidelity():
    """The ledger replaces the bag of digits; see tests/test_facts.py for the unit-level behaviour."""
    src = {"text": [{"lines": ["Spend 240% on 12 teams"]}]}
    fs = F.extract(src)
    assert not ledger_findings(fs, "240% across 12 teams")
    gone = ledger_findings(fs, "a lot")
    assert gone and gone[0].code == "fidelity" and not gone[0].fatal, "a dropped fact is a shortfall"
    moved = ledger_findings(fs, "Spend 310% on 12 teams")
    assert moved[0].code == "fidelity-changed" and moved[0].fatal, "a moved value is never shippable"


def test_system_prompt_has_no_unfilled_placeholders():
    sp = system_prompt()
    assert "{{" not in sp and "check" in sp and "Gold examples" in sp


def test_every_task_prompt_fills_every_placeholder(tmp_path):
    """Every {{PLACEHOLDER}} in skill/*.md must be filled by whoever builds that prompt."""
    d = parse_pptx(DECKS / "hp_wolf_print_security.pptx", tmp_path)
    items = [{"index": s.index, "content": s.for_prompt()} for s in d.slides]
    plan = mock.plan(items)
    content = items[1]["content"]
    spec_obj = None
    texts = {}
    for v in ("A", "B"):
        texts[f"generate {v}"] = prompts.generate_messages(
            variant=v, position=2, total=5, brief=plan, plan=plan["slides"][1], content=content,
            prev_plan=plan["slides"][0], next_plan=plan["slides"][2], source_png=None, vision=False)[-1]["content"]
        assert f"variant {v}" in texts[f"generate {v}"]
    from app.spec import parse_spec, to_tagged
    spec_obj = parse_spec(to_tagged(mock.spec(content, plan["slides"][1], "A")), "s1")[0]
    texts["repair"] = prompts.repair_messages(variant="A", position=2, plan=plan["slides"][1], content=content, spec=spec_obj,
                                              slide_id="s1", issues=["[overflow] x"], shot=None, vision=False)[-1]["content"]
    assert "[overflow] x" in texts["repair"]
    for label, other in (("revise", None), ("revise+other", spec_obj)):
        texts[label] = prompts.revise_messages(variant="A", position=2, plan=plan["slides"][1], content=content, spec=spec_obj,
                                               slide_id="s1", comment="make it calmer", other=other,
                                               other_id="s2" if other else None, shot=None, vision=False)[-1]["content"]
    assert "make it calmer" in texts["revise"]
    texts["critic"] = prompts.critic_messages(variant="A", plan=plan["slides"][1], content=content,
                                              qa_findings=[{"severity": "warn", "message": "tight"}], shots=[],
                                              source_png=None)[-1]["content"]
    texts["plan"] = prompts.plan_messages(items)[-1]["content"]
    # judge.md is filled by evals/run_eval.py with these three keys
    texts["judge"] = prompts._fill(read("judge.md"), CONTENT="{}", CANDIDATE_STEPS=2, REFERENCE_STEPS=3)
    for label, text in texts.items():
        assert not re.search(r"\{\{[A-Z_]+\}\}", text), f"{label} left a placeholder unfilled"


# ------------------------------------------------------------------ group transforms (item 1)
def test_group_children_use_the_group_transform(tmp_path):
    d = parse_pptx(_group_deck(tmp_path / "groups.pptx"), tmp_path / "assets")
    head = _block(d.slides[0], "Grouped headline")
    detail = _block(d.slides[0], "Grouped detail")
    # group moved to (3810000, 1905000) EMU and scaled 2x: child offsets scale with it
    assert head.box == [_stage(3810000), _stage(1905000), _stage(762000), _stage(381000)]
    assert detail.box == [_stage(5334000), _stage(2667000), _stage(762000), _stage(381000)]
    assert pptx_parse._where(detail.box) == "middle center"


def test_grouped_image_is_not_mistaken_for_decoration(tmp_path):
    d = parse_pptx(_group_deck(tmp_path / "groups.pptx"), tmp_path / "assets")
    sc = d.slides[1]
    assert len(sc.images) == 1
    img = sc.images[0]
    assert img.box == [_stage(1524000), _stage(1524000), _stage(3048000), _stage(1524000)]
    assert not img.decorative and img.source == "embedded"
    assert sc.for_prompt().get("images"), "a grouped hero image must reach the model"


def test_nested_groups_compose(tmp_path):
    d = parse_pptx(_group_deck(tmp_path / "groups.pptx"), tmp_path / "assets")
    nested = _block(d.slides[2], "Nested")
    # inner scales 2x, outer scales 2x again -> 4x, offset by the outer group's position
    assert nested.box == [_stage(762000), _stage(762000), _stage(1524000), _stage(762000)]


def test_unmoved_group_is_unchanged(tmp_path):
    prs = _widescreen()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    grp = s.shapes.add_group_shape()
    tb = grp.shapes.add_textbox(Emu(1524000), Emu(762000), Emu(762000), Emu(381000))
    tb.text_frame.text = "Untouched"
    p = tmp_path / "plain_group.pptx"
    prs.save(str(p))
    d = parse_pptx(p, tmp_path / "assets")
    assert _block(d.slides[0], "Untouched").box == [_stage(1524000), _stage(762000), _stage(762000), _stage(381000)]


# ------------------------------------------------------------------ hidden slides (item 4)
def _three_slides(path, hide: int | None = None):
    prs = _widescreen()
    for i, t in enumerate(("First", "Second", "Third"), start=1):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = t
        if hide == i:
            s._element.set("show", "0")
    prs.save(str(path))
    return path


def test_hidden_slides_are_skipped_so_renders_line_up(tmp_path):
    d = parse_pptx(_three_slides(tmp_path / "hidden.pptx", hide=2), tmp_path / "assets")
    assert [s.index for s in d.slides] == [1, 2]
    assert [s.title for s in d.slides] == ["First", "Third"]
    assert [s.source_index for s in d.slides] == [1, 3]
    assert d.hidden == [2]
    assert render.visible_slide_count(tmp_path / "hidden.pptx") == 2


def test_renderer_count_agrees_with_parser(tmp_path):
    p = _three_slides(tmp_path / "visible.pptx")
    d = parse_pptx(p, tmp_path / "assets")
    assert render.visible_slide_count(p) == len(d.slides) == 3
    assert not d.hidden


def test_render_slides_clears_stale_images_when_it_cannot_render(tmp_path):
    out = tmp_path / "renders"
    out.mkdir()
    (out / "001.png").write_bytes(b"stale")
    assert render.render_slides(tmp_path / "missing.pptx", out, "libreoffice") == "none"
    assert not list(out.glob("[0-9][0-9][0-9].png"))


# ------------------------------------------------------------------ title heuristic
def test_slide_without_a_title_placeholder(tmp_path):
    prs = _widescreen()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(1)).text_frame
    tb.text = "Where we are today"
    tb.paragraphs[0].font.size = Pt(40)
    body = s.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(3)).text_frame
    body.text = "Queues delay experiments"
    body.add_paragraph().text = "Egress fees add 18%"
    body.add_paragraph().text = "Data cannot leave the network"

    s2 = prs.slides.add_slide(prs.slide_layouts[6])
    low = s2.shapes.add_textbox(Inches(1), Inches(5.5), Inches(8), Inches(1.5)).text_frame
    low.text = "Footnote one"
    for extra in ("Footnote two", "Footnote three"):
        low.add_paragraph().text = extra
    p = tmp_path / "untitled.pptx"
    prs.save(str(p))

    d = parse_pptx(p, tmp_path / "assets")
    assert d.slides[0].title == "Where we are today"
    assert [t.kind for t in d.slides[0].texts][0] == "title"
    assert d.slides[1].title == ""  # nothing near the top and too much text to guess


# ------------------------------------------------------------------ SmartArt / OLE / crop fallback (items 2, 3)
SMARTART = f"""<p:graphicFrame xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
  xmlns:a="{A[1:-1]}" xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:nvGraphicFramePr><p:cNvPr id="4" name="Diagram 1"/></p:nvGraphicFramePr>
  <p:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/diagram">
    <dgm:relIds r:dm="rId2" r:lo="rId3" r:qs="rId4" r:cs="rId5"/>
  </a:graphicData></p:graphic></p:graphicFrame>"""

DIAGRAM_DATA = f"""<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:a="{A[1:-1]}">
  <dgm:ptLst>
    <dgm:pt modelId="1"><dgm:t><a:p><a:r><a:t>Assess</a:t></a:r></a:p></dgm:t></dgm:pt>
    <dgm:pt modelId="2"><dgm:t><a:p><a:r><a:t>Protect</a:t></a:r><a:r><a:t> the fleet</a:t></a:r></a:p></dgm:t></dgm:pt>
    <dgm:pt modelId="3"><dgm:t><a:p/></dgm:t></dgm:pt>
  </dgm:ptLst></dgm:dataModel>"""


class _FakePart:
    def __init__(self, blob: bytes | None):
        self.blob = blob

    def related_part(self, rid: str):
        if self.blob is None or rid != "rId2":
            raise KeyError(rid)
        return _FakePart(self.blob)


class _FakeShape:
    """Minimal stand-in for the shapes python-pptx cannot model (SmartArt, OLE)."""

    def __init__(self, xml: str, shape_type=None, *, name="Diagram 1", blob: bytes | None = None,
                 left=0, top=0, width=Emu(7620 * 800), height=Emu(7620 * 400)):
        self._element = etree.fromstring(xml)
        self.shape_type = shape_type
        self.name = name
        self.part = _FakePart(blob)
        self.left, self.top, self.width, self.height = left, top, width, height
        self.has_chart = self.has_table = self.has_text_frame = self.is_placeholder = False


def _ctx(tmp_path, renders: bool = False) -> tuple[_Ctx, SlideContent]:
    assets = tmp_path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    rdir = tmp_path / "renders"
    if renders:
        rdir.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (1600, 900), "white")
        im.paste(Image.new("RGB", (600, 300), (200, 30, 40)), (100, 100))
        im.save(rdir / "001.png")
    return _Ctx(assets, 12192000, 6858000, rdir if renders else None), SlideContent(index=1, source_index=1)


def test_smartart_text_is_extracted(tmp_path):
    ctx, sc = _ctx(tmp_path)
    shape = _FakeShape(SMARTART, blob=DIAGRAM_DATA.encode())
    assert pptx_parse._smartart_text(shape) == ["Assess", "Protect the fleet"]
    _walk([shape], ctx, sc)
    assert [p.text for t in sc.texts for p in t.paragraphs] == ["Assess", "Protect the fleet"]
    assert sc.texts[0].kind == "body"
    assert sc.warnings and "text only" in sc.warnings[0]  # no render to crop the layout from


def test_smartart_without_a_diagram_part_is_not_lost(tmp_path):
    ctx, sc = _ctx(tmp_path, renders=True)
    _walk([_FakeShape(SMARTART, blob=None)], ctx, sc)
    assert not sc.texts and not sc.warnings
    assert len(sc.images) == 1 and sc.images[0].source == "render-crop"
    assert (tmp_path / "assets" / f"{sc.images[0].key}.png").exists()


def test_ole_object_is_cropped_out_of_the_reference_render(tmp_path):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    ctx, sc = _ctx(tmp_path, renders=True)
    shape = _FakeShape("<p:x xmlns:p='http://x'/>", MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT, name="Worksheet",
                       left=Emu(7620 * 100), top=Emu(7620 * 100), width=Emu(7620 * 600), height=Emu(7620 * 300))
    _walk([shape], ctx, sc)
    assert not sc.warnings
    img = sc.images[0]
    assert img.source == "render-crop" and not img.decorative and img.box == [100, 100, 600, 300]
    with Image.open(tmp_path / "assets" / f"{img.key}.png") as im:
        assert (im.width, im.height) == (600, 300) and im.convert("RGB").getpixel((5, 5)) == (200, 30, 40)
    assert sc.for_prompt()["images"][0]["px"] == "600x300"


def test_ole_object_without_a_render_still_warns(tmp_path):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    ctx, sc = _ctx(tmp_path)
    _walk([_FakeShape("<p:x xmlns:p='http://x'/>", MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT, name="Worksheet")], ctx, sc)
    assert not sc.images and sc.warnings and "Worksheet" in sc.warnings[0]


# ------------------------------------------------------------------ EMF/WMF (item 2)
def test_vector_images_are_converted(tmp_path, monkeypatch):
    png = io.BytesIO()
    Image.new("RGB", (120, 60), "blue").save(png, "PNG")
    monkeypatch.setattr(pptx_parse, "to_png", lambda blob, ext: png.getvalue())
    ctx, _ = _ctx(tmp_path)
    saved = ctx.save_image(b"\x01\x00\x00\x00" + b"fake emf", "emf")
    assert saved and saved[1:] == (120, 60)
    assert (tmp_path / "assets" / f"{saved[0]}.png").exists()


def test_vector_image_without_libreoffice_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pptx_parse, "to_png", lambda blob, ext: None)
    ctx, _ = _ctx(tmp_path)
    assert ctx.save_image(b"fake emf", "emf") is None


def test_sniff_ext():
    assert vector.sniff_ext(b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF") == "emf"
    assert vector.sniff_ext(b"\xd7\xcd\xc6\x9a" + b"\x00" * 40) == "wmf"
    assert vector.sniff_ext(b"\x89PNG\r\n\x1a\n") == ""


def test_missing_asset_file_is_resaved(tmp_path):
    """A vanished asset must not blow up the second shape that references the same image."""
    ctx, _ = _ctx(tmp_path)
    blob = io.BytesIO()
    Image.new("RGB", (40, 40), "green").save(blob, "PNG")
    first = ctx.save_image(blob.getvalue(), "png")
    (tmp_path / "assets" / f"{first[0]}.png").unlink()
    second = ctx.save_image(blob.getvalue(), "png")
    assert second and (tmp_path / "assets" / f"{second[0]}.png").exists()


# ------------------------------------------------------------------ theme (item 5)
def test_theme_is_extracted(tmp_path):
    d = parse_pptx(DECKS / "hp_wolf_print_security.pptx", tmp_path)
    t = d.theme
    assert t.name and t.major_font and t.minor_font
    assert {"dk1", "lt1", "accent1", "accent6"} <= set(t.colors)
    assert all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in t.colors.values())
    assert len(t.accents) == 6


def test_theme_of_a_non_pptx_is_empty(tmp_path):
    bad = tmp_path / "not.pptx"
    bad.write_bytes(b"nope")
    from app.ingest.theme import parse_theme

    assert parse_theme(bad).colors == {}


@pytest.mark.parametrize("box, where", [([0, 0, 1600, 900], "full slide"), ([1300, 700, 200, 100], "bottom right")])
def test_where(box, where):
    assert pptx_parse._where(box) == where
    assert STAGE_W == 1600 and STAGE_H == 900
