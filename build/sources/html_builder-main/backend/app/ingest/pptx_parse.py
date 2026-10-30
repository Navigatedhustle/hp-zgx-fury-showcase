"""PPTX -> structured SlideContent (text hierarchy, tables, charts, images, notes)."""
from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.util import Emu
from pydantic import BaseModel, Field

from ..images import trim_margins
from .theme import DeckTheme, parse_theme
from .vector import VECTOR_EXT, sniff_ext, to_png

log = logging.getLogger(__name__)

STAGE_W, STAGE_H = 1600, 900
WEB_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"}
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MIN_CROP_PX = 8


class Paragraph(BaseModel):
    text: str
    level: int = 0
    bold: bool = False


class TextBlock(BaseModel):
    kind: str = "text"  # title | subtitle | body | text
    paragraphs: list[Paragraph]
    box: list[int] = Field(default_factory=list)  # x, y, w, h on a 1600x900 stage


class TableData(BaseModel):
    rows: list[list[str]]
    box: list[int] = Field(default_factory=list)


class Series(BaseModel):
    name: str
    values: list[float | None]


class ChartData(BaseModel):
    type: str
    title: str = ""
    categories: list[str] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    box: list[int] = Field(default_factory=list)


class ImageRef(BaseModel):
    key: str
    alt: str = ""
    width: int = 0
    height: int = 0
    box: list[int] = Field(default_factory=list)
    decorative: bool = False
    source: str = "embedded"  # embedded | converted (EMF/WMF) | render-crop | upload (the user's own)


class SlideContent(BaseModel):
    index: int  # 1-based, counting visible slides only — matches renders/{index:03d}.png
    source_index: int = 0  # 1-based position in the source deck, hidden slides included
    layout: str = ""
    title: str = ""
    texts: list[TextBlock] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)
    charts: list[ChartData] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)

    def for_prompt(self) -> dict:
        """Compact representation for LLM prompts."""
        out: dict = {"title": self.title}
        body = []
        for t in self.texts:
            if t.kind == "title":
                continue
            lines = [("  " * p.level) + ("**" + p.text + "**" if p.bold else p.text) for p in t.paragraphs]
            body.append({"kind": t.kind, "position": _where(t.box), "lines": lines})
        if body:
            out["text"] = body
        if self.tables:
            out["tables"] = [t.rows for t in self.tables]
        if self.charts:
            out["charts"] = [c.model_dump(exclude={"box"}) for c in self.charts]
        imgs = [i for i in self.images if not i.decorative]
        if imgs:
            out["images"] = [{"key": i.key, "alt": i.alt, "position": _where(i.box), "px": f"{i.width}x{i.height}",
                              **({"source": "upload"} if i.source == "upload" else {})} for i in imgs]
        if self.notes:
            out["speaker_notes"] = self.notes
        return out


def _where(box: list[int]) -> str:
    if len(box) != 4:
        return ""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    if w > STAGE_W * 0.8 and h > STAGE_H * 0.8:
        return "full slide"
    horiz = "left" if cx < STAGE_W * 0.4 else "right" if cx > STAGE_W * 0.6 else "center"
    vert = "top" if cy < STAGE_H * 0.35 else "bottom" if cy > STAGE_H * 0.65 else "middle"
    return f"{vert} {horiz}"


class ParsedDeck(BaseModel):
    title: str
    slides: list[SlideContent]
    theme: DeckTheme = Field(default_factory=DeckTheme)
    hidden: list[int] = Field(default_factory=list)  # source positions skipped because the slide is hidden


@dataclass(frozen=True)
class Transform:
    """Affine map from a shape's own coordinate space into slide EMU space.

    A group carries both where it sits (`a:off`/`a:ext`) and the coordinate space its children are
    written in (`a:chOff`/`a:chExt`). They only coincide while the group has never been moved or
    resized, so children need the scale+translate applied, composed through nested groups.
    """

    sx: float = 1.0
    sy: float = 1.0
    dx: float = 0.0
    dy: float = 0.0


IDENTITY = Transform()


def _child_transform(group_shape, tf: Transform) -> Transform:
    """Transform for the children of `group_shape`, composed onto the enclosing `tf`."""
    try:
        xfrm = group_shape._element.xpath("./*[local-name()='grpSpPr']/*[local-name()='xfrm']")
        if not xfrm:
            return tf

        def point(tag: str, ax: str, ay: str) -> tuple[int, int] | None:
            node = xfrm[0].find(f"{{{A_NS}}}{tag}")
            if node is None:
                return None
            return int(node.get(ax) or 0), int(node.get(ay) or 0)

        off, ext = point("off", "x", "y"), point("ext", "cx", "cy")
        ch_off, ch_ext = point("chOff", "x", "y"), point("chExt", "cx", "cy")
        if not (off and ext and ch_off and ch_ext) or not ch_ext[0] or not ch_ext[1]:
            return tf  # no child space declared (or degenerate): children are already in group space
        sx, sy = ext[0] / ch_ext[0], ext[1] / ch_ext[1]
        return Transform(tf.sx * sx, tf.sy * sy,
                         tf.dx + tf.sx * (off[0] - ch_off[0] * sx),
                         tf.dy + tf.sy * (off[1] - ch_off[1] * sy))
    except Exception as e:  # noqa: BLE001
        log.warning("group transform unreadable (%s); using the parent's", e)
        return tf


