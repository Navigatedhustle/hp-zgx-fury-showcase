"""Deterministic slide edits.

Structured operations (set_text / delete / reorder / set_style / set_src) applied straight to a
spec's HTML — no LLM, no regeneration. The HTML comes from a model and the ops come from
a browser, so everything here is parse-then-rebuild (never regex surgery) and every op is
checked against the slide's contract before anything is written.

Elements are addressed by a ``data-eid`` stamped into the HTML on the first edit
(:func:`ensure_ids`); see the module notes below for why.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Collection, Literal, Sequence

from lxml import etree
from lxml import html as lxml_html
from pydantic import BaseModel, Field, TypeAdapter

from .spec import SlideSpec

# ---------------------------------------------------------------- addressing
# Why an injected id and not a DOM path: a path (`/0/2/1`) dies the moment a sibling is
# deleted or reordered — which is exactly what this module does — and a content hash dies
# on set_text. A `data-eid` is written once, travels with the element through every later
# edit, survives assembly (data-* attributes go into <template data-slide> untouched) and
# is what the iframe hands back when the user clicks something. It needs nothing from the
# LLM: ensure_ids() stamps whatever the model wrote.
EID_ATTR = "data-eid"
ROOT_EID = "root"  # reserved for the shell-created .slide section; never addressable
_EID_OK = re.compile(r"[a-zA-Z][\w-]{0,31}")

_VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_SKIP_TAGS = frozenset({"script", "style"})  # never addressable: editing inside them is code injection
_MAX_TEXT = 2000

# runtime hooks the step engine drives (runtime/shell.js: applyStep, autoSteps, resolveAssets)
_STEP_HOOKS = ("[data-step]", "[data-count]", ".appear")
_ICON_ATTR = "data-icon"


class EditError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- operations
class _Op(BaseModel):
    eid: str


class SetTextOp(_Op):
    op: Literal["set_text"] = "set_text"
    text: str
    replace_children: bool = False  # opt-in: set_text on a container discards its markup


class DeleteOp(_Op):
    op: Literal["delete"] = "delete"


class ReorderOp(_Op):
    op: Literal["reorder"] = "reorder"
    index: int  # target position among the parent's *element* children, 0-based


class SetStyleOp(_Op):
    op: Literal["set_style"] = "set_style"
    style: dict[str, str]  # property -> value; an empty value removes the declaration


class SetSrcOp(_Op):
    """Point an <img> at another deck asset — the user's own upload, usually. Never a URL: every image in
    a deck is inlined by assemble.py, and an external src is exactly what the skill forbids."""

    op: Literal["set_src"] = "set_src"
    key: str


EditOp = Annotated[SetTextOp | DeleteOp | ReorderOp | SetStyleOp | SetSrcOp, Field(discriminator="op")]
_OPS = TypeAdapter(list[EditOp])


class EditRequest(BaseModel):
    """Body shape for the edit route."""

    ops: list[EditOp] = Field(default_factory=list)


def parse_ops(raw: Sequence[Any]) -> list[EditOp]:
    """Validate a list of raw op dicts (raises pydantic ValidationError)."""
    return _OPS.validate_python(list(raw))


# ---------------------------------------------------------------- results
class EditNote(BaseModel):
    code: str
    message: str
    eid: str = ""


class OpResult(BaseModel):
    index: int
    op: str
    eid: str
    ok: bool = True
    code: str = ""
    message: str = ""
    warnings: list[EditNote] = Field(default_factory=list)


class EditResult(BaseModel):
    """What happened. `spec` is the original one untouched when `ok` is False."""

    ok: bool
    spec: SlideSpec
    changed: bool = False
    results: list[OpResult] = Field(default_factory=list)
    warnings: list[EditNote] = Field(default_factory=list)
    error: str = ""
    error_code: str = ""
    failed_index: int | None = None
    qa_recommended: bool = False
    qa_reasons: list[str] = Field(default_factory=list)


class ElementInfo(BaseModel):
    """One addressable element, for the editor's element picker / outline."""

    eid: str
    tag: str
    classes: list[str] = Field(default_factory=list)
    parent: str | None = None
    index: int = 0
    depth: int = 0
    text: str = ""
    has_children: bool = False
    editable_text: bool = True
    deletable: bool = True
    locks: list[str] = Field(default_factory=list)
    asset: str = ""  # the asset key an <img> shows; set only for images the editor may swap


