"""Slide spec: the contract the LLM writes. Parsing, validation and auto-repair."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

THEMES = ("light", "navy", "dark", "blue", "tint")


class SpecMeta(BaseModel):
    pattern: str = "custom"
    title: str = ""
    steps: int | None = None
    theme: str = "light"
    bleed: bool = False
    auto: bool = True
    notes: list[str] = Field(default_factory=list)
    sources: str = ""


class SlideSpec(BaseModel):
    meta: SpecMeta = Field(default_factory=SpecMeta)
    html: str = ""
    css: str = ""
    js: str = ""


class Issue(BaseModel):
    severity: Literal["error", "warn"]
    code: str
    message: str


_SECTIONS = ("meta", "html", "css", "script")
# models sometimes write attributes on the section tag (<html lang="en">). <meta> stays bare so that a
# void <meta charset=...> inside the html body is never mistaken for an unclosed section.
_OPEN_PAT = {t: rf"<{t}>" if t == "meta" else rf"<{t}(?:\s[^<>]*)?>" for t in _SECTIONS}
_TAG = {t: re.compile(rf"{_OPEN_PAT[t]}(.*?)</{t}\s*>", re.S | re.I) for t in _SECTIONS}
_OPEN = {t: re.compile(_OPEN_PAT[t], re.I) for t in _SECTIONS}
_CLOSE = {t: re.compile(rf"</{t}\s*>", re.I) for t in _SECTIONS}
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _strip_fence(s: str) -> str:
    return _FENCE.sub("", s.strip()).strip()


def _loads_lenient(raw: str) -> dict:
    raw = _strip_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        txt = re.sub(r",\s*([}\]])", r"\1", m.group(0))  # trailing commas
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    raise ValueError("meta is not valid JSON")


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply (tolerates think blocks, fences, trailing commas)."""
    return _loads_lenient(_THINK.sub("", text))


def _is_truncated(text: str, tag: str) -> bool:
    """True when the last opening tag has no closing tag after it (reply cut off mid-section)."""
    last = None
    for last in _OPEN[tag].finditer(text):  # noqa: B007 - we want the last match
        pass
    return last is not None and not _CLOSE[tag].search(text, last.end())


def parse_spec(text: str, slide_id: str) -> tuple[SlideSpec, list[Issue]]:
    """Parse tagged output. Raises ValueError when the reply is unusable."""
    text = _THINK.sub("", text or "")
    # unterminated think (reasoning cut off): keep what follows the last </think> or the whole text
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    parts = {}
    for tag, rx in _TAG.items():
        # a missing section is fine (<script> is optional); one that opens and never closes is not
        if _is_truncated(text, tag):
            raise ValueError(f"<{tag}> section is never closed — the reply was cut off")
        m = rx.findall(text)
        parts[tag] = m[-1] if m else ""  # last occurrence wins (models sometimes draft twice)
    if not parts["html"].strip():
        raise ValueError("missing <html> section")
    issues: list[Issue] = []
    meta = SpecMeta()
    if parts["meta"].strip():
        try:
            meta = SpecMeta.model_validate(_loads_lenient(parts["meta"]))
        except Exception as e:  # noqa: BLE001
            issues.append(Issue(severity="warn", code="meta", message=f"meta unreadable, defaults used: {e}"))
    else:
        issues.append(Issue(severity="warn", code="meta", message="missing <meta> section"))
    spec = SlideSpec(meta=meta, html=_strip_fence(parts["html"]), css=_strip_fence(parts["css"]), js=_strip_fence(parts["script"]))
    return normalize(spec, slide_id, issues)