def _box(shape, sw: int, sh: int, tf: Transform = IDENTITY) -> list[int]:
    try:
        x = (tf.dx + int(shape.left or 0) * tf.sx) / sw * STAGE_W
        y = (tf.dy + int(shape.top or 0) * tf.sy) / sh * STAGE_H
        w = int(shape.width or 0) * tf.sx / sw * STAGE_W
        h = int(shape.height or 0) * tf.sy / sh * STAGE_H
        return [round(x), round(y), round(w), round(h)]
    except Exception:  # noqa: BLE001
        return []


def _decorative(box: list[int]) -> bool:
    area = (box[2] * box[3]) if len(box) == 4 else 0
    return area < STAGE_W * STAGE_H * 0.012


def _clean(s: str) -> str:
    return " ".join((s or "").replace("\x0b", " ").split())


def _paragraphs(text_frame) -> list[Paragraph]:
    out = []
    for p in text_frame.paragraphs:
        txt = _clean(p.text)
        if not txt:
            continue
        runs = [r for r in p.runs if r.text.strip()]
        bold = bool(runs) and all(bool(r.font.bold) for r in runs)
        out.append(Paragraph(text=txt, level=int(p.level or 0), bold=bold))
    return out


def _chart(shape, box) -> ChartData | None:
    try:
        ch = shape.chart
        cd = ChartData(type=str(ch.chart_type).split(".")[-1].split(" ")[0].lower(), box=box)
        try:
            if ch.has_title and ch.chart_title.has_text_frame:
                cd.title = _clean(ch.chart_title.text_frame.text)
        except Exception:  # noqa: BLE001
            pass
        plot = ch.plots[0]
        cd.categories = [str(c) for c in plot.categories]
        for s in plot.series:
            vals = []
            for v in s.values:
                vals.append(None if v is None else float(v))
            cd.series.append(Series(name=str(s.name or ""), values=vals))
        return cd
    except Exception as e:  # noqa: BLE001
        log.warning("chart extraction failed: %s", e)
        return None


def _smartart_text(shape) -> list[str]:
    """SmartArt text lives in a related diagram data part."""
    try:
        el = shape._element
        rel_ids = el.xpath(".//*[local-name()='relIds']")
        if not rel_ids:
            return []
        dm = rel_ids[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}dm")
        part = shape.part.related_part(dm)
        root = etree.fromstring(part.blob)
        texts = []
        for pt in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/diagram}pt"):
            t = _clean(" ".join(x.text or "" for x in pt.iter(f"{{{A_NS}}}t")))
            if t:
                texts.append(t)
        return texts
    except Exception:  # noqa: BLE001
        return []


def is_hidden(slide) -> bool:
    """A slide marked `show="0"` is skipped by PowerPoint and by LibreOffice's PDF export."""
    try:
        return slide._element.get("show") == "0"
    except Exception:  # noqa: BLE001
        return False


