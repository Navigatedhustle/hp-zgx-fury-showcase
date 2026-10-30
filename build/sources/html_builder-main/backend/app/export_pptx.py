"""PowerPoint export: one rendered image per slide, with the real speaker notes attached — or, with
`editable=True`, the same slide rebuilt with its words and pictures as real PowerPoint text boxes and pictures.

A corporate review loop is a PPTX loop. Reviewers who never open the HTML deck still ask for "the
deck", and a link they have to click is not one. This is the honest 80% of that round trip: every
slide becomes a full-bleed picture of the finished design at its last step, on a 16:9 stage, with the
speaker notes and sources in the notes pane where PowerPoint expects them. Nothing is editable and
nothing is interactive — the HTML file remains the artefact that actually runs.

The pictures come from the QA screenshots that `app/qa/render_check.py` already took (`shot_final.png`
in each version's directory). A version with no screenshot — a deck exported before QA ran, or one
whose shots were cleaned up — is re-rendered through `check_spec`, which is the same entry point the
QA loop and the PDF export drive the renderer through.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from .pipeline import runner
from .qa.extract_layout import SlideLayout, TextBox, extract_layout
from .qa.render_check import check_spec
from .spec import SlideSpec
from .store import db
from .store.db import Project, Slide, Version

log = logging.getLogger(__name__)

# The HTML stage is 1600x900. PowerPoint's own 16:9 default is 13.333" x 7.5" at 914400 EMU/inch, so
# the picture fills the slide exactly and a re-import into a 16:9 template lines up.
SLIDE_W = Emu(12192000)
SLIDE_H = Emu(6858000)
BLANK_LAYOUT = 6

_TAGS = re.compile(r"</?(?:b|i|em|strong)>", re.I)


def _plain(s: str) -> str:
    """Notes are written with a little inline HTML (`<b>`, `<em>`). The notes pane is plain text."""
    return html.unescape(_TAGS.sub("", s)).strip()


@dataclass
class DeckPage:
    slide: Slide
    version: Version
    spec: SlideSpec

    @property
    def shot(self) -> Path:
        return db.version_dir(self.version.project_id, self.version.id) / "shot_final.png"

    def notes(self) -> str:
        lines = [_plain(n) for n in self.spec.meta.notes]
        if self.spec.meta.sources:
            lines += ["", f"Sources: {_plain(self.spec.meta.sources)}"]
        return "\n".join(lines).strip()


def deck_pages(project_id: str, *, fill_unapproved: bool = True) -> list[DeckPage]:
    """The slides that would go into the deck, in order — the same choice `runner.build_deck` makes.

    Deliberately re-derived rather than returned by `build_deck`: that function's job is to produce
    one HTML string, and this export needs the versions behind it, not the markup.
    """
    pages = []
    for s in db.slides_of(project_id):
        if not s.included:
            continue
        v = db.get(Version, s.approved_version_id) if s.approved_version_id else None
        if v is None and fill_unapproved:
            v = runner.best_version(s)
        if v is None or not v.spec:
            continue
        if (s.plan or {}).get(runner.APPENDIX_KEY) and not any(pg.slide.id == runner.APPENDIX_DIVIDER_ID for pg in pages):
            pages.append(_divider_page(project_id))
        pages.append(DeckPage(slide=s, version=v, spec=SlideSpec.model_validate(v.spec)))
    return pages


def _divider_page(project_id: str) -> DeckPage:
    """The "Appendix" section slide. Never stored: it has no shot, so `slide_images` renders it on the spot."""
    spec = runner.appendix_divider()
    slide = Slide(id=runner.APPENDIX_DIVIDER_ID, project_id=project_id, index=0, position=0)
    version = Version(id=f"{runner.APPENDIX_DIVIDER_ID}-divider", slide_id=slide.id, project_id=project_id,
                      lineage="A", number=1, status="ready", spec=spec.model_dump())
    return DeckPage(slide=slide, version=version, spec=spec)


async def slide_images(pages: list[DeckPage], work: Path) -> list[tuple[DeckPage, Path]]:
    """A PNG per page. Existing QA screenshots are reused; anything missing is rendered into `work`.

    Rendering is sequential on purpose: `check_spec` shares one Chromium instance with the QA loop and
    with any concurrent PDF export, and an export is not the thing that should be competing for it.
    """
    out: list[tuple[DeckPage, Path]] = []
    for i, page in enumerate(pages):
        if page.shot.exists():
            out.append((page, page.shot))
            continue
        try:
            d = work / f"slide{i:03d}"
            report = await check_spec(page.spec, page.slide.id, db.asset_files(page.version.project_id), d,
                                      title=page.spec.meta.title or "Export")
            shot = d / "shot_final.png"
            if shot.exists():
                out.append((page, shot))
            else:
                log.warning("pptx export: slide %s produced no screenshot (%d findings)", page.slide.index, len(report.findings))
        except Exception as e:  # noqa: BLE001 — one unrenderable slide must not lose the other 30
            log.warning("pptx export: could not render slide %s: %s", page.slide.index, e)
    return out


def write_pptx(shots: list[tuple[DeckPage, Path]], out: Path) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    blank = prs.slide_layouts[BLANK_LAYOUT]
    for page, png in shots:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(png), 0, 0, width=SLIDE_W, height=SLIDE_H)
        notes = page.notes()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    prs.save(str(out))
    return out


# ------------------------------------------------------------------ the editable export
# The stage is 1600 px across a 13.333" slide: 1 px = 1/120" = 7620 EMU = 0.6 pt.
EMU_PER_PX = SLIDE_W // 1600
PT_PER_PX = 0.6
# The deck's web fonts, by the names PowerPoint knows them. Anything else is passed through as the page named it.
FONT_NAMES = {"archivo": "Archivo", "plexmono": "IBM Plex Mono", "ibm plex mono": "IBM Plex Mono"}
# PowerPoint's font metrics are not the browser's, and a substituted font is usually wider: a little more room
# stops a line that fitted in the browser from wrapping onto a second one and colliding with the next box.
WRAP_SLACK = 0.04
_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}
_RGB = re.compile(r"rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)(?:[ ,/]+([\d.]+))?")


def _emu(px: float) -> Emu:
    return Emu(int(round(px * EMU_PER_PX)))


def _font_name(css_family: str) -> str:
    first = (css_family or "").split(",")[0].strip().strip("'\"")
    return FONT_NAMES.get(first.lower(), first) or "Archivo"


def _color(css: str) -> RGBColor | None:
    m = _RGB.match(css or "")
    if not m or (m.group(4) is not None and float(m.group(4)) == 0):
        return None
    return RGBColor(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _set_background(slide, png: Path) -> None:
    """The design, minus its words and pictures, as the slide's background fill: not a shape, so clicking a
    line of text never grabs a full-slide picture instead."""
    _, rid = slide.part.get_or_add_image_part(str(png))
    csld = slide._element.find(qn("p:cSld"))
    for old in csld.findall(qn("p:bg")):
        csld.remove(old)
    bg = etree.SubElement(csld, qn("p:bg"))
    csld.remove(bg)
    csld.insert(0, bg)
    bgpr = etree.SubElement(bg, qn("p:bgPr"))
    fill = etree.SubElement(bgpr, qn("a:blipFill"), dpi="0", rotWithShape="1")
    etree.SubElement(fill, qn("a:blip"), {qn("r:embed"): rid})
    etree.SubElement(etree.SubElement(fill, qn("a:stretch")), qn("a:fillRect"))
    etree.SubElement(bgpr, qn("a:effectLst"))


def _add_text(slide, t: TextBox) -> None:
    single = t.line and t.h < t.line * 1.5
    w = t.w * (1 + WRAP_SLACK)
    x = t.x - (w - t.w) * {"center": 0.5, "right": 1.0}.get(t.align, 0.0)
    box = slide.shapes.add_textbox(_emu(x), _emu(t.y), _emu(w), _emu(max(t.h, t.line or 0)))
    tf = box.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = not single
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE if t.valign == "middle" else MSO_ANCHOR.TOP
    para = tf.paragraphs[0]

    def style(p) -> None:
        p.alignment = _ALIGN.get(t.align, PP_ALIGN.LEFT)
        if t.line:
            p.line_spacing = Pt(t.line * PT_PER_PX)

    style(para)
    for r in t.runs:
        if r.br:
            para = tf.add_paragraph()
            style(para)
            continue
        run = para.add_run()
        run.text = r.text
        f = run.font
        f.size = Pt(max(1.0, round(r.size * PT_PER_PX * 2) / 2))
        f.name = _font_name(r.family)
        f.bold = r.weight >= 600
        f.italic = r.italic
        f.underline = r.underline
        c = _color(r.color)
        if c is not None:
            f.color.rgb = c
        if r.spacing:
            run._r.get_or_add_rPr().set("spc", str(int(round(r.spacing * PT_PER_PX * 100))))


def write_editable_pptx(slides: list[tuple[DeckPage, SlideLayout]], out: Path) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    blank = prs.slide_layouts[BLANK_LAYOUT]
    for page, lay in slides:
        slide = prs.slides.add_slide(blank)
        _set_background(slide, lay.background)
        for pic in lay.pictures:
            shape = slide.shapes.add_picture(str(pic.path), _emu(pic.x), _emu(pic.y), _emu(pic.w), _emu(pic.h))
            if pic.crop:
                shape.crop_left, shape.crop_right = pic.crop.get("l", 0), pic.crop.get("r", 0)
                shape.crop_top, shape.crop_bottom = pic.crop.get("t", 0), pic.crop.get("b", 0)
            if pic.alt:
                shape._element.nvPicPr.cNvPr.set("descr", pic.alt)
        for t in lay.texts:
            _add_text(slide, t)
        notes = page.notes()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    prs.save(str(out))
    return out


async def slide_layouts(pages: list[DeckPage], work: Path) -> list[tuple[DeckPage, SlideLayout]]:
    """Each page read back out of the browser. Sequential for the same reason as `slide_images`."""
    out = []
    for i, page in enumerate(pages):
        try:
            lay = await extract_layout(page.spec, page.slide.id, db.asset_files(page.version.project_id),
                                       work / f"slide{i:03d}", title=page.spec.meta.title or "Export", number=i + 1)
            if lay.background.exists():
                out.append((page, lay))
        except Exception as e:  # noqa: BLE001 — one unrenderable slide must not lose the other 30
            log.warning("editable pptx export: could not render slide %s: %s", page.slide.index, e)
    return out


async def export_pptx(project_id: str, out: Path, *, fill_unapproved: bool = True,
                      editable: bool = False) -> tuple[Path, dict]:
    """Build the .pptx at `out`. Returns it with the same counts `export/stats` reports."""
    p = db.get(Project, project_id)
    pages = deck_pages(project_id, fill_unapproved=fill_unapproved)
    if editable:
        built = await slide_layouts(pages, out.parent)
        await asyncio.to_thread(write_editable_pptx, built, out)
    else:
        built = await slide_images(pages, out.parent)
        await asyncio.to_thread(write_pptx, built, out)
    stats = {"slides": len(built), "missing": len(pages) - len(built),
             "title": (p.deck_title or p.name) if p else ""}
    log.info("pptx export (%s) for %s: %d slide(s), %d without a picture", "editable" if editable else "pictures",
             project_id, stats["slides"], stats["missing"])
    return out, stats
