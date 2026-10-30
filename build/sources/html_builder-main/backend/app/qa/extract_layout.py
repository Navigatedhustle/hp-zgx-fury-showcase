"""Read a finished slide back out of the browser as editable parts, for the editable PowerPoint export.

The slide is rendered at its final step, and the DOM is walked for two kinds of thing PowerPoint can hold natively:

- **text blocks** — the innermost block-level element whose content is only inline (a heading, a paragraph, a list
  item, a table cell, a card label), with its box on the 1600x900 stage and its text as styled runs;
- **pictures** — every `<img>` that is the slide's own content (not a full-bleed backdrop, not the HP stamp), with
  the rectangle the picture actually occupies after `object-fit`.

Then the same page is photographed a second time with exactly those things made invisible. That *background*
keeps everything PowerPoint cannot rebuild faithfully — gradients, cards, rules, SVG charts and diagrams, icons,
bullets and list numbers (they are `::before` content, and stay painted) — so the editable slide looks like the
designed one, with its words and pictures lifted out on top where a reviewer can change them.

Text is hidden with `-webkit-text-fill-color` rather than `color` on purpose: pseudo-elements are then reset to
their own colour, so a list's dash or number stays in the background instead of vanishing with the text.
"""
from __future__ import annotations

import base64
import binascii
from pathlib import Path

from pydantic import BaseModel, Field

from ..assemble import DeckInput, DeckSlide, assemble
from ..spec import SlideSpec
from . import render_check

# 2x: the background is a picture PowerPoint will scale to a projector; 1600x900 would look soft there.
BG_SCALE = 2

LAYOUT_JS = r"""
() => {
  const root = document.querySelector('.slide.on');
  const stage = document.getElementById('stage');
  if (!root || !stage) return {texts: [], images: []};
  const S = stage.getBoundingClientRect();
  const k = S.width ? 1600 / S.width : 1;
  const box = r => ({x: (r.left - S.left) * k, y: (r.top - S.top) * k, w: r.width * k, h: r.height * k});
  const visible = el => { for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.05) return false; }
    return true; };
  const INLINE = new Set(['inline', 'inline-block', 'contents']);
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'svg', 'SVG', 'IMG', 'VIDEO', 'CANVAS', 'INPUT', 'SELECT', 'TEXTAREA']);
  const chrome = el => el.closest('.stamp,.src');
  const hasText = el => (el.textContent || '').trim().length > 0;
  // Only inline children, none of them pictures or SVG: the whole element is one text box.
  const inlineOnly = el => [...el.querySelectorAll('*')].every(c =>
    INLINE.has(getComputedStyle(c).display) && !['IMG', 'svg', 'SVG', 'VIDEO', 'CANVAS', 'INPUT'].includes(c.tagName) && !(c instanceof SVGElement));
  const px = v => parseFloat(v) || 0;

  const texts = [], images = [];
  let n = 0;
  const runsOf = el => {
    const out = [];
    const walk = node => {
      for (const c of node.childNodes) {
        if (c.nodeType === 3) {
          const t = c.textContent.replace(/\s+/g, ' ');
          if (!t.trim() && !out.length) continue;
          const cs = getComputedStyle(c.parentElement);
          let text = t;
          if (cs.textTransform === 'uppercase') text = text.toUpperCase();
          else if (cs.textTransform === 'lowercase') text = text.toLowerCase();
          out.push({text, family: cs.fontFamily, size: px(cs.fontSize) * k, weight: +cs.fontWeight || 400,
                    italic: cs.fontStyle === 'italic', color: cs.color, underline: cs.textDecorationLine.includes('underline'),
                    spacing: px(cs.letterSpacing) * k});
        } else if (c.nodeType === 1) {
          if (c.tagName === 'BR') out.push({br: true});
          else if (getComputedStyle(c).display !== 'none') walk(c);
        }
      }
    };
    walk(el);
    // trim the outer whitespace the collapse left behind
    const first = out.find(r => !r.br), last = [...out].reverse().find(r => !r.br);
    if (first) first.text = first.text.replace(/^\s+/, '');
    if (last) last.text = last.text.replace(/\s+$/, '');
    return out.filter(r => r.br || r.text);
  };

  const visit = el => {
    if (SKIP.has(el.tagName) || el instanceof SVGElement || chrome(el) || !visible(el)) return;
    const cs = getComputedStyle(el);
    if (hasText(el) && !INLINE.has(cs.display) && inlineOnly(el)) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const b = box(r);
      // the content box: text wraps inside the padding, not the border
      const pl = px(cs.paddingLeft) + px(cs.borderLeftWidth), pr = px(cs.paddingRight) + px(cs.borderRightWidth);
      const pt = px(cs.paddingTop) + px(cs.borderTopWidth), pb = px(cs.paddingBottom) + px(cs.borderBottomWidth);
      const lh = cs.lineHeight === 'normal' ? px(cs.fontSize) * 1.2 : px(cs.lineHeight);
      const align = cs.textAlign === 'start' ? 'left' : cs.textAlign === 'end' ? 'right' : cs.textAlign;
      const runs = runsOf(el);
      if (!runs.length) return;
      // Where the words start: an inline swatch or icon before them (a chart legend's dot) is not text, and a
      // left-aligned box that began at the swatch would print the words on top of it.
      let left = b.x + pl * k;
      const right = b.x + b.w - pr * k;
      if (align === 'left') {
        const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let first = Infinity;
        for (let t = tw.nextNode(); t; t = tw.nextNode()) {
          if (!t.textContent.trim()) continue;
          const rg = document.createRange(); rg.selectNodeContents(t);
          for (const rr of rg.getClientRects()) first = Math.min(first, (rr.left - S.left) * k);
          break;
        }
        if (first > left + 1 && first < right) left = first;
      }
      el.setAttribute('data-xl', 't');
      texts.push({id: n++, x: left, y: b.y + pt * k, w: Math.max(4, right - left), h: Math.max(4, b.h - (pt + pb) * k),
                  align, line: lh * k, valign: (cs.display.includes('flex') && cs.alignItems === 'center') ? 'middle' : 'top', runs});
      return;
    }
    if (el.tagName === 'IMG') return;
    for (const c of el.children) {
      if (c.tagName === 'IMG') {
        if (chrome(c) || !visible(c) || !c.naturalWidth || c.closest('.bg-img') || c.classList.contains('bg-img')) continue;
        // Only a raster PowerPoint can place; an SVG picture stays painted in the background.
        if (!/^data:image\/(png|jpe?g|gif|webp)[;,]/.test(c.currentSrc || c.src)) continue;
        const r = c.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) continue;
        const ics = getComputedStyle(c);
        // A picture laid over most of the stage is a backdrop with a scrim on it: it stays in the background.
        if ((ics.position === 'absolute' || ics.position === 'fixed') && r.width * r.height > 0.5 * S.width * S.height) continue;
        let b = box(r), crop = null;
        const nw = c.naturalWidth, nh = c.naturalHeight, fit = ics.objectFit;
        if (fit === 'contain' || fit === 'scale-down') {
          const s = Math.min(b.w / nw, b.h / nh, fit === 'scale-down' ? 1 / k : Infinity);
          const w = nw * s, h = nh * s;
          b = {x: b.x + (b.w - w) / 2, y: b.y + (b.h - h) / 2, w, h};
        } else if (fit === 'cover') {
          const s = Math.max(b.w / nw, b.h / nh), w = nw * s, h = nh * s;
          crop = {l: (w - b.w) / 2 / w, r: (w - b.w) / 2 / w, t: (h - b.h) / 2 / h, b: (h - b.h) / 2 / h};
        }
        c.setAttribute('data-xl', 'i');
        images.push({id: n++, ...b, crop, src: c.currentSrc || c.src, alt: c.alt || ''});
      } else {
        visit(c);
      }
    }
  };
  visit(root);
  return {texts, images};
}
"""