class _Ctx:
    def __init__(self, assets_dir: Path, sw: int, sh: int, renders_dir: Path | None = None):
        self.assets_dir = assets_dir
        self.renders_dir = renders_dir
        self.sw, self.sh = sw, sh
        self.seen: dict[str, str] = {}
        self.counter = 0

    def _existing(self, key: str) -> tuple[str, int, int] | None:
        f = next(iter(sorted(self.assets_dir.glob(f"{key}.*"))), None)
        if f is None:
            return None  # asset vanished under us: fall through and write it again
        if f.suffix == ".svg":
            return key, 0, 0
        try:
            with Image.open(f) as im:
                return key, im.width, im.height
        except Exception:  # noqa: BLE001
            return None

    def save_image(self, blob: bytes, ext: str) -> tuple[str, int, int] | None:
        digest = hashlib.sha1(blob).hexdigest()[:12]
        if digest in self.seen:
            found = self._existing(self.seen[digest])
            if found:
                return found
            self.seen.pop(digest, None)
        ext = (ext or "").lower().lstrip(".")
        if ext in VECTOR_EXT:
            png = to_png(blob, ext)
            if png is None:
                return None
            blob, ext = png, "png"
        if ext not in WEB_IMAGE_EXT:
            return None
        self.counter += 1
        key = f"img{self.counter}"
        if ext == "svg":
            (self.assets_dir / f"{key}.svg").write_bytes(blob)
            self.seen[digest] = key
            return key, 0, 0
        try:
            im = Image.open(io.BytesIO(blob))
            im.load()
        except Exception:  # noqa: BLE001
            return None
        im = trim_margins(im)  # a diagram inside a wide white frame lays out as a small island
        if im.width > 2000:
            im.thumbnail((2000, 2000))
        has_alpha = im.mode in ("RGBA", "LA", "P") and ("transparency" in im.info or im.mode != "P")
        if has_alpha or ext in ("png", "gif"):
            out = self.assets_dir / f"{key}.png"
            im.save(out, "PNG", optimize=True)
        else:
            out = self.assets_dir / f"{key}.jpg"
            im.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
        self.seen[digest] = key
        return key, im.width, im.height

    def render_png(self, slide_index: int) -> Path | None:
        if not self.renders_dir:
            return None
        p = self.renders_dir / f"{slide_index:03d}.png"
        return p if p.exists() else None

    def crop(self, slide_index: int, box: list[int]) -> tuple[str, int, int] | None:
        """Cut `box` (stage coordinates) out of the reference render and save it like any other asset."""
        png = self.render_png(slide_index)
        if png is None or len(box) != 4:
            return None
        try:
            with Image.open(png) as im:
                im.load()
                fx, fy = im.width / STAGE_W, im.height / STAGE_H
                left, top = max(0, int(box[0] * fx)), max(0, int(box[1] * fy))
                right = min(im.width, int((box[0] + box[2]) * fx))
                bottom = min(im.height, int((box[1] + box[3]) * fy))
                if right - left < MIN_CROP_PX or bottom - top < MIN_CROP_PX:
                    return None
                region = im.convert("RGB").crop((left, top, right, bottom))
            buf = io.BytesIO()
            region.save(buf, "PNG", optimize=True)
            return self.save_image(buf.getvalue(), "png")
        except Exception as e:  # noqa: BLE001
            log.warning("render crop failed for slide %d: %s", slide_index, e)
            return None


def _image_ext(image, shape) -> str:
    """python-pptx raises on formats it cannot name (EMF); sniff the blob instead of losing the shape."""
    try:
        return (image.ext or "").lower()
    except Exception:  # noqa: BLE001
        pass
    ext = sniff_ext(image.blob)
    if ext:
        return ext
    name = getattr(image, "filename", "") or getattr(shape, "name", "")
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _recover(ctx: _Ctx, sc: SlideContent, box: list[int], alt: str, warning: str) -> None:
    """Last resort for a shape we could not parse: crop it out of the reference render.

    The pixels are already there and the box is known, so the model gets a picture instead of a hole.
    The warning survives only when there is no render to crop from (RENDERER=none).
    """
    saved = ctx.crop(sc.index, box)
    if saved is None:
        sc.warnings.append(warning)
        return
    key, w, h = saved
    sc.images.append(ImageRef(key=key, alt=_clean(alt), width=w, height=h, box=box,
                              decorative=_decorative(box), source="render-crop"))


