"""Pixel math over the QA screenshots — no model, no network, no numpy (not a dependency here): Pillow only.

Two jobs:

* `contrast_findings` — the CSS-only contrast check in `render_check` gives up the moment a text element sits
  on a background image, which is exactly where slide contrast actually fails. Here the rendered PNG is
  sampled under the text's own line boxes instead, so a photo background is judged on what it really looks
  like and a scrim or overlay passes on its merits.
* `image_diff` — a structural difference between two screenshots, so QA iterations can be told apart:
  a repair that moved something real vs. one that returned the same slide with different bytes.

Both work off Pillow histograms (C speed); nothing iterates pixels in Python.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageChops
from pydantic import BaseModel

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- luminance helpers
def _rel_lum(v: int) -> float:
    c = v / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


_LUM = [_rel_lum(i) for i in range(256)]


def _luma(r: float, g: float, b: float) -> int:
    """8-bit luma, matching Pillow's RGB->"L" conversion (ITU-R 601) so foreground and background are
    measured on the same scale. The WCAG ratio is then taken on the grey, which is an approximation for
    saturated colours but monotone, cheap and consistent for both sides of the comparison."""
    return max(0, min(255, round(0.299 * r + 0.587 * g + 0.114 * b)))


def contrast_ratio(a: int, b: int) -> float:
    hi, lo = (a, b) if _LUM[a] >= _LUM[b] else (b, a)
    return (_LUM[hi] + 0.05) / (_LUM[lo] + 0.05)


# ---------------------------------------------------------------- contrast under text
_PAD = 3            # grow the glyph box so the background immediately around the text is sampled too
_GLYPH_BAND = 26    # luma this close to the text colour is glyph or antialiasing, not background
_MIN_BG_SHARE = 0.12  # less background than this in the crop: all text, nothing reliable to compare against
_MIN_PIXELS = 150   # smaller crops are too noisy to judge
# "worst" background, not the single worst pixel: one specular highlight in a photo must not fail a slide,
# but the darkest/brightest *region* under the text must still count. 0.88 lands past the bulk of a
# gradient or a scrim while ignoring the top ~12% of outliers.
_PERCENTILE = 0.88
# Deliberately at (and a touch below) the CSS check's thresholds: percentile sampling over real pixels is
# noisier than a flat CSS colour, and the gold examples are the calibration set — they must stay clean.
_MIN_RATIO_LARGE = 2.5   # font-size >= 24px
_MIN_RATIO_SMALL = 3.0
_MAX_REPORTED = 6


def _worst_background(crop: Image.Image, fg: int) -> int | None:
    """The least favourable background luma under a text box, or None when the crop cannot be judged."""
    hist = crop.convert("L").histogram()
    total = sum(hist)
    if total < _MIN_PIXELS:
        return None
    lo, hi = max(0, fg - _GLYPH_BAND), min(255, fg + _GLYPH_BAND)
    bg = [0 if lo <= i <= hi else n for i, n in enumerate(hist)]
    n = sum(bg)
    if n < total * _MIN_BG_SHARE:
        return None
    # Walk in from the end nearest the text colour: light text is defeated by the brightest background,
    # dark text by the darkest.
    want = n * (1.0 - _PERCENTILE)
    order = range(255, -1, -1) if fg >= 128 else range(256)
    acc = 0
    for i in order:
        acc += bg[i]
        if acc >= want:
            return i
    return None


def _open(png: Path | bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png) if isinstance(png, (bytes, bytearray)) else png)
    return img.convert("RGB")


def measure_contrast(png: Path | bytes, candidates: list[dict]) -> list[dict]:
    """Per-candidate measurements: {label, size, ratio, fg, bg}. Unjudgeable candidates are dropped.

    Each candidate is one line box of text that has no solid CSS background behind it:
    {x, y, w, h, color: [r,g,b], size, label}. Coordinates are viewport CSS pixels, which equal
    screenshot pixels (1600x900 viewport, device_scale_factor=1).
    """
    if not candidates:
        return []
    try:
        img = _open(png)
    except Exception as e:  # noqa: BLE001 - a screenshot we cannot read must never fail QA
        log.warning("contrast sampling skipped: %s", e)
        return []
    W, H = img.size
    out: list[dict] = []
    for c in candidates:
        try:
            x0 = max(0, int(c["x"]) - _PAD)
            y0 = max(0, int(c["y"]) - _PAD)
            x1 = min(W, int(c["x"] + c["w"]) + _PAD)
            y1 = min(H, int(c["y"] + c["h"]) + _PAD)
            if x1 - x0 < 6 or y1 - y0 < 6:
                continue
            fg = _luma(*c["color"][:3])
            bg = _worst_background(img.crop((x0, y0, x1, y1)), fg)
        except Exception:  # noqa: BLE001
            continue
        if bg is None:
            continue
        out.append({"label": c.get("label", "text"), "size": float(c.get("size") or 0),
                    "ratio": round(contrast_ratio(fg, bg), 2), "fg": fg, "bg": bg})
    return out


def contrast_findings(png: Path | bytes, candidates: list[dict]) -> list[dict]:
    """One aggregated `contrast-image` warning for text that is hard to read against real pixels."""
    bad = [m for m in measure_contrast(png, candidates)
           if m["ratio"] < (_MIN_RATIO_LARGE if m["size"] >= 24 else _MIN_RATIO_SMALL)]
    if not bad:
        return []
    bad.sort(key=lambda m: m["ratio"])
    worst = ", ".join(f"{m['label']} ({m['ratio']:.2f}:1)" for m in bad[:3])
    return [{"severity": "warn", "code": "contrast-image",
             "message": f"{len(bad[:_MAX_REPORTED])} text element(s) over imagery or a gradient are hard to read "
                        f"against the pixels actually behind them, e.g. {worst} — darken the scrim, add a panel "
                        f"behind the text, or move it off the busy part of the image"}]


# ---------------------------------------------------------------- screenshot diffs
_DIFF_EPS = 8       # per-pixel luma noise floor: font hinting and gradient banding live below this
_BLOCK_EPS = 4      # mean luma move that makes a whole block count as changed
_GRID = (40, 23)    # ~40x39 px blocks over a 1600x900 stage


class VisualDiff(BaseModel):
    """Deterministic difference between two screenshots. `changed_blocks` is the structural signal:
    it survives per-pixel noise and counts how much *area* actually moved."""
    shot: str = ""              # which screenshot was compared, e.g. "shot_final.png"
    identical: bool = False     # byte-identical files
    changed_ratio: float = 0.0  # 0..1 share of pixels whose luma moved by more than 8/255
    changed_blocks: float = 0.0  # 0..1 share of a 40x23 grid whose mean luma moved by more than 4/255
    mean_abs_diff: float = 0.0  # 0..255 mean absolute luma difference
    max_abs_diff: int = 0       # 0..255 largest single-pixel luma difference


def image_diff(a: Path, b: Path, *, shot: str = "") -> VisualDiff | None:
    """Structural diff between two PNGs. None when either is missing or unreadable."""
    try:
        if not (a.exists() and b.exists()):
            return None
        raw_a, raw_b = a.read_bytes(), b.read_bytes()
        name = shot or b.name
        if raw_a == raw_b:
            return VisualDiff(shot=name, identical=True)
        ia = _open(raw_a).convert("L")
        ib = _open(raw_b).convert("L")
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        d = ImageChops.difference(ia, ib)
        hist = d.histogram()
        total = sum(hist) or 1
        mean = sum(i * n for i, n in enumerate(hist)) / total
        changed = sum(n for i, n in enumerate(hist) if i > _DIFF_EPS) / total
        top = max((i for i, n in enumerate(hist) if n), default=0)
        cells = d.resize(_GRID, Image.BOX).histogram()  # box filter: each bin counts whole blocks
        blocks = sum(n for i, n in enumerate(cells) if i > _BLOCK_EPS) / (_GRID[0] * _GRID[1])
        return VisualDiff(shot=name, identical=False, changed_ratio=round(changed, 5),
                          changed_blocks=round(blocks, 5), mean_abs_diff=round(mean, 3), max_abs_diff=top)
    except Exception as e:  # noqa: BLE001 - a diff is a metric, never a reason to fail QA
        log.warning("visual diff failed: %s", e)
        return None
