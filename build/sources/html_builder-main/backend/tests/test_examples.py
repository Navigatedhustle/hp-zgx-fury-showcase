"""The prompt pack and the runtime must agree.

`.plot` shipped documented-but-undefined: the skill promised a class the stylesheet never had, and every
slide that used it silently lost its layout. These are the cheap static guards against that whole family of
bug — a class or helper the model is told to use that does not exist, an icon name it cannot resolve, a
pattern name with no entry in the catalogue.

The expensive guard — every gold example actually renders in Chromium with zero QA errors — lives in
test_render_and_pipeline.py::test_gold_examples_render_without_errors and is deliberately not repeated here.
"""
from __future__ import annotations

import json
import re

from app.assemble import icons
from app.config import RUNTIME_DIR, SKILL_DIR
from app.skillpack import examples, read
from app.spec import _split_top

SKILL = read("HP_DECK_SKILL.md")
BASE_CSS = (RUNTIME_DIR / "base.css").read_text(encoding="utf-8")
LIB_JS = (RUNTIME_DIR / "lib.js").read_text(encoding="utf-8")

_CLASS = re.compile(r"\.([A-Za-z][\w-]*)")  # inside a selector prelude every .foo is a class
# ...but in prose only a token that STARTS with a dot is one: this skips "H.chart" and "1.5px", and
# still reads a compound like ".split.even" whole, so both of its classes are checked.
_DOC_CLASS = re.compile(r"(?<![\w-])\.[A-Za-z][\w.-]*")
_CODE = re.compile(r"`([^`]+)`")