# ---------------------------------------------------------------- html io
def _parse(html: str) -> lxml_html.HtmlElement:
    """Parse a spec fragment into a synthetic wrapper whose children are the top-level nodes."""
    return lxml_html.fragment_fromstring(html or "", create_parent="div")


def _serialize(wrapper: lxml_html.HtmlElement) -> str:
    """Serialize the wrapper's contents back to a fragment (the wrapper itself is dropped)."""
    out = wrapper.text or ""
    out += "".join(etree.tostring(c, encoding="unicode", method="html") for c in wrapper)
    return out.strip()


def _is_el(node: Any) -> bool:
    return isinstance(node.tag, str)


def _kids(node: Any) -> list[Any]:
    """Element children only (comments and PIs are structure the user cannot address)."""
    return [c for c in node if _is_el(c)]


def _elements(wrapper: Any) -> list[Any]:
    out: list[Any] = []

    def walk(node: Any) -> None:
        for c in _kids(node):
            if c.tag in _SKIP_TAGS:
                continue
            out.append(c)
            walk(c)

    walk(wrapper)
    return out


# ---------------------------------------------------------------- id stamping
def _assign_ids(wrapper: Any) -> bool:
    """Give every addressable element a unique data-eid. Existing valid ids are kept."""
    els = _elements(wrapper)
    keep: dict[int, str] = {}
    used: set[str] = set()
    for el in els:
        cur = (el.get(EID_ATTR) or "").strip()
        if cur and cur != ROOT_EID and _EID_OK.fullmatch(cur) and cur not in used:
            used.add(cur)
            keep[id(el)] = cur
    changed, n = False, 0
    for el in els:
        if id(el) in keep:
            if el.get(EID_ATTR) != keep[id(el)]:
                el.set(EID_ATTR, keep[id(el)])
                changed = True
            continue
        n += 1
        while f"e{n}" in used:
            n += 1
        used.add(f"e{n}")
        el.set(EID_ATTR, f"e{n}")
        changed = True
    return changed


def ensure_ids(spec: SlideSpec) -> SlideSpec:
    """Stamp stable element ids into spec.html. Idempotent; returns the spec unchanged when already stamped."""
    wrapper = _parse(spec.html)
    if not _assign_ids(wrapper):
        return spec
    return SlideSpec(meta=spec.meta, html=_serialize(wrapper), css=spec.css, js=spec.js)


def strip_ids(html: str) -> str:
    """Remove every data-eid (for diffing against pre-edit HTML or handing clean markup to the LLM)."""
    wrapper = _parse(html)
    for el in _elements(wrapper):
        if el.get(EID_ATTR) is not None:
            del el.attrib[EID_ATTR]
    return _serialize(wrapper)


# ---------------------------------------------------------------- hooks the slide depends on
_STR_LIT = re.compile(r"""['"]([^'"\n]{1,200})['"]""")
_HOOK_IN_SEL = re.compile(r"\.(-?[_a-zA-Z][\w-]*)|\[\s*([\w-]+)|#(-?[_a-zA-Z][\w-]*)")


def script_hooks(js: str) -> set[str]:
    """Class / attribute / id hooks the slide script selects on.

    The script only ever reaches the DOM through selectors (H.$, H.$$, querySelector,
    closest, H.reveal, ...), so the string literals that look like selectors are the
    contract between markup and code. H.segmented/H.tabs query fixed attributes of their
    own (runtime/lib.js), so those are implied.
    """
    hooks: set[str] = set()
    if not js:
        return hooks
    for lit in _STR_LIT.findall(js):
        if not re.search(r"[.\[#]", lit):
            continue  # a plain word is a value, not a selector
        for cls, attr, ident in _HOOK_IN_SEL.findall(lit):
            if cls:
                hooks.add(f".{cls}")
            elif attr:
                hooks.add(f"[{attr}]")
            elif ident:
                hooks.add(f"#{ident}")
    if "H.segmented" in js:
        hooks.add("[data-v]")
    if "H.tabs" in js:
        hooks |= {"[data-tab]", "[data-panel]"}
    return hooks


def _hooks_of(el: Any) -> set[str]:
    out = {f"[{k}]" for k in el.keys() if k != EID_ATTR}
    out |= {f".{c}" for c in (el.get("class") or "").split()}
    if el.get("id"):
        out.add(f"#{el.get('id')}")
    return out


