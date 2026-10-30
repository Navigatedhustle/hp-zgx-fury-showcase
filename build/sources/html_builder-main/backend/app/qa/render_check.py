"""Render a slide spec in headless Chromium: JS errors, overflow, clipping, overlap, font size, contrast,
accessibility, screenshots.

The DOM, pixel-contrast and accessibility passes run at *every* step, not only the last one, and the
findings are unioned with the step recorded on each — a cinematic variant that is clean when it finishes can
still be broken halfway through. `qa/pixels.py` samples the screenshot under text that has no flat CSS
background, and diffs consecutive QA iterations; `qa/a11y.py` holds the curated accessibility rules.

Playwright runs on its own thread + event loop (Proactor on Windows), independent of the server loop.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import sys
import threading
from concurrent.futures import Future
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from .. import facts

from ..assemble import DeckInput, DeckSlide, assemble
from ..config import settings
from ..spec import SlideSpec
from .a11y import A11Y_CHECK_JS
from .pixels import VisualDiff, contrast_findings, image_diff

log = logging.getLogger(__name__)


class Finding(BaseModel):
    severity: str  # error | warn
    code: str
    message: str
    step: int | None = None  # which step the slide was on when this was seen (None when the slide has no steps)
    # A finding the repair loop is not allowed to give up on. An `error` fails QA but ships once the repair
    # budget is spent; a `fatal` one means the slide asserts something the source does not, which is never
    # shippable however well it is laid out. Only the fact ledger raises it.
    fatal: bool = False


class RenderReport(BaseModel):
    steps: int = 0
    findings: list[Finding] = Field(default_factory=list)
    shots: list[str] = Field(default_factory=list)  # file names: shot_0.png, shot_final.png
    text: str = ""
    diff: VisualDiff | None = None  # vs. the previous QA iteration, when one was handed in
    # Charts as H.chart built them (runtime/lib.js `record`), read at the final step, for qa/charts.py.
    charts: list[dict] = Field(default_factory=list)
    unverified_charts: int = 0      # chart-like SVGs H.chart did not build: their data cannot be checked

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]


CHART_JS = r"""
() => {
  const root = document.querySelector('.slide.on');
  if (!root) return {charts: [], unverified: 0};
  const charts = [...root.querySelectorAll('[data-chart]')].filter(c => c.__chart).map(c => {
    const d = c.__chart;
    const want = d.series.reduce((n, se) => n + se.values.filter(v => v && isFinite(v)).length, 0);
    let visible = want;
    if (/bars|groupedBars|stackedBars/i.test(d.type) && d.type !== 'hbars')
      visible = [...c.querySelectorAll('rect.bar')].filter(r => +r.getAttribute('height') > 0.5).length;
    else if (d.type === 'hbars')
      visible = [...c.querySelectorAll('.fillbar')].filter(b => parseFloat(b.style.width) > 0).length;
    else if (d.type === 'line')
      visible = [...c.querySelectorAll('path.line')].every(p => (parseFloat(p.style.strokeDashoffset) || 0) < 1) ? want : 0;
    return {...d, hidden: Math.max(0, want - visible)};
  });
  // Chart-shaped SVGs H.chart did not build (hand-rolled bars and lines): present, but nothing to check them against.
  const unverified = [...root.querySelectorAll('svg')].filter(s => !s.closest('[data-chart]') && !s.closest('[data-icon]')
    && s.querySelectorAll('rect, path, polyline, circle').length >= 4 && s.getBoundingClientRect().width > 160).length;
  return {charts, unverified};
}
"""

DOM_CHECK_JS = r"""
(opts) => {
  const FINAL = !opts || opts.final !== false;  // codes that only make sense once the slide has finished
  const root = document.querySelector('.slide.on');
  const out = [];
  const contrast = [];
  if (!root) return {findings:[{severity:'error', code:'no-slide', message:'slide did not render'}], text:'', contrast};
  const W = 1600, H = 900;
  const opacityOf = el => { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return 0; o *= +cs.opacity; } return o; };
  const label = el => { let s = el.tagName.toLowerCase(); if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.'); const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40); return t ? `${s} "${t}"` : s; };
  const chrome = el => el.closest('.stamp,.src');
  const all = [...root.querySelectorAll('*')].filter(el => !chrome(el));
  const hasOwnText = el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const textEls = all.filter(el => hasOwnText(el) && !(el instanceof SVGElement) && opacityOf(el) > 0.05);

  if (FINAL && !textEls.length && !root.querySelector('img,svg')) out.push({severity:'error', code:'empty', message:'slide has no visible content at the final step'});

  // 1. outside the stage
  const seen = new Set();
  for (const el of all) {
    if (el.classList.contains('bg-img') || el.classList.contains('bg-shade') || opacityOf(el) <= 0.05) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (!(hasOwnText(el) || el.tagName === 'IMG' || el.classList.contains('card'))) continue;
    if (r.right > W + 3 || r.bottom > H + 3 || r.left < -3 || r.top < -3) {
      const key = label(el); if (seen.has(key)) continue; seen.add(key);
      out.push({severity:'error', code:'overflow', message:`${key} extends outside the 1600x900 stage (box ${Math.round(r.left)},${Math.round(r.top)} → ${Math.round(r.right)},${Math.round(r.bottom)})`});
    }
  }
  // 2. clipped content inside containers
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (opacityOf(el) <= 0.05) continue;
    const clips = /(hidden|clip|auto|scroll)/.test(cs.overflow + cs.overflowX + cs.overflowY);
    if (!clips || el.tagName === 'svg' || el.tagName === 'INPUT') continue;
    if (!(el.innerText || '').trim()) continue;
    if (el.scrollHeight > el.clientHeight + 6 || el.scrollWidth > el.clientWidth + 6) {
      out.push({severity:'error', code:'clipped', message:`content clipped inside ${label(el)} (needs ${el.scrollWidth}x${el.scrollHeight}, has ${el.clientWidth}x${el.clientHeight})`});
    }
  }
  // 2b. text escaping its box (fixed-height cards etc.)
  for (const el of textEls) {
    const p = el.parentElement; if (!p) continue;
    if (getComputedStyle(el).display.startsWith('inline')) continue;
    const r = el.getBoundingClientRect(), pr = p.getBoundingClientRect();
    if (r.bottom > pr.bottom + 8 && getComputedStyle(p).overflow === 'visible' && pr.height > 0 && p !== root) {
      if (r.height > 0 && (r.bottom - pr.bottom) > 8 && !['inline','contents'].includes(getComputedStyle(p).display))
        out.push({severity:'warn', code:'spill', message:`text ${label(el)} spills below its container ${label(p)} by ${Math.round(r.bottom - pr.bottom)}px`});
    }
  }
  // 3. overlapping text
  const boxes = textEls.map(el => ({el, r: el.getBoundingClientRect()})).filter(b => b.r.width > 4 && b.r.height > 4);
  let overlaps = 0;
  for (let i = 0; i < boxes.length && overlaps < 6; i++) for (let j = i + 1; j < boxes.length && overlaps < 6; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const x = Math.max(0, Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left));
    const y = Math.max(0, Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top));
    const inter = x * y, small = Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
    if (small > 0 && inter / small > 0.3) { overlaps++; out.push({severity:'error', code:'overlap', message:`${label(a.el)} overlaps ${label(b.el)}`}); }
  }
  // 4. stamp collision
  const stamp = root.querySelector('.stamp');
  if (stamp) { const s = stamp.getBoundingClientRect();
    for (const b of boxes) { const x = Math.min(b.r.right, s.right) - Math.max(b.r.left, s.left), y = Math.min(b.r.bottom, s.bottom) - Math.max(b.r.top, s.top);
      if (x > 4 && y > 4) { out.push({severity:'warn', code:'stamp', message:`${label(b.el)} collides with the HP stamp in the bottom-right corner`}); break; } } }
  // 5. font size
  const tiny = textEls.filter(el => { const cs = getComputedStyle(el), fs = parseFloat(cs.fontSize); return fs < 10.5 || (fs < 12.5 && cs.textTransform !== 'uppercase'); });
  if (tiny.length) out.push({severity:'warn', code:'font-size', message:`${tiny.length} text element(s) too small (body < 13px, labels < 11px), e.g. ${label(tiny[0])} at ${getComputedStyle(tiny[0]).fontSize}`});
  // 6. contrast
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r:p[0], g:p[1], b:p[2], a:p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  // The line boxes of an element's own text, which is what actually has to be readable.
  const lineRects = el => { const rs = [];
    for (const n of el.childNodes) { if (n.nodeType !== 3 || !n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (r.width >= 14 && r.height >= 7) rs.push(r); }
    return rs; };
  // A full-bleed photo or scrim is a *sibling* laid over the slide, not an ancestor background, so walking
  // up the tree finds the slide's own flat colour and cheerfully measures the text against the wrong thing.
  // Its presence alone sends text without an opaque panel to the pixels (the hit test below misses layers
  // marked pointer-events:none, which a decorative overlay often is).
  const bleed = all.some(el => {
    const cs = getComputedStyle(el);
    if (cs.position !== 'absolute' && cs.position !== 'fixed') return false;
    if (!(['IMG', 'VIDEO', 'CANVAS'].includes(el.tagName) || (cs.backgroundImage && cs.backgroundImage !== 'none'))) return false;
    if (opacityOf(el) <= 0.05) return false;
    const r = el.getBoundingClientRect();
    return r.width * r.height > 0.5 * W * H;
  });
  // What is really behind a piece of text, hit-tested through the rendered stack rather than guessed from
  // the tree: a progress-bar fill, a photo or a scrim is a sibling painted underneath, and only the stack
  // knows it is there. PIX means "no flat colour — go and read the screenshot".
  const PIX = 'pixels';
  const backdrop = (el, r) => {
    const px = Math.min(W - 1, Math.max(1, r.left + r.width / 2));
    const py = Math.min(H - 1, Math.max(1, r.top + r.height / 2));
    const stack = document.elementsFromPoint(px, py);
    const i = stack.indexOf(el);
    // el's own background paints behind its own text, so it starts the chain; everything the stack puts
    // above it is in front of the text and irrelevant; its descendants are not behind it either.
    for (const e of [el].concat(i >= 0 ? stack.slice(i + 1) : stack)) {
      if (e !== el && el.contains(e)) continue;
      const cs = getComputedStyle(e);
      if (cs.visibility === 'hidden') continue;
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return PIX;
      if (['IMG', 'VIDEO', 'CANVAS'].includes(e.tagName) || e instanceof SVGElement) return PIX;
      const c = parse(cs.backgroundColor);
      if (!c || !c.a) continue;
      if (c.a > 0.95 && opacityOf(e) > 0.95) return c;  // opaque: this is the backdrop
      return PIX;                                       // translucent: the real colour is a blend
    }
    return null;
  };
  const CAP = 40;
  let lowContrast = 0, lowExample = '';
  for (const el of textEls) {
    const ecs = getComputedStyle(el);
    const fg = parse(ecs.color); if (!fg) continue;
    const size = parseFloat(ecs.fontSize);
    const rects = lineRects(el);
    let bg = null, complex = false, panel = false;
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') { complex = true; break; }
      const c = parse(cs.backgroundColor); if (c && c.a > 0.5) { bg = c; panel = e !== root && root.contains(e); break; }
      if (e === root) break; }
    if (bleed && !panel) complex = true;
    const hit = rects.length ? backdrop(el, rects[0]) : null;
    if (hit === PIX) complex = true;              // the stack beats the tree when the two disagree
    else if (hit) { bg = hit; complex = false; }
    if (complex || !bg) {
      // No flat colour to compare against — hand the text's own line boxes to the pixel sampler, which
      // reads what is actually behind them in the screenshot (photo, gradient, scrim, video poster).
      // Mid-animation opacity would make the rendered colour a blend, so only settled text is offered.
      if (contrast.length >= CAP || fg.a < 0.9 || opacityOf(el) < 0.9) continue;
      for (const r of rects.slice(0, 3)) {
        if (contrast.length >= CAP) break;
        contrast.push({x:r.left, y:r.top, w:r.width, h:r.height, color:[fg.r, fg.g, fg.b], size, label:label(el)});
      }
      continue;
    }
    const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    if (ratio < (size >= 24 ? 2.6 : 3.2)) { lowContrast++; if (!lowExample) lowExample = `${label(el)} (${ratio.toFixed(2)}:1)`; }
  }
  if (lowContrast) out.push({severity:'warn', code:'contrast', message:`${lowContrast} low-contrast text element(s), e.g. ${lowExample}`});
  // 7. broken images
  root.querySelectorAll('img').forEach(img => { if (!img.complete || img.naturalWidth === 0) out.push({severity:'error', code:'image', message:`image failed to load: ${img.getAttribute('alt') || img.src.slice(0, 60)}`}); });
  // 7b. image scale. A slide whose subject is a picture (a stack diagram, a product) and shows it as a thumbnail
  // wastes the one thing it is about; a picture stretched past its pixels goes soft on a projector.
  if (FINAL) {
    const pics = [...root.querySelectorAll('img')].filter(img => !chrome(img) && !img.closest('.bg-img') && img.naturalWidth > 0 && opacityOf(img) > 0.05);
    const words0 = (root.innerText || '').split(/\s+/).filter(Boolean).length;
    for (const img of pics) {
      const r = img.getBoundingClientRect(), share = (r.width * r.height) / (W * H);
      const name = img.getAttribute('alt') || img.getAttribute('src').slice(0, 40);
      if (pics.length === 1 && words0 < 90 && share < 0.09 && img.naturalWidth >= r.width * 1.3)
        out.push({severity:'warn', code:'image-small', message:`image "${name}" is the slide's subject but fills only ${Math.round(share * 100)}% of the stage (${Math.round(r.width)}x${Math.round(r.height)}px); give it more room`});
      if (r.width > 320 && r.width > img.naturalWidth * 1.6)
        out.push({severity:'warn', code:'image-blurry', message:`image "${name}" is shown at ${Math.round(r.width)}px wide but has only ${img.naturalWidth}px — it will look soft`});
    }
  }
  // 7c. precise layout (final step). A slide can pass every "does it fit" check and still look careless: a card
  // 3px lower than its neighbours, gaps of 22/22/37px, a paragraph in the margin. Offsets under ~1.5px are
  // sub-pixel rounding; offsets over 6px are a design decision. What lies between is a mistake.
  if (FINAL) {
    // the slide's own padding: 76/64 normally, 0 on a full-bleed slide (which then has no margin to police)
    const pad = v => { const n = parseFloat(v); return isNaN(n) ? null : n; };
    const PX = pad(getComputedStyle(root).paddingLeft) ?? 76, PY = pad(getComputedStyle(root).paddingTop) ?? 64;
    const flowKids = el => [...el.children].filter(c => {
      const cs = getComputedStyle(c);
      if (cs.position === 'absolute' || cs.position === 'fixed' || cs.display === 'none' || opacityOf(c) <= 0.05) return false;
      if (chrome(c) || c.tagName === 'SCRIPT' || c.tagName === 'STYLE') return false;
      const r = c.getBoundingClientRect(); return r.width > 40 && r.height > 16;
    });
    const edge = (c, align) => { const r = c.getBoundingClientRect();
      return align === 'center' ? (r.top + r.bottom) / 2 : /end/.test(align) ? r.bottom : r.top; };
    let mis = 0, misEx = '', gaps = 0, gapEx = '', ragged = 0, raggedEx = '';
    for (const p of [root, ...root.querySelectorAll('*')]) {
      const cs = getComputedStyle(p);
      const isRow = (cs.display.includes('flex') && cs.flexDirection.startsWith('row')) || cs.display.includes('grid');
      if (!isRow) continue;
      const kids = flowKids(p);
      if (kids.length < 2) continue;
      // group the children into visual rows by their vertical overlap
      const rows = [];
      for (const k of kids) { const r = k.getBoundingClientRect();
        const row = rows.find(g => { const q = g[0].getBoundingClientRect(); return r.top < q.bottom - 8 && r.bottom > q.top + 8; });
        if (row) row.push(k); else rows.push([k]); }
      for (const row of rows) {
        if (row.length < 2) continue;
        const align = p => { const s = getComputedStyle(p).alignSelf; return s && s !== 'auto' ? s : cs.alignItems; };
        // Like with like: cards and columns of about one width. An icon beside its text is offset on purpose.
        const ws = row.map(k => k.getBoundingClientRect().width);
        const peers = Math.min.apply(null, ws) >= 0.8 * Math.max.apply(null, ws);
        if (peers && !row.some(k => align(k) === 'baseline')) {
          const e = row.map(k => edge(k, align(k)));
          const off = Math.max.apply(null, e) - Math.min.apply(null, e);
          if (off > 1.5 && off <= 6) { mis++; if (!misEx) misEx = `${label(row[0])} and its ${row.length - 1} neighbour(s) are ${off.toFixed(1)}px out of line`; }
        }
        const cards = row.filter(k => k.classList.contains('card'));
        if (cards.length >= 2) {
          const hs = cards.map(k => k.getBoundingClientRect().height);
          const d = Math.max.apply(null, hs) - Math.min.apply(null, hs);
          if (d > 12) { ragged++; if (!raggedEx) raggedEx = `${cards.length} cards in one row range from ${Math.round(Math.min.apply(null, hs))} to ${Math.round(Math.max.apply(null, hs))}px tall`; }
        }
        if (row.length >= 3 && cs.display.includes('flex')) {
          const rs = row.map(k => k.getBoundingClientRect()).sort((a, b) => a.left - b.left);
          const g = rs.slice(1).map((r, i) => r.left - rs[i].right);
          const spread = Math.max.apply(null, g) - Math.min.apply(null, g);
          if (spread > 8) { gaps++; if (!gapEx) gapEx = `gaps of ${g.map(x => Math.round(x)).join('/')}px between ${label(row[0])} and its siblings`; }
        }
      }
    }
    if (mis) out.push({severity:'error', code:'misaligned', message:`${mis} row(s) almost but not quite aligned: ${misEx} — align them exactly (same align-items, no stray margin)`});
    if (gaps) out.push({severity:'warn', code:'uneven-gap', message:`uneven spacing: ${gapEx} — use one gap for the row`});
    if (ragged) out.push({severity:'warn', code:'ragged', message:`${raggedEx} — let the row stretch them to one height`});
    // the content box: 1448x772 inside the slide's padding. Bleed layers and the runtime's chrome are exempt.
    const L = PX, T = PY, R = W - PX, B = H - PY;
    // Only content in the normal flow: something positioned (a corner logo, a bleed photo) was put there on purpose.
    const placed = el => { for (let e = el; e && e !== root; e = e.parentElement) {
      const p = getComputedStyle(e).position; if (p === 'absolute' || p === 'fixed') return true; } return false; };
    const inMargin = all.filter(el => (hasOwnText(el) || el.tagName === 'IMG' || el.classList.contains('card'))
      && !el.closest('.bg-img,.bg-shade') && opacityOf(el) > 0.05 && !placed(el))
      .filter(el => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false;
        const over = Math.max(L - r.left, r.right - R, T - r.top, r.bottom - B);
        return over > 4 && r.right <= W + 3 && r.bottom <= H + 3 && r.left >= -3 && r.top >= -3; });  // off-stage is `overflow`
    if (inMargin.length) out.push({severity:'error', code:'margin', message:`${inMargin.length} element(s) sit in the slide margin, outside the 1448x772 content area, e.g. ${label(inMargin[0])}`});
    const title = root.querySelector('.title');
    if (title && getComputedStyle(title).textAlign !== 'center') {
      const d = title.getBoundingClientRect().left - L;
      if (Math.abs(d) > 1.5 && Math.abs(d) <= 12) out.push({severity:'warn', code:'title-drift', message:`the title starts ${d.toFixed(1)}px ${d > 0 ? 'right' : 'left'} of the content edge — the slides' titles should line up`});
    }
  }
  // 8. word count
  const words = (root.innerText || '').split(/\s+/).filter(Boolean).length;
  if (FINAL && words > 170) out.push({severity:'warn', code:'density', message:`${words} words on the slide — too dense; move detail to notes`});
  return {findings: out, text: root.innerText || '', contrast};
}
"""

# Findings that are one summary of the whole slide rather than one defect: keep the first step that reports
# them instead of repeating a slightly different count for every step.
_AGGREGATE_CODES = {"font-size", "contrast", "contrast-image", "density"}


def _is_aggregate(code: str) -> bool:
    return code in _AGGREGATE_CODES or code.startswith("a11y-")

def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def ledger_findings(slide_facts: Sequence[facts.Fact], rendered_text: str, notes_text: str = "") -> list[Finding]:
    """Check the finished slide against the source slide's fact ledger.

    Four outcomes, and they are deliberately not one severity:

      changed   a value moved: the source says 4.2M where the slide says 5.1M, in the same claim. Code can
                be *certain* about this, so it is `fatal` — no amount of layout makes it shippable, and the
                repair loop may not shrug it off.
      key       a fact the plan called the slide's message is absent, or reached only the speaker notes. An
                error, so it drives a repair, but it ships with a warning if repair cannot place it.
      missing   a supporting fact did not fit. A warning: a shortfall, not a lie.
      invented  a figure with a unit that no source fact accounts for. Only a **warning**, and deliberately
                so: a good slide legitimately derives figures the source never wrote down ("90s to 30s" is
                honestly "3x faster"), and code cannot tell a derivation from a fabrication. It is handed to
                the critic, which can reason about whether the arithmetic follows from the source.

    Every message names the figure, because "3 numbers are missing" is not something a repair pass or a
    reader can act on.
    """
    lg = facts.ledger(slide_facts, rendered_text, notes_text)
    out: list[Finding] = []
    if lg.changed:
        out.append(Finding(severity="error", fatal=True, code="fidelity-changed",
                           message="the slide changes a value from the source: "
                                   + "; ".join(c.detail for c in lg.changed[:4])))
    if lg.invented:
        out.append(Finding(severity="warn", code="fidelity-invented",
                           message=f"the slide states {_plural(len(lg.invented), 'figure')} that appear nowhere in the "
                                   f"source: {', '.join(lg.invented[:6])} — each must follow from the source by "
                                   f"arithmetic the audience could check, or come out"))
    gone = [c for c in lg.checks if c.status == "missing" and c.fact.visible_required] + lg.hidden
    if gone:
        where = ", ".join(f"{c.fact.raw}{' (in the notes only)' if c.status == 'notes' else ''}" for c in gone[:6])
        out.append(Finding(severity="error", code="fidelity-key",
                           message=f"{_plural(len(gone), 'key fact')} the plan called this slide's message "
                                   f"{'is' if len(gone) == 1 else 'are'} not on it: {where}"))
    minor = [c for c in lg.missing if not c.fact.visible_required]
    if minor:
        out.append(Finding(severity="warn", code="fidelity",
                           message=f"{_plural(len(minor), 'supporting fact')} reached neither the slide nor its notes: "
                                   f"{', '.join(c.fact.raw for c in minor[:8])}"))
    return out


_LAUNCH_ARGS = ["--disable-gpu", "--font-render-hinting=none"]
# Tried in order. Playwright's own Chromium first (what the checks were tuned on); then the Edge every Windows
# machine already has, and Chrome — so a laptop whose network blocked the Chromium download still renders.
_BROWSER_CHANNELS = (None, "msedge", "chrome")


async def _launch(pw):
    """Launch the first browser that starts. Raises the first failure if none does."""
    first: Exception | None = None
    for channel in _BROWSER_CHANNELS:
        try:
            browser = await pw.chromium.launch(args=_LAUNCH_ARGS, **({"channel": channel} if channel else {}))
        except Exception as e:  # noqa: BLE001 - not installed, blocked by AV, ...
            first = first or e
            continue
        if channel:
            log.warning("Playwright's Chromium is unavailable (%s) — rendering with the installed %s instead",
                        str(first).splitlines()[0] if first else "", channel)
        return browser
    raise first  # type: ignore[misc]

# Below this share of the stage, a slide that claims steps did not really move between step 0 and the end.
# md5 catches the byte-identical case; this catches "a caret blinked" and "one label changed opacity by 2%".
_STEPS_MIN_CHANGE = 0.004


class _Renderer:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._browser = None
        self._pw = None
        self._ready = threading.Event()
        self._sem: asyncio.Semaphore | None = None
        self._start_error: BaseException | None = None
        self._lock = threading.Lock()  # guards _thread/_ready across callers
        self._relaunching: asyncio.Lock | None = None  # renderer-loop only

    def _run(self) -> None:
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._start())
        except BaseException as e:  # noqa: BLE001 - Chromium missing, sandbox/AV block, ...
            # The thread is about to die. Record why and wake the waiters *now*: leaving _ready unset
            # made every later call wait the full 60s before failing, once per version.
            log.exception("QA renderer failed to start")
            self._start_error = e
            self._loop = None
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        loop.run_forever()

    async def _start(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await _launch(self._pw)
        self._sem = asyncio.Semaphore(max(1, settings().qa_concurrency))
        self._relaunching = asyncio.Lock()

    def ensure(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._ready.clear()
                self._start_error = None
                self._thread = threading.Thread(target=self._run, name="qa-renderer", daemon=True)
                self._thread.start()
            thread = self._thread
        ok = self._ready.wait(60)
        err = self._start_error
        if ok and err is None:
            return
        with self._lock:
            if self._thread is thread:
                self._thread = None  # let the next call try again instead of blocking on a dead thread
        raise RuntimeError(f"Chromium failed to start for QA rendering: {err}" if err else
                           "Chromium failed to start for QA rendering (timed out)")

    def submit(self, coro) -> Future:
        self.ensure()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _relaunch(self) -> None:
        """Replace a browser that died mid-run. Without this every later version fails QA with code=render."""
        async with self._relaunching:
            if self._browser is not None and self._browser.is_connected():
                return
            log.warning("QA Chromium is gone — relaunching")
            old, self._browser = self._browser, None
            if old is not None:
                try:
                    await old.close()
                except Exception:  # noqa: BLE001
                    pass
            self._browser = await _launch(self._pw)

    async def _context(self, **kwargs):
        if self._browser is None or not self._browser.is_connected():
            await self._relaunch()
        try:
            return await self._browser.new_context(**kwargs)
        except Exception:  # noqa: BLE001 - the browser can die between the check and the call
            await self._relaunch()
            return await self._browser.new_context(**kwargs)

    async def _step_findings(self, page, out_dir: Path, rep: RenderReport) -> list[tuple[int, list[dict]]]:
        """Walk every step, running the DOM, pixel-contrast and accessibility checks at each one.

        Variant A is cinematic: it can be flawless at the final step and overlap, clip or overflow halfway
        through. Each pass is a single page.evaluate (~20ms) against the settle time that was already being
        spent stepping through, so the cost is noise. `rep.text` and the screenshots keep coming from the
        final step — fidelity is about the finished slide.
        """
        s0, sf = out_dir / "shot_0.png", out_dir / "shot_final.png"
        await page.evaluate("DECK.api.goto(0, 0)")
        await page.wait_for_timeout(120)
        await page.screenshot(path=str(s0))
        raw: list[tuple[int, list[dict]]] = []
        for st in range(rep.steps + 1):
            final = st == rep.steps
            if st or final:  # a slide with no steps still gets the old goto + long settle before its check
                await page.evaluate(f"DECK.api.goto(0, {st})")
            await page.wait_for_timeout(250 if final else (60 if st else 0))
            dom = await page.evaluate(DOM_CHECK_JS, {"final": final})
            shot: bytes | None = None
            if final:
                rep.text = dom.get("text", "")
                ch = await page.evaluate(CHART_JS)
                rep.charts, rep.unverified_charts = list(ch.get("charts") or []), int(ch.get("unverified") or 0)
                await page.screenshot(path=str(sf))
                shot = sf.read_bytes()
            found = list(dom.get("findings") or [])
            cands = dom.get("contrast") or []
            if cands:
                if shot is None:
                    shot = s0.read_bytes() if st == 0 else await page.screenshot()
                found += contrast_findings(shot, cands)
            found += list((await page.evaluate(A11Y_CHECK_JS)).get("findings") or [])
            raw.append((st, found))
        return raw

    def _collect(self, raw: list[tuple[int, list[dict]]], rep: RenderReport) -> None:
        """Union the per-step findings, deduplicated, with the step recorded on each one."""
        seen: set[tuple[str, str]] = set()
        seen_codes: set[str] = set()
        for st, found in raw:
            for f in found:
                code, msg = f.get("code", ""), f.get("message", "")
                if _is_aggregate(code):
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                if (code, msg) in seen:
                    continue
                seen.add((code, msg))
                if rep.steps and st != rep.steps:
                    msg = f"{msg} — seen at step {st} of {rep.steps}"
                rep.findings.append(Finding(severity=f.get("severity", "warn"), code=code, message=msg,
                                            step=st if rep.steps else None))

    async def check(self, html_path: Path, out_dir: Path, prev_dir: Path | None = None) -> RenderReport:
        async with self._sem:
            ctx = await self._context(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            page = await ctx.new_page()
            logs: list[Finding] = []
            page.on("pageerror", lambda e: logs.append(Finding(severity="error", code="js", message=f"uncaught: {e}")))
            page.on("console", lambda m: m.type == "error" and not m.text.startswith("[slide ") and logs.append(Finding(severity="error", code="js", message=m.text[:300])))
            page.on("request", lambda r: (r.url.startswith("http") and logs.append(
                Finding(severity="error", code="external", message=f"external request: {r.url[:120]}"))))
            rep = RenderReport()
            try:
                await page.goto(html_path.resolve().as_uri() + "?instant", wait_until="load", timeout=30000)
                await page.wait_for_function("window.DECK && DECK.ready", timeout=15000)
                rep.steps = await page.evaluate("DECK.api.steps(0)")
                s0, sf = out_dir / "shot_0.png", out_dir / "shot_final.png"
                raw = await self._step_findings(page, out_dir, rep)
                self._collect(raw, rep)
                rep.shots = ["shot_0.png", "shot_final.png"] if rep.steps else ["shot_final.png"]
                if rep.steps:
                    same = hashlib.md5(s0.read_bytes()).digest() == hashlib.md5(sf.read_bytes()).digest()
                    step_diff = None if same else image_diff(s0, sf, shot="shot_0→shot_final")
                    if same or (step_diff is not None and step_diff.changed_blocks < _STEPS_MIN_CHANGE):
                        how = "identical" if same else f"all but identical ({step_diff.changed_blocks:.1%} of the stage moved)"
                        rep.findings.append(Finding(severity="warn", code="steps", step=rep.steps,
                                                    message=f"meta.steps={rep.steps} but the slide looks {how} at step 0 and the final step"))
                if not rep.steps:
                    s0.unlink(missing_ok=True)
                if prev_dir is not None:
                    rep.diff = image_diff(prev_dir / "shot_final.png", sf, shot="shot_final.png")
                for e in await page.evaluate("DECK.api.errors()"):
                    logs.append(Finding(severity="error", code="js", message=f"{e.get('phase')}: {str(e.get('message'))[:300]}"))
            except Exception as e:  # noqa: BLE001
                rep.findings.append(Finding(severity="error", code="render", message=f"render failed: {e}"[:400]))
            finally:
                await ctx.close()
            seen = set()
            for f in logs:
                if f.message not in seen:
                    seen.add(f.message)
                    rep.findings.insert(0, f)
            return rep

    async def on_page(self, html_path: Path, fn, *, scale: int = 1):
        """Open a rendered deck page and hand it to `fn(page)` — for work that needs the live DOM (the editable
        PowerPoint export reads the finished slide back out of it). Shares the semaphore with QA."""
        async with self._sem:
            ctx = await self._context(viewport={"width": 1600, "height": 900}, device_scale_factor=scale)
            page = await ctx.new_page()
            try:
                await page.goto(html_path.resolve().as_uri() + "?instant", wait_until="load", timeout=30000)
                await page.wait_for_function("window.DECK && DECK.ready", timeout=15000)
                return await fn(page)
            finally:
                await ctx.close()

    async def pdf(self, html_path: Path, out: Path) -> None:
        async with self._sem:
            ctx = await self._context(viewport={"width": 1600, "height": 900})
            page = await ctx.new_page()
            try:
                await page.goto(html_path.resolve().as_uri() + "?instant", wait_until="load", timeout=60000)
                await page.wait_for_function("window.DECK && DECK.ready", timeout=30000)
                await page.evaluate("DECK.api.preparePrint()")
                await page.emulate_media(media="print")
                await page.wait_for_timeout(400)
                await page.pdf(path=str(out), width="1600px", height="900px", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            finally:
                await ctx.close()


_renderer = _Renderer()


async def check_spec(spec: SlideSpec, slide_id: str, assets: dict[str, Path], out_dir: Path, title: str = "QA",
                     prev_dir: Path | None = None) -> RenderReport:
    """Render and check one slide. `prev_dir` is the previous QA iteration's directory: hand it in and
    `report.diff` comes back as a `VisualDiff` of that iteration's shot_final.png against this one's, so a
    repair that changed nothing is visible without a model."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html = assemble(DeckInput(title=title, slides=[DeckSlide(id=slide_id, spec=spec)], assets=assets, storage_key="qa"))
    path = out_dir / "qa.html"
    path.write_text(html, encoding="utf-8")
    await asyncio.to_thread(_renderer.ensure)
    fut = _renderer.submit(_renderer.check(path, out_dir, prev_dir))
    return await asyncio.wrap_future(fut)


async def on_page(html_path: Path, fn, *, scale: int = 1):
    """Run `fn(page)` against a rendered deck page on the shared browser. Returns what `fn` returns."""
    await asyncio.to_thread(_renderer.ensure)
    fut = _renderer.submit(_renderer.on_page(html_path, fn, scale=scale))
    return await asyncio.wrap_future(fut)


async def export_pdf(html_path: Path, out: Path) -> Path:
    await asyncio.to_thread(_renderer.ensure)
    fut = _renderer.submit(_renderer.pdf(html_path, out))
    await asyncio.wrap_future(fut)
    return out
