"""Deck images: margin trimming (ingest and upload) and storing a user's own upload as a deck asset.

A diagram exported from PowerPoint or a screenshot tool usually arrives inside a wide frame of white or
transparent canvas. Laid out with `.figure img{max-width:80%}` that frame is still part of the picture, so
the content itself ends up a small island in the middle of the slide — the "stack image was too small"
complaint. Trimming it once, when the file enters the deck, fixes every later layout for free.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

UPLOAD_TYPES = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp", "gif": "png"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2400           # larger than any 1600x900 slide needs, even at 1.5x in a full-bleed layout
_TRIM_MIN = 0.04          # only trim when a margin is at least this share of the side: no nibbling at photos
_TRIM_PAD = 0.02          # breathing room left around the content
_TRIM_TOLERANCE = 12      # 0-255 per channel: JPEG noise in a "white" background is not content


class ImageRefused(ValueError):
    """The file is not an image a deck can carry. The message is safe to show the user."""


def _content_box(im: Image.Image) -> tuple[int, int, int, int] | None:
    """The bounding box of what is not background, or None when there is no uniform background."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        alpha = im.convert("RGBA").getchannel("A")
        if alpha.getextrema()[0] < 250:  # some transparency: the background is whatever is clear
            return alpha.point(lambda a: 255 if a > 8 else 0).getbbox()
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    bg = corners[0]
    if any(max(abs(a - b) for a, b in zip(c, bg)) > _TRIM_TOLERANCE for c in corners[1:]):
        return None  # a photo, or a gradient: no frame to take off
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    return diff.point(lambda v: 255 if v > _TRIM_TOLERANCE else 0).getbbox()


def trim_margins(im: Image.Image) -> Image.Image:
    """`im` without its uniform (white, flat-coloured or transparent) frame; `im` itself when there is none."""
    box = _content_box(im)
    if box is None:
        return im
    w, h = im.size
    left, top, right, bottom = box
    if max(left, w - right) < w * _TRIM_MIN and max(top, h - bottom) < h * _TRIM_MIN:
        return im
    pad_x, pad_y = int(w * _TRIM_PAD), int(h * _TRIM_PAD)
    return im.crop((max(0, left - pad_x), max(0, top - pad_y), min(w, right + pad_x), min(h, bottom + pad_y)))


def store_upload(blob: bytes, filename: str, assets_dir: Path) -> tuple[str, int, int]:
    """Validate, normalise and save a user's image as a deck asset. Returns (key, width, height).

    Re-encoded rather than copied: that drops EXIF (a phone photo carries its GPS position), applies the
    EXIF rotation so the picture is the right way up, and means the bytes inlined into every export are
    bytes Pillow wrote. SVG is refused outright — it can carry script, and it is inlined into the deck.
    """
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext == "svg":
        raise ImageRefused("SVG images can't be uploaded — export it as PNG first.")
    if ext not in UPLOAD_TYPES:
        raise ImageRefused("Please upload a PNG, JPEG, WebP or GIF image.")
    if not blob:
        raise ImageRefused("That file is empty.")
    if len(blob) > MAX_UPLOAD_BYTES:
        raise ImageRefused(f"Image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    try:
        with Image.open(io.BytesIO(blob)) as probe:
            probe.verify()  # cheap structural check before decoding a hostile file for real
        im = Image.open(io.BytesIO(blob))
        im.load()
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise ImageRefused("That file isn't a readable image.") from e
    im = ImageOps.exif_transpose(im)
    im = trim_margins(im)
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    key = "u_" + hashlib.sha1(blob).hexdigest()[:10]
    assets_dir.mkdir(parents=True, exist_ok=True)
    for old in assets_dir.glob(f"{key}.*"):  # the same upload twice is one asset
        old.unlink()
    if alpha:
        im.convert("RGBA").save(assets_dir / f"{key}.png", "PNG", optimize=True)
    else:
        im.convert("RGB").save(assets_dir / f"{key}.jpg", "JPEG", quality=90, optimize=True)
    return key, im.width, im.height