def _subtree(el: Any) -> list[Any]:
    out = [el]
    for c in _kids(el):
        out.extend(_subtree(c))
    return out


def _count_hook(wrapper: Any, hook: str) -> int:
    return sum(1 for e in _elements(wrapper) if hook in _hooks_of(e))


# ---------------------------------------------------------------- style allowlist
# category "layout" means the change can move things around -> QA is worth re-running.
_STYLE_PROPS: dict[str, str] = {
    "color": "cosmetic", "background": "cosmetic", "background-color": "cosmetic",
    "border-color": "cosmetic", "opacity": "cosmetic", "font-weight": "cosmetic",
    "font-style": "cosmetic", "text-transform": "cosmetic", "text-decoration": "cosmetic",
    "text-align": "cosmetic", "border-radius": "cosmetic", "box-shadow": "cosmetic",
    "object-fit": "cosmetic", "object-position": "cosmetic",
    "font-size": "layout", "line-height": "layout", "letter-spacing": "layout",
    "width": "layout", "height": "layout", "min-width": "layout", "min-height": "layout",
    "max-width": "layout", "max-height": "layout", "border-width": "layout",
    "margin": "layout", "margin-top": "layout", "margin-right": "layout",
    "margin-bottom": "layout", "margin-left": "layout",
    "padding": "layout", "padding-top": "layout", "padding-right": "layout",
    "padding-bottom": "layout", "padding-left": "layout",
    "gap": "layout", "row-gap": "layout", "column-gap": "layout",
    "align-items": "layout", "justify-content": "layout", "flex-direction": "layout",
    "flex-wrap": "layout", "align-self": "layout", "order": "layout",
    # Reshaping a grid is the one layout change the editor could not express at all: a 3-up card row
    # could be recoloured and resized but never made 2-up. `flex` is here for the same reason — in a
    # flex row, `width` alone does nothing once a sibling is growing.
    "grid-template-columns": "layout", "grid-template-rows": "layout", "grid-column": "layout",
    "grid-row": "layout", "flex": "layout", "flex-grow": "layout", "flex-shrink": "layout",
    "flex-basis": "layout",
}
# position/inset/transform/float/z-index are deliberately absent: they take an element out
# of the 1600x900 flow the CSS was written against. Resizing works *with* that flow instead —
# a drag writes width/height/flex-basis, never a coordinate.
_VALUE_BAN = re.compile(r"""url\s*\(|expression\s*\(|image-set|javascript:|@|/\*|\\|[;{}<>!"']""", re.I)
_VALUE_TOKEN = re.compile(
    r"""^(?:
        -?\d+(?:\.\d+)?(?:px|rem|em|%|vw|vh|vmin|vmax|ch|fr|pt|deg|s|ms)?
      | \#[0-9a-fA-F]{3,8}
      | [a-zA-Z][a-zA-Z0-9-]{0,32}
      | (?:rgb|rgba|hsl|hsla)\(\s*[0-9a-zA-Z.,%\s/-]{1,60}\)
      | var\(\s*--[a-zA-Z0-9-]{1,40}\s*(?:,\s*[#\w.%\s-]{1,40})?\)
      | calc\(\s*[0-9a-zA-Z.%+\s-]{1,60}\)
      | (?:repeat|minmax|fit-content)\(\s*[0-9a-zA-Z.,%\s()-]{1,60}\)
    )$""",
    re.X,
)


def _depth_split(s: str, sep: str) -> list[str]:
    """Split on sep outside parens and string literals."""
    out: list[str] = []
    depth, quote, buf = 0, "", []
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return out