def _walk(shapes, ctx: _Ctx, sc: SlideContent, tf: Transform = IDENTITY):
    for shape in shapes:
        try:
            box = _box(shape, ctx.sw, ctx.sh, tf)
            st = shape.shape_type
            if st == MSO_SHAPE_TYPE.GROUP:
                _walk(shape.shapes, ctx, sc, _child_transform(shape, tf))
                continue
            if getattr(shape, "has_chart", False) and shape.has_chart:
                cd = _chart(shape, box)
                if cd:
                    sc.charts.append(cd)
                else:
                    _recover(ctx, sc, box, f"chart: {shape.name}", f"chart '{shape.name}' could not be read")
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[_clean(c.text) for c in r.cells] for r in shape.table.rows]
                rows = [r for r in rows if any(r)]
                if rows:
                    sc.tables.append(TableData(rows=rows, box=box))
                continue
            image = None
            if st == MSO_SHAPE_TYPE.PICTURE or (shape.is_placeholder and hasattr(shape, "image")):
                try:
                    image = shape.image
                except Exception:  # noqa: BLE001
                    image = None
            if image is not None or st == MSO_SHAPE_TYPE.PICTURE:
                ext = _image_ext(image, shape) if image is not None else ""
                saved = ctx.save_image(image.blob, ext) if image is not None else None
                if saved:
                    key, w, h = saved
                    alt = ""
                    try:
                        alt = shape._element.xpath("./*[1]/*[local-name()='cNvPr']")[0].get("descr") or ""
                    except Exception:  # noqa: BLE001
                        pass
                    sc.images.append(ImageRef(key=key, alt=_clean(alt or shape.name), width=w, height=h, box=box,
                                              decorative=_decorative(box),
                                              source="converted" if ext in VECTOR_EXT else "embedded"))
                else:
                    _recover(ctx, sc, box, shape.name or "image",
                             f"skipped image '{shape.name}' ({ext or 'unknown format'}) — not a web format")
                continue
            if st in (MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT, MSO_SHAPE_TYPE.LINKED_OLE_OBJECT, MSO_SHAPE_TYPE.MEDIA):
                _recover(ctx, sc, box, f"embedded object: {shape.name}", f"skipped {st} '{shape.name}'")
                continue
            if shape.has_text_frame:
                paras = _paragraphs(shape.text_frame)
                if not paras:
                    continue
                kind = "text"
                if shape.is_placeholder:
                    pt = shape.placeholder_format.type
                    if pt in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE):
                        kind = "title"
                    elif pt == PP_PLACEHOLDER.SUBTITLE:
                        kind = "subtitle"
                    elif pt in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.VERTICAL_BODY):
                        kind = "body"
                    elif pt in (PP_PLACEHOLDER.SLIDE_NUMBER, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.DATE):
                        continue
                sc.texts.append(TextBlock(kind=kind, paragraphs=paras, box=box))
                continue
            if _is_diagram(shape):
                # SmartArt: the text comes out of the diagram part, the layout does not — crop it as well.
                smart = _smartart_text(shape)
                if smart:
                    sc.texts.append(TextBlock(kind="body", paragraphs=[Paragraph(text=t) for t in smart], box=box))
                _recover(ctx, sc, box, f"SmartArt diagram: {shape.name}",
                         f"SmartArt '{shape.name}' kept as text only — diagram layout not captured"
                         if smart else f"skipped SmartArt '{shape.name}' — no text found")
        except Exception as e:  # noqa: BLE001
            sc.warnings.append(f"shape '{getattr(shape, 'name', '?')}' skipped: {e}")


def _is_diagram(shape) -> bool:
    """A graphicFrame that is neither chart nor table nor OLE: SmartArt (`dgm:relIds`) or similar."""
    try:
        return bool(shape._element.xpath(".//*[local-name()='relIds']"))
    except Exception:  # noqa: BLE001
        return False


def _apply_title(sc: SlideContent) -> None:
    titles = [t for t in sc.texts if t.kind == "title"]
    if titles:
        sc.title = " ".join(p.text for p in titles[0].paragraphs)
        return
    cands = [t for t in sc.texts if len(t.box) == 4 and t.box[1] < STAGE_H * 0.3 and len(t.paragraphs) <= 2]
    if not cands and sum(len(t.paragraphs) for t in sc.texts) <= 2:
        cands = sc.texts[:1]
    if cands:
        cands[0].kind = "title"
        sc.title = " ".join(p.text for p in cands[0].paragraphs)


def parse_pptx(path: Path, assets_dir: Path, renders_dir: Path | None = None) -> ParsedDeck:
    """Parse `path` into per-slide content.

    `renders_dir` holds the reference renders (`{index:03d}.png`, 1-based over visible slides). When it
    exists, shapes this parser cannot read are cropped out of the render and saved as normal assets, so
    render_slides() must have run first. It defaults to the `renders` folder beside `assets_dir`.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    if renders_dir is None:
        renders_dir = assets_dir.parent / "renders"
    prs = Presentation(str(path))
    sw, sh = int(prs.slide_width or Emu(12192000)), int(prs.slide_height or Emu(6858000))
    ctx = _Ctx(assets_dir, sw, sh, renders_dir if renders_dir.exists() else None)
    slides: list[SlideContent] = []
    hidden: list[int] = []
    for source_index, slide in enumerate(prs.slides, start=1):
        if is_hidden(slide):
            # LibreOffice's PDF export drops hidden slides; keeping them here would shift every
            # subsequent slide against renders/{index:03d}.png.
            hidden.append(source_index)
            continue
        sc = SlideContent(index=len(slides) + 1, source_index=source_index,
                          layout=slide.slide_layout.name if slide.slide_layout else "")
        _walk(slide.shapes, ctx, sc)
        # reading order: top-to-bottom, then left-to-right
        sc.texts.sort(key=lambda t: (t.box[1] // 40, t.box[0]) if len(t.box) == 4 else (0, 0))
        _apply_title(sc)
        try:
            if slide.has_notes_slide:
                sc.notes = (slide.notes_slide.notes_text_frame.text or "").strip()
        except Exception:  # noqa: BLE001
            pass
        slides.append(sc)
    if hidden:
        log.info("skipped %d hidden slide(s): %s", len(hidden), hidden)
    title = ""
    try:
        title = prs.core_properties.title or ""
    except Exception:  # noqa: BLE001
        pass
    if not title and slides:
        title = slides[0].title or path.stem
    return ParsedDeck(title=title or path.stem, slides=slides, theme=parse_theme(path), hidden=hidden)