# ---------------------------------------------------------------- normalization
_EXT_URL = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""", re.I)
_SCRIPT_TAG = re.compile(r"<script\b.*?</script>", re.S | re.I)
_STYLE_TAG = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
_OUTER_SLIDE = re.compile(r"^\s*<(?:section|div)\b[^>]*class\s*=\s*[\"'][^\"']*\bslide\b[^\"']*[\"'][^>]*>(.*)</(?:section|div)>\s*$", re.S | re.I)


def normalize(spec: SlideSpec, slide_id: str, issues: list[Issue] | None = None) -> tuple[SlideSpec, list[Issue]]:
    issues = list(issues or [])
    html = spec.html
    # inline <style> blocks move to css; inline <script> blocks are dropped
    styles = _STYLE_TAG.findall(html)
    if styles:
        spec.css = "\n".join(styles) + "\n" + spec.css
        html = _STYLE_TAG.sub("", html)
        issues.append(Issue(severity="warn", code="inline-style", message="moved <style> from html to css"))
    if _SCRIPT_TAG.search(html):
        html = _SCRIPT_TAG.sub("", html)
        issues.append(Issue(severity="warn", code="inline-script", message="removed <script> from html"))
    # the shell creates the .slide root; unwrap if the model wrote it anyway
    m = _OUTER_SLIDE.match(html)
    if m:
        html = m.group(1)
    spec.html = html.strip()

    if spec.meta.theme not in THEMES:
        issues.append(Issue(severity="warn", code="theme", message=f"unknown theme {spec.meta.theme!r}, using light"))
        spec.meta.theme = "light"
    if spec.meta.steps is not None:
        if spec.meta.steps < 0 or spec.meta.steps > 12:
            issues.append(Issue(severity="warn", code="steps", message=f"steps={spec.meta.steps} clamped to 0..12"))
            spec.meta.steps = max(0, min(12, spec.meta.steps))
    spec.meta.notes = [str(n) for n in spec.meta.notes if str(n).strip()][:12]

    if _EXT_URL.search(spec.html) or _EXT_URL.search(spec.css) or re.search(r"https?://", spec.js):
        # links (<a href>) to the web are fine; resources are not
        bad = re.search(r"""(?:src\s*=\s*["']\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import)""", spec.html + spec.css, re.I)
        if bad or re.search(r"fetch\(|XMLHttpRequest|import\(", spec.js):
            issues.append(Issue(severity="error", code="external", message="external resource referenced; decks must be self-contained"))

    spec.css = scope_css(spec.css, slide_id)
    js_issues = check_js(spec.js)
    issues.extend(js_issues)
    return spec, issues


def check_js(js: str) -> list[Issue]:
    out: list[Issue] = []
    if not js.strip():
        return out
    if not re.search(r"function\s+(go|mount)\s*\(", js) and not re.search(r"\b(go|mount)\s*=\s*(\(|function|[a-z]+\s*=>)", js):
        out.append(Issue(severity="warn", code="js-api", message="script defines neither go(root, step) nor mount(root)"))
    if re.search(r"document\.(getElementById|querySelector(All)?)\(", js):
        out.append(Issue(severity="warn", code="js-global-query", message="query inside root (H.$(sel, root)), not document"))
    if re.search(r"\b(setInterval|localStorage|eval|new Function)\b", js):
        out.append(Issue(severity="warn", code="js-risky", message="avoid setInterval/localStorage/eval in slide scripts"))
    return out


# ---------------------------------------------------------------- CSS scoping
def _walk(s: str):
    """Yield (index, char) for every character outside string literals (escapes respected)."""
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in "\"'":
            i += 1
            while i < n and s[i] != ch:
                i += 2 if s[i] == "\\" else 1
            i += 1
            continue
        yield i, ch
        i += 1


def _split_list(s: str, sep: str) -> list[str]:
    """Split on sep at paren/bracket depth 0 and outside strings (:is(.a, .b), [data-k="a,b"])."""
    out, depth, start = [], 0, 0
    for i, ch in _walk(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            out.append(s[start:i])
            start = i + 1
    out.append(s[start:])
    return [p for p in out if p.strip()]


def _split_top(css: str) -> list[tuple[str, str]]:
    """Split CSS into (prelude, body) blocks at top level. Declarations outside blocks are dropped."""
    out: list[tuple[str, str]] = []
    start, open_at, depth = 0, -1, 0
    for i, ch in _walk(css):  # strings are skipped: content:"{" must not open a block
        if ch == "{":
            depth += 1
            if depth == 1:
                open_at = i
        elif ch == "}":
            if not depth:  # stray closer: it must not end up in the next prelude
                start = i + 1
                continue
            depth -= 1
            if depth == 0:
                # brace-less statements (@import "a.css"; a stray declaration) cling to the next prelude
                parts = _split_list(css[start:open_at], ";")
                out.append(((parts[-1] if parts else "").strip(), css[open_at + 1 : i]))
                start = i + 1
    return out  # an unterminated trailing block is dropped rather than leaked unscoped


def _scope_selector(sel: str, scope: str) -> str:
    sel = sel.strip()
    if not sel:
        return sel
    if sel.startswith(scope):
        return sel
    for root in (":root", "html", "body", ".slide-root", ".slide", "section.slide", ":scope"):
        if sel == root:
            return scope
        if sel.startswith(root + " ") or sel.startswith(root + ">") or sel.startswith(root + ".") or sel.startswith(root + ":"):
            rest = sel[len(root):]
            return scope + rest
    return f"{scope} {sel}"


# keyframe names are global, so every slide gets its own (two slides may both define "pop")
_KEYFRAMES = re.compile(r"^@(?:-\w+-)?keyframes\s+(.+)$", re.S | re.I)
_ANIM_DECL = re.compile(r"(animation(?:-name)?\s*:)([^;{}]*)", re.I)


def _rename_animations(css: str, names: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        value = m.group(2)
        for old, new in names.items():
            value = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, value)
        return m.group(1) + value

    return _ANIM_DECL.sub(sub, css)


def _scope_rules(css: str, slide_id: str, frames: dict[str, str]) -> str:
    scope = f".s-{slide_id}"
    rules = []
    for prelude, body in _split_top(css):
        low = prelude.lower()
        if low.startswith("@media") or low.startswith("@supports") or low.startswith("@container"):
            rules.append(f"{prelude}{{{_scope_rules(body, slide_id, frames)}}}")
        elif (m := _KEYFRAMES.match(prelude)) is not None:
            name = m.group(1).strip().strip("\"'")
            frames[name] = f"{name}-s-{slide_id}"
            rules.append(f"{prelude[:m.start(1)]}{frames[name]}{{{body}}}")  # body (from/to/%) stays verbatim
        elif low.startswith("@font-face") or low.startswith("@import") or low.startswith("@page"):
            continue
        elif prelude.startswith("@"):
            continue
        else:
            sels = ",".join(_scope_selector(s, scope) for s in _split_list(prelude, ","))
            rules.append(f"{sels}{{{body.strip()}}}")
    return "\n".join(rules)


def scope_css(css: str, slide_id: str) -> str:
    frames: dict[str, str] = {}  # keyframe name -> slide-local name, collected at every nesting level
    out = _scope_rules(re.sub(r"/\*.*?\*/", "", css or "", flags=re.S), slide_id, frames)
    return _rename_animations(out, frames) if frames else out


# ---------------------------------------------------------------- serialization
def to_tagged(spec: SlideSpec) -> str:
    """Render a spec back into the tagged format (for few-shot examples and repair prompts)."""
    meta = spec.meta.model_dump()
    return (
        f"<meta>{json.dumps(meta, ensure_ascii=False)}</meta>\n"
        f"<html>\n{spec.html}\n</html>\n"
        f"<css>\n{spec.css}\n</css>\n"
        f"<script>\n{spec.js}\n</script>"
    )