HIDE_CSS = """
[data-xl="t"], [data-xl="t"] * { -webkit-text-fill-color: transparent !important; text-shadow: none !important;
                                 text-decoration-color: transparent !important; caret-color: transparent !important; }
[data-xl="t"]::before, [data-xl="t"]::after, [data-xl="t"] *::before, [data-xl="t"] *::after { -webkit-text-fill-color: initial !important; }
[data-xl="i"] { visibility: hidden !important; }
#hud, #controls { display: none !important; }  /* the deck's own navigation is not part of the slide */
"""


class Run(BaseModel):
    text: str = ""
    br: bool = False
    family: str = ""
    size: float = 16
    weight: int = 400
    italic: bool = False
    underline: bool = False
    color: str = ""
    spacing: float = 0


class TextBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    align: str = "left"
    valign: str = "top"
    line: float = 0
    runs: list[Run] = Field(default_factory=list)


class Picture(BaseModel):
    x: float
    y: float
    w: float
    h: float
    crop: dict[str, float] | None = None
    path: Path | None = None
    alt: str = ""


class SlideLayout(BaseModel):
    background: Path
    texts: list[TextBox] = Field(default_factory=list)
    pictures: list[Picture] = Field(default_factory=list)


def _save_data_url(src: str, dest: Path) -> Path | None:
    """The page inlines every asset as a data URL; write it back out as a file python-pptx can place."""
    if not src.startswith("data:") or "," not in src:
        return None
    head, data = src.split(",", 1)
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(
        head[5:].split(";")[0], "")
    if not ext or ";base64" not in head:
        return None  # SVG and anything exotic stay in the background picture
    try:
        dest = dest.with_suffix(ext)
        dest.write_bytes(base64.b64decode(data))
        return dest
    except (binascii.Error, ValueError):
        return None


async def extract_layout(spec: SlideSpec, slide_id: str, assets: dict[str, Path], out_dir: Path,
                         title: str = "Export", number: int = 1) -> SlideLayout:
    """Render `spec` at its final step and split it into a background picture, text boxes and pictures."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html = assemble(DeckInput(title=title, slides=[DeckSlide(id=slide_id, spec=spec)], assets=assets, storage_key="export"))
    path = out_dir / "layout.html"
    path.write_text(html, encoding="utf-8")
    bg = out_dir / "background.png"

    async def work(page) -> dict:
        steps = await page.evaluate("DECK.api.steps(0)")
        await page.evaluate(f"DECK.api.goto(0, {steps})")
        await page.wait_for_timeout(300)
        # The slide is rendered as a one-slide deck, so its stamp says 01; give it its place in the real deck.
        await page.evaluate("n => document.querySelectorAll('.slide.on .stamp span').forEach(e => e.textContent = n)",
                            f"{number:02d}")
        found = await page.evaluate(LAYOUT_JS)
        await page.add_style_tag(content=HIDE_CSS)
        await page.wait_for_timeout(60)
        await page.screenshot(path=str(bg))
        return found

    found = await render_check.on_page(path, work, scale=BG_SCALE)
    pictures = []
    for i, im in enumerate(found.get("images") or []):
        f = _save_data_url(im.get("src") or "", out_dir / f"pic{i:02d}")
        if f is not None:
            pictures.append(Picture(**{k: im[k] for k in ("x", "y", "w", "h")}, crop=im.get("crop"), path=f, alt=im.get("alt", "")))
    return SlideLayout(background=bg, texts=[TextBox.model_validate(t) for t in found.get("texts") or []],
                       pictures=pictures)