def _tokens(value: str) -> list[str]:
    out: list[str] = []
    depth, buf = 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch.isspace() and depth == 0:
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def check_style(prop: str, value: str) -> str:
    """Validate one declaration; returns its category. Raises EditError when not allowed."""
    prop = prop.strip().lower()
    if prop not in _STYLE_PROPS:
        raise EditError("style-prop", f"style property {prop!r} is not editable")
    value = value.strip()
    if not value:
        return _STYLE_PROPS[prop]  # empty means "remove"
    if len(value) > 120 or _VALUE_BAN.search(value):
        raise EditError("style-value", f"value {value!r} for {prop} is not allowed")
    toks = _tokens(value)
    # Track lists are legitimately long ("repeat(4, 1fr)" is one token, but "1fr 2fr 1fr 1fr" is four
    # and a six-column grid is six). Everything else stays tight.
    limit = 8 if prop.startswith("grid-template") else 4
    if not toks or len(toks) > limit:
        raise EditError("style-value", f"value {value!r} for {prop} is not allowed")
    for t in toks:
        if not _VALUE_TOKEN.match(t):
            raise EditError("style-value", f"value {value!r} for {prop} is not allowed")
    return _STYLE_PROPS[prop]


def _merge_style(existing: str, updates: dict[str, str]) -> str:
    decls: list[list[str]] = []
    for d in _depth_split(existing or "", ";"):
        d = d.strip()
        if not d or ":" not in d:
            continue
        k, v = d.split(":", 1)
        decls.append([k.strip().lower(), v.strip()])
    for prop, value in updates.items():
        prop, value = prop.strip().lower(), value.strip()
        hit = next((d for d in decls if d[0] == prop), None)
        if hit is not None:
            hit[1] = value
        elif value:
            decls.append([prop, value])
    return ";".join(f"{k}:{v}" for k, v in decls if v)


# ---------------------------------------------------------------- tail-safe structure edits
def _retail(parent: Any, tails: list[str | None]) -> None:
    """Reassign tails by position so indentation stays with the layout, not with the element."""
    for el, tail in zip(_kids(parent), tails):
        el.tail = tail


def _remove(el: Any) -> None:
    parent = el.getparent()
    sibs = _kids(parent)
    k = sibs.index(el)
    tails = [s.tail for s in sibs]
    parent.remove(el)
    _retail(parent, tails[:k] + tails[k + 1 :])


def _move(el: Any, index: int) -> None:
    parent = el.getparent()
    tails = [s.tail for s in _kids(parent)]
    parent.remove(el)
    rest = _kids(parent)
    at = list(parent).index(rest[index]) if index < len(rest) else len(list(parent))
    parent.insert(at, el)
    _retail(parent, tails)


# ---------------------------------------------------------------- applying
class _Ctx:
    def __init__(self, wrapper: Any, spec: SlideSpec, assets: Collection[str] | None = None) -> None:
        self.wrapper = wrapper
        self.spec = spec
        self.assets = assets  # the deck's image keys; None = the caller did not say, so any well-formed key
        self.hooks = script_hooks(spec.js)
        self.qa_reasons: list[str] = []

    def find(self, eid: str) -> Any:
        if not eid or eid == ROOT_EID:
            raise EditError("root-protected", "the slide root is not editable")
        for el in _elements(self.wrapper):
            if el.get(EID_ATTR) == eid:
                return el
        raise EditError("unknown-eid", f"no element {eid!r} in this slide")

    def qa(self, reason: str) -> None:
        if reason not in self.qa_reasons:
            self.qa_reasons.append(reason)


def _step_warnings(el: Any, verb: str) -> list[EditNote]:
    """Flag step-engine dependencies in a subtree (see runtime/shell.js applyStep/autoSteps)."""
    out: list[EditNote] = []
    eid = el.get(EID_ATTR) or ""
    sub = _subtree(el)
    appear = [e for e in sub if "appear" in (e.get("class") or "").split()]
    loose = [e for e in appear if e.get("data-step") is None]
    if loose:
        out.append(EditNote(code="step-order", eid=eid,
                            message=f"{verb} {len(loose)} .appear element(s) without data-step — the reveal order shifts"))
    if any(e.get("data-step") is not None for e in sub):
        out.append(EditNote(code="step-ref", eid=eid, message=f"{verb} an element with data-step — check meta.steps still fits"))
    if any(e.get("data-count") is not None for e in sub):
        out.append(EditNote(code="counter", eid=eid, message=f"{verb} an animated counter ([data-count])"))
    if any(e.get("src", "").startswith("asset:") or "asset:" in (e.get("style") or "") for e in sub):
        out.append(EditNote(code="asset", eid=eid, message=f"{verb} an element that references a deck asset"))
    return out