def _section(name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}.*?$(.*?)(?=^## |\Z)", SKILL, re.S | re.M)
    assert m, f"section {name!r} missing from HP_DECK_SKILL.md"
    return m.group(1)


def _defined_classes(css: str, _top: bool = True) -> set[str]:
    """Every class name the stylesheet defines. Only selector preludes are read, so declaration
    values (`1.5px`, `.35s`) can never be mistaken for classes."""
    if _top:
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # a comment's apostrophe would derail the splitter
    out: set[str] = set()
    for prelude, body in _split_top(css):
        low = prelude.lower()
        if low.startswith(("@media", "@supports", "@container")):
            out |= _defined_classes(body, False)
        elif not prelude.startswith("@"):
            out |= set(_CLASS.findall(prelude))
    return out


BASE_CLASSES = _defined_classes(BASE_CSS)


def _documented_classes() -> set[str]:
    """Class names the skill tells the model to use, from the component-library section only."""
    out: set[str] = set()
    for span in _CODE.findall(_section("4. Component library (runtime classes — prefer these over custom CSS)")):
        for token in _DOC_CLASS.findall(span):
            out |= {c for c in token.split(".") if c}
    return out


def test_every_documented_class_exists_in_the_runtime():
    documented = _documented_classes()
    assert len(documented) > 80, "the component-library section stopped parsing"
    missing = sorted(c for c in documented if c not in BASE_CLASSES)
    assert not missing, f"documented in HP_DECK_SKILL.md but not defined in runtime/base.css: {missing}"


def test_every_documented_helper_exists_in_lib():
    """H.foo / H.chart.foo named in the skill must be exported by runtime/lib.js."""
    m = re.search(r"window\.H\s*=\s*\{(.*?)\};", LIB_JS, re.S)
    assert m, "window.H export not found in runtime/lib.js"
    export = m.group(1)
    top = set(re.findall(r"[{,\s]([A-Za-z_]\w*)\s*(?=[,}:])", export + ","))
    chart = set(re.findall(r"chart:\s*\{([^}]*)\}", export)[0].replace(" ", "").split(","))

    named = set(re.findall(r"\bH\.([a-z]\w*)(?:\.([a-z]\w*))?", SKILL))
    bad = []
    for first, second in named:
        if first == "chart" and second:
            if second not in chart:
                bad.append(f"H.chart.{second}")
        elif first in ("fmt", "state"):  # nested objects defined inline; their keys are checked below
            continue
        elif first not in top:
            bad.append(f"H.{first}")
    assert not bad, f"documented in HP_DECK_SKILL.md but not exported by runtime/lib.js: {sorted(set(bad))}"

    for obj in ("fmt", "state"):
        keys = set(re.findall(rf"\bH\.{obj}\.(\w+)", SKILL))
        body = re.search(rf"(?:const {obj} = |function {obj})", LIB_JS)
        assert body, obj
        for k in keys:
            assert re.search(rf"(?:^|[\s{{,]){k}\s*[(:]", LIB_JS, re.M), f"H.{obj}.{k} is documented but not defined"


def test_icons_are_consistent_and_resolvable():
    raw = json.loads((RUNTIME_DIR / "icons.json").read_text(encoding="utf-8"))
    assert raw == icons()
    for name, svg in raw.items():
        assert re.fullmatch(r"[a-z][a-z0-9-]*", name), name
        for attr in ('viewBox="0 0 24 24"', 'stroke-width="2"', 'stroke="currentColor"', 'fill="none"',
                     'stroke-linecap="round"', 'stroke-linejoin="round"', 'class="ic"', 'aria-hidden="true"'):
            assert attr in svg, f"icon {name!r} does not match the house SVG style: {attr} missing"
        assert svg.endswith("</svg>") and "<script" not in svg, name

    # the skill hands the model this exact list and forbids inventing names, so every icon an example
    # uses has to be in it
    used = {n for ex in examples() for n in re.findall(r'data-icon="([^"]+)"', ex.output)}
    assert used, "no example uses an icon any more — the check would pass vacuously"
    assert not (used - set(raw)), f"examples use icons that do not exist: {sorted(used - set(raw))}"


def _example_css(ex) -> str:
    m = re.search(r"<css>(.*?)</css>", ex.output, re.S)
    return m.group(1) if m else ""


def _example_html(ex) -> str:
    m = re.search(r"<html>(.*?)</html>", ex.output, re.S)
    return m.group(1) if m else ""


def test_examples_only_use_classes_that_exist():
    """A gold example is copied almost verbatim by the model. A class in one that nothing styles teaches
    the model a name that does nothing."""
    bad: list[str] = []
    for ex in examples():
        known = BASE_CLASSES | _defined_classes(_example_css(ex))
        for attr in re.findall(r'class="([^"]*)"', _example_html(ex)):
            for cls in attr.split():
                if cls not in known:
                    bad.append(f"{ex.name}: .{cls}")
    assert not bad, f"classes used by a gold example that neither base.css nor the example's own CSS defines: {sorted(set(bad))}"


def test_example_patterns_are_in_the_catalogue():
    catalogue = set(re.findall(r"^\| `([a-z-]+)`(?: / `([a-z-]+)`)?", _section("6. Pattern catalogue (pick the one that fits the content's shape)"), re.M))
    names = {n for pair in catalogue for n in pair if n}
    assert len(names) > 15, "the pattern catalogue stopped parsing"
    used = {ex.spec().meta.pattern for ex in examples()}
    assert not (used - names), f"gold examples use patterns missing from the §6 catalogue: {sorted(used - names)}"


def test_the_big_components_are_demonstrated_by_a_gold_example():
    """Documentation alone does not teach a 27B model a layout. Every component complex enough to get
    wrong needs a worked example in the prompt."""
    html = "\n".join(_example_html(ex) for ex in examples())
    js = "\n".join(ex.output for ex in examples())
    for cls in ("specs", "hook", "verdict", "lane", "rows", "kpi", "clock", "fnote",
                "matrix", "quad", "acc", "hotspot", "rail", "ticks", "mark", "timeline"):
        assert re.search(rf'class="[^"]*\b{cls}\b', html), f".{cls} is in the runtime but no gold example uses it"
    for helper in ("H.accordion", "H.hotspots", "H.chart.stackedBars", "H.chart.sparkline"):
        assert helper in js, f"{helper} is in lib.js but no gold example calls it"


def test_every_example_parses_and_declares_its_steps():
    for ex in examples():
        spec = ex.spec(ex.name)
        assert spec.meta.pattern and spec.meta.title, ex.name
        assert spec.meta.notes, f"{ex.name} has no speaker notes"
        assert (SKILL_DIR / "examples" / f"{ex.name}.md").exists()
