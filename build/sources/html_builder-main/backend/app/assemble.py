"""Deterministic deck assembly: runtime + fonts + assets + slide specs -> one self-contained HTML."""
from __future__ import annotations

import base64
import html as htmllib
import json
import mimetypes
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import BRAND_DIR, RUNTIME_DIR
from .spec import SlideSpec
from showcase_app.security import DOCUMENT_CSP

_FONT_FILES = [("Archivo", 400), ("Archivo", 600), ("Archivo", 700), ("Archivo", 800), ("PlexMono", 400), ("PlexMono", 700)]
_ASSET_REF = re.compile(r"""asset:([\w.-]+)|H\.asset\(\s*['"]([\w.-]+)['"]\s*\)""")


@dataclass
class DeckSlide:
    id: str
    spec: SlideSpec


@dataclass
class DeckInput:
    title: str
    slides: list[DeckSlide]
    assets: dict[str, Path] = field(default_factory=dict)  # key -> file on disk
    storage_key: str = "hpdeck"


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


@lru_cache
def _runtime_css() -> str:
    faces = []
    for fam, w in _FONT_FILES:
        brand = BRAND_DIR / "fonts" / f"{fam}-{w}.woff2"
        p = brand if brand.exists() else RUNTIME_DIR / "fonts" / f"{fam}-{w}.woff2"
        b64 = base64.b64encode(p.read_bytes()).decode()
        faces.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{b64}) format('woff2');font-weight:{w};font-display:block}}")
    tokens = (RUNTIME_DIR / "tokens.css").read_text(encoding="utf-8")
    brand_tokens = BRAND_DIR / "tokens.css"
    if brand_tokens.exists():
        tokens += "\n" + brand_tokens.read_text(encoding="utf-8")
    return "\n".join(faces) + "\n" + tokens + "\n" + (RUNTIME_DIR / "base.css").read_text(encoding="utf-8")


@lru_cache
def _runtime_js() -> tuple[str, str, str]:
    """lib, shell, edit — in load order (edit.js hooks onto the DECK the shell creates)."""
    return (
        (RUNTIME_DIR / "lib.js").read_text(encoding="utf-8"),
        (RUNTIME_DIR / "shell.js").read_text(encoding="utf-8"),
        (RUNTIME_DIR / "edit.js").read_text(encoding="utf-8"),
    )


@lru_cache
def icons() -> dict[str, str]:
    return json.loads((RUNTIME_DIR / "icons.json").read_text(encoding="utf-8"))


def default_logo() -> Path:
    for p in (Path(__file__).resolve().parents[5] / "showcase_app/assets/hp-logo-keyline.png", BRAND_DIR / "hp.svg", RUNTIME_DIR / "img" / "hp.svg"):
        if p.exists():
            return p
    raise FileNotFoundError("HP logo missing")


def clear_caches() -> None:
    _runtime_css.cache_clear()
    _runtime_js.cache_clear()
    icons.cache_clear()


def referenced_assets(specs: list[SlideSpec]) -> set[str]:
    keys: set[str] = set()
    for s in specs:
        for m in _ASSET_REF.finditer(s.html + s.css + s.js):
            keys.add(m.group(1) or m.group(2))
    return keys


def _script_safe(s: str) -> str:
    return s.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def _json_script(obj) -> str:
    return _script_safe(json.dumps(obj, ensure_ascii=False))


def assemble(deck: DeckInput, *, embed: bool = False, asset_base: str | None = None, instant: bool = False) -> str:
    """Build the deck. With asset_base, images are fetched from the server (preview); otherwise inlined."""
    specs = [s.spec for s in deck.slides]
    assets = dict(deck.assets)
    assets.setdefault("hp", default_logo())
    used = referenced_assets(specs) | {"hp"}

    img: dict[str, str] = {}
    if asset_base is None:
        for key in sorted(used):
            if key in assets and assets[key].exists():
                img[key] = _data_uri(assets[key])
    else:
        img["hp"] = _data_uri(assets["hp"])

    meta = []
    templates = []
    scripts = []
    css = []
    for ds in deck.slides:
        sp = ds.spec
        has_script = bool(sp.js.strip())
        meta.append({
            "id": ds.id, "title": sp.meta.title, "steps": sp.meta.steps, "notes": sp.meta.notes,
            "sources": sp.meta.sources, "theme": sp.meta.theme, "bleed": sp.meta.bleed, "auto": sp.meta.auto,
            "hasScript": has_script,
        })
        templates.append(f'<template data-slide="{htmllib.escape(ds.id)}">\n{sp.html}\n</template>')
        if sp.css.strip():
            css.append(f"/* slide {ds.id} */\n{sp.css}")
        if has_script:
            body = _script_safe(sp.js)
            scripts.append(
                f'<script data-slide="{ds.id}">\nDECK.define({json.dumps(ds.id)}, function(H){{\n"use strict";\n{body}\n'
                f'return {{mount: typeof mount === "function" ? mount : null, go: typeof go === "function" ? go : null}};\n}});\n</script>'
            )

    lib_js, shell_js, edit_js = _runtime_js()
    cfg = {"title": deck.title, "storageKey": deck.storage_key, "embed": embed, "assetBase": asset_base}
    per_slide_css = "\n".join(css).replace("</style", "<\\/style")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{htmllib.escape(DOCUMENT_CSP.split('; sandbox')[0], quote=True)}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="HP Deck Builder">
<title>{htmllib.escape(deck.title)}</title>
<style>
{_runtime_css()}
</style>
<style id="slide-css">
{per_slide_css}
</style>
</head>
<body{' class="instant"' if instant else ''}>
<div id="viewport"><div id="stage"></div></div>
<div id="progress"></div>
<div id="hud">→ NEXT &nbsp;·&nbsp; F FULLSCREEN &nbsp;·&nbsp; S PRESENTER &nbsp;·&nbsp; ? HELP</div>
<script id="deck-config" type="application/json">{_json_script(cfg)}</script>
<script id="assets" type="application/json">{_json_script({"img": img, "icons": icons()})}</script>
<script id="deck-slides" type="application/json">{_json_script(meta)}</script>
{chr(10).join(templates)}
<script>
{lib_js}
</script>
<script>
{shell_js}
</script>
<script>
{edit_js}
</script>
{chr(10).join(scripts)}
</body>
</html>
"""