def _script_check(ctx: _Ctx, el: Any) -> list[EditNote]:
    """Refuse to delete the last element a script selector can find; warn when others remain."""
    notes: list[EditNote] = []
    eid = el.get(EID_ATTR) or ""
    sub = _subtree(el)
    for hook in sorted(ctx.hooks):
        inside = sum(1 for e in sub if hook in _hooks_of(e))
        if not inside:
            continue
        total = _count_hook(ctx.wrapper, hook)
        if inside >= total:
            raise EditError("script-ref", f"the slide script selects {hook} and this is the last element carrying it")
        notes.append(EditNote(code="script-ref", eid=eid, message=f"the slide script also selects {hook} ({total - inside} left)"))
    return notes


def _apply_set_text(ctx: _Ctx, op: SetTextOp) -> list[EditNote]:
    el = ctx.find(op.eid)
    if el.tag in _VOID_TAGS:
        raise EditError("void-element", f"<{el.tag}> has no text content")
    if el.get(_ICON_ATTR) is not None:
        raise EditError("icon-slot", "the runtime fills [data-icon] elements; their text cannot be set")
    if len(op.text) > _MAX_TEXT:
        raise EditError("too-long", f"text is longer than {_MAX_TEXT} characters")
    kids = _kids(el)
    if kids and not op.replace_children:
        raise EditError("has-children", f"{op.eid} contains markup; set replace_children to discard it")
    notes: list[EditNote] = []
    if kids:
        for kid in kids:
            notes.extend(_script_check(ctx, kid))
            for note in _step_warnings(kid, "replacing"):
                if note.code in ("step-ref", "counter"):
                    raise EditError("protected-children", f"{op.eid} contains step-driven markup ({note.code}); delete it explicitly instead")
                notes.append(note)
        for kid in kids:
            el.remove(kid)
        ctx.qa("set_text replaced child markup")
    if el.get("data-count") is not None:
        notes.append(EditNote(code="counter", eid=op.eid, message="the runtime rewrites this element's text from data-count"))
    old = (el.text or "").strip()
    el.text = op.text
    if len(op.text) > len(old) + 10 and len(op.text) > len(old) * 1.2:
        ctx.qa("set_text made the content longer (overflow risk)")
    return notes


def _apply_delete(ctx: _Ctx, op: DeleteOp) -> list[EditNote]:
    el = ctx.find(op.eid)
    parent = el.getparent()
    if parent is ctx.wrapper and len(_kids(parent)) == 1:
        raise EditError("empty-slide", "this is the slide's only top-level element")
    notes = _script_check(ctx, el)
    notes.extend(_step_warnings(el, "deleting"))
    _remove(el)
    ctx.qa("delete changes the layout")
    return notes


def _apply_reorder(ctx: _Ctx, op: ReorderOp) -> list[EditNote]:
    el = ctx.find(op.eid)
    parent = el.getparent()
    sibs = _kids(parent)
    if len(sibs) < 2:
        raise EditError("no-siblings", f"{op.eid} has no siblings to move among")
    if not 0 <= op.index < len(sibs):
        raise EditError("bad-index", f"index {op.index} is outside 0..{len(sibs) - 1}")
    if sibs.index(el) == op.index:
        return [EditNote(code="noop", eid=op.eid, message="already at that position")]
    notes: list[EditNote] = []
    # a loose .appear reveals by document order, so moving anything past one re-times the slide
    loose = sum(1 for s in sibs for e in _subtree(s)
                if "appear" in (e.get("class") or "").split() and e.get("data-step") is None)
    if loose:
        notes.append(EditNote(code="step-order", eid=op.eid,
                              message=f"{loose} sibling .appear element(s) reveal by document order — the sequence changes"))
    notes.extend(n for n in _step_warnings(el, "moving") if n.code != "step-order")
    _move(el, op.index)
    ctx.qa("reorder changes the layout")
    return notes


def _apply_set_style(ctx: _Ctx, op: SetStyleOp) -> list[EditNote]:
    el = ctx.find(op.eid)
    if not op.style:
        raise EditError("empty-style", "no style declarations given")
    cats = {prop: check_style(prop, value) for prop, value in op.style.items()}
    # inline, so the appended declarations can never disturb scope_css or the keyframe renaming
    merged = _merge_style(el.get("style") or "", op.style)
    if merged:
        el.set("style", merged)
    elif el.get("style") is not None:
        del el.attrib["style"]
    if any(c == "layout" for c in cats.values()):
        ctx.qa("set_style changed layout properties")
    return []


ASSET_KEY = re.compile(r"[\w.-]{1,64}")


def _apply_set_src(ctx: _Ctx, op: SetSrcOp) -> list[EditNote]:
    el = ctx.find(op.eid)
    if el.tag != "img":
        raise EditError("not-image", f"{op.eid} is a <{el.tag}>, not an image")
    if not ASSET_KEY.fullmatch(op.key) or op.key == "hp":
        raise EditError("bad-asset", f"{op.key!r} is not a deck image")
    if ctx.assets is not None and op.key not in ctx.assets:
        raise EditError("unknown-asset", f"no image {op.key!r} in this deck")
    el.set("src", f"asset:{op.key}")
    # A new picture has its own proportions; the old one's alt text describes the wrong thing.
    el.set("alt", el.get("alt") or "")
    ctx.qa("set_src swapped an image (its proportions may differ)")
    return []


_APPLY = {"set_text": _apply_set_text, "delete": _apply_delete, "reorder": _apply_reorder, "set_style": _apply_set_style,
          "set_src": _apply_set_src}


def apply_ops(spec: SlideSpec, ops: Sequence[EditOp], assets: Collection[str] | None = None) -> EditResult:
    """Apply ops to a spec and return a new one. Atomic: on any failure the spec is untouched.

    CSS and JS are never rewritten — style changes go inline — so the caller does not need
    to re-run scope_css (and must not: it would rename already-renamed keyframes).
    """
    ops = list(ops)
    if not ops:
        return EditResult(ok=True, spec=spec)
    stamped = ensure_ids(spec)
    wrapper = _parse(stamped.html)
    _assign_ids(wrapper)
    ctx = _Ctx(wrapper, stamped, assets)

    results: list[OpResult] = []
    for i, op in enumerate(ops):
        try:
            notes = _APPLY[op.op](ctx, op)
        except EditError as e:
            results.append(OpResult(index=i, op=op.op, eid=op.eid, ok=False, code=e.code, message=str(e)))
            return EditResult(ok=False, spec=spec, results=results, error=str(e), error_code=e.code, failed_index=i)
        results.append(OpResult(index=i, op=op.op, eid=op.eid, warnings=notes))

    html = _serialize(wrapper)
    out = SlideSpec(meta=spec.meta.model_copy(deep=True), html=html, css=spec.css, js=spec.js)
    warnings = [n for r in results for n in r.warnings]
    return EditResult(
        ok=True,
        spec=out,
        changed=html != spec.html,
        results=results,
        warnings=warnings,
        qa_recommended=bool(ctx.qa_reasons),
        qa_reasons=ctx.qa_reasons,
    )


# ---------------------------------------------------------------- outline for the editor
def outline(spec: SlideSpec) -> list[ElementInfo]:
    """Flat, document-ordered list of what the editor may address. Call ensure_ids first."""
    wrapper = _parse(spec.html)
    _assign_ids(wrapper)
    hooks = script_hooks(spec.js)
    counts = {h: _count_hook(wrapper, h) for h in hooks}
    out: list[ElementInfo] = []

    def walk(node: Any, parent: str | None, depth: int) -> None:
        kids = _kids(node)
        for idx, el in enumerate(kids):
            if el.tag in _SKIP_TAGS:
                continue
            eid = el.get(EID_ATTR) or ""
            locks: list[str] = []
            sub = _subtree(el)
            for hook in sorted(hooks):
                if sum(1 for e in sub if hook in _hooks_of(e)) >= counts.get(hook, 0) > 0:
                    locks.append(f"script:{hook}")
            if parent is None and len(kids) == 1:
                locks.append("only-top-level")
            editable = el.tag not in _VOID_TAGS and el.get(_ICON_ATTR) is None
            src = el.get("src") or ""
            out.append(ElementInfo(
                eid=eid, tag=el.tag, classes=(el.get("class") or "").split(), parent=parent, index=idx,
                depth=depth, text=" ".join(el.text_content().split())[:80], has_children=bool(_kids(el)),
                editable_text=editable, deletable=not locks, locks=locks,
                asset=src[6:] if el.tag == "img" and src.startswith("asset:") else "",
            ))
            walk(el, eid, depth + 1)

    walk(wrapper, None, 0)
    return out
