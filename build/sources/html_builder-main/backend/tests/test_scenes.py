"""The interaction catalogue (`H.scene` in runtime/lib.js).

Variant A used to invent a step machine per slide: build the markup, wire a control, recompute on input,
set the complete state for any step idempotently, reset when the audience steps backwards, and keep the
control live after the last step. Done freehand fifteen times a deck, that is why cinematic slides came
out worse than the calm ones.

A scene owns that glue, so the glue is tested once — here, in a real browser, against the contract the
catalogue promises:

  * go(step) sets the COMPLETE state for that step, in any order, any number of times
  * a control still works after the last step
  * stepping backwards genuinely reverses

These render in headless Chromium, so they belong with the other slow QA tests.
"""
import asyncio
import json

import pytest
from app.config import RUNTIME_DIR
from app.qa.render_check import check_spec
from app.spec import parse_spec

ASSETS = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}


def _spec(steps: int, html: str, script: str, css: str = "") -> str:
    return (f'<meta>{{"steps":{steps},"notes":["Speaker note"],"sources":""}}</meta>\n'
            f"<html>{html}</html>\n<css>{css}</css>\n<script>{script}</script>")


# ---------------------------------------------------------------- rendering
# Rendered through check_spec, which is exactly what the pipeline does: it walks every step, not only
# the last, so a scene that breaks halfway shows up here the same way it would on a real slide.
def _report(tmp_path, spec_text: str):
    spec, _ = parse_spec(spec_text, "sc")
    return asyncio.run(check_spec(spec, "sc", ASSETS, tmp_path))


def _codes(rep):
    return {f.code for f in rep.findings}


# ---------------------------------------------------------------- compare
COMPARE = _spec(2, """
<div class="wrap" data-scene>
  <h1 class="title">Cost of the current fleet</h1>
  <div class="row">
    <div class="card"><span class="num" data-v="spend">0</span><span class="lab">Annual spend</span></div>
    <div class="card"><span class="num" data-v="hours">0</span><span class="lab">Hours lost</span></div>
  </div>
</div>""", """
let S;
function mount(root){
  S = H.scene.compare(H.$('[data-scene]', root), {
    options: [
      {label: 'Today', values: {spend: 4200000, hours: 12500}},
      {label: 'After the rollout', values: {spend: 2800000, hours: 4300}},
      {label: 'At full scale', values: {spend: 1900000, hours: 1200}}
    ],
    captions: ['What the fleet costs now', 'After the first wave', 'At full scale']
  });
}
function go(root, step){ if (S) S.go(step); }
""", ".wrap{display:flex;flex-direction:column;gap:22px}.row{display:flex;gap:22px}"
     ".card{border:1.5px solid var(--rule);border-radius:14px;padding:22px;flex:1}"
     ".num{display:block;font-family:var(--mono);font-size:60px;font-weight:700}"
     ".lab{font-size:15px;color:var(--mute)}.title{font-size:50px;font-weight:800}")


def test_a_compare_scene_renders_clean(tmp_path):
    rep = _report(tmp_path, COMPARE)
    assert not [f for f in rep.findings if f.severity == "error"], rep.findings
    assert rep.steps == 2


# ---------------------------------------------------------------- calculator
CALC = _spec(2, """
<div class="wrap" data-scene>
  <h1 class="title">What downtime costs you</h1>
  <div class="card"><span class="num" data-v="cost">0</span><span class="lab">Per year</span></div>
</div>""", """
let S;
function mount(root){
  S = H.scene.calculator(H.$('[data-scene]', root), {
    inputs: [
      {key: 'seats', label: 'Seats', min: 100, max: 5000, step: 100, value: 1200},
      {key: 'hours', label: 'Hours lost', min: 1, max: 40, step: 1, value: 12}
    ],
    compute: v => ({cost: v.seats * v.hours * 85}),
    presets: [{label: 'Mid', set: {seats: 2500}}, {label: 'Large', set: {seats: 5000, hours: 20}}],
    captions: ['Your fleet today', 'A mid-size estate', 'At enterprise scale']
  });
}
function go(root, step){ if (S) S.go(step); }
""", ".wrap{display:flex;flex-direction:column;gap:22px}"
     ".card{border:1.5px solid var(--rule);border-radius:14px;padding:22px}"
     ".num{display:block;font-family:var(--mono);font-size:60px;font-weight:700}"
     ".lab{font-size:15px;color:var(--mute)}.title{font-size:50px;font-weight:800}")


def test_a_calculator_scene_renders_clean(tmp_path):
    rep = _report(tmp_path, CALC)
    assert not [f for f in rep.findings if f.severity == "error"], rep.findings


# ---------------------------------------------------------------- explorer
EXPLORER = _spec(3, """
<div class="wrap" data-scene>
  <h1 class="title">Three ways the fleet leaks time</h1>
  <div class="row">
    <button class="card" data-item data-title="Patching" data-body="Nine hours a month per device.">Patching</button>
    <button class="card" data-item data-title="Imaging" data-body="Four hours per new starter.">Imaging</button>
    <button class="card" data-item data-title="Recovery" data-body="Two full days per incident.">Recovery</button>
  </div>
  <div class="panel" data-panel><b data-panel-title></b><p data-panel-body></p></div>
</div>""", """
let S;
function mount(root){
  S = H.scene.explorer(H.$('[data-scene]', root), {
    captions: ['Pick one to see the cost', 'Patching', 'Imaging', 'Recovery']
  });
}
function go(root, step){ if (S) S.go(step); }
""", ".wrap{display:flex;flex-direction:column;gap:22px}.row{display:flex;gap:22px}"
     ".card{border:1.5px solid var(--rule);border-radius:14px;padding:22px;flex:1;font-size:22px}"
     ".panel{border:1.5px solid var(--rule);border-radius:14px;padding:22px;min-height:90px}"
     ".title{font-size:50px;font-weight:800}")


def test_an_explorer_scene_renders_clean(tmp_path):
    rep = _report(tmp_path, EXPLORER)
    assert not [f for f in rep.findings if f.severity == "error"], rep.findings


# ---------------------------------------------------------------- timeline
TIMELINE = _spec(3, """
<div class="wrap" data-scene>
  <h1 class="title">The rollout, quarter by quarter</h1>
  <div class="row">
    <div class="card" data-stage="Q1">Q1 — pilot, 200 seats</div>
    <div class="card" data-stage="Q2">Q2 — first wave, 1,200 seats</div>
    <div class="card" data-stage="Q3">Q3 — second wave, 3,400 seats</div>
    <div class="card" data-stage="Q4">Q4 — complete, 5,000 seats</div>
  </div>
</div>""", """
let S;
function mount(root){
  S = H.scene.timeline(H.$('[data-scene]', root), {
    captions: ['The pilot', 'First wave', 'Second wave', 'Complete']
  });
}
function go(root, step){ if (S) S.go(step); }
""", ".wrap{display:flex;flex-direction:column;gap:22px}.row{display:flex;gap:22px}"
     ".card{border:1.5px solid var(--rule);border-radius:14px;padding:22px;flex:1;font-size:17px;opacity:.45}"
     ".card.in{opacity:1}.card.now{border-color:var(--blue)}.title{font-size:50px;font-weight:800}")


def test_a_timeline_scene_renders_clean(tmp_path):
    rep = _report(tmp_path, TIMELINE)
    assert not [f for f in rep.findings if f.severity == "error"], rep.findings


# ---------------------------------------------------------------- the contract
ALL = {"compare": COMPARE, "calculator": CALC, "explorer": EXPLORER, "timeline": TIMELINE}


@pytest.mark.parametrize("name", sorted(ALL))
def test_every_step_of_every_scene_is_clean(name, tmp_path):
    """check_spec walks every step, not only the last — a scene that breaks halfway is caught here."""
    rep = _report(tmp_path, ALL[name])
    errors = [f for f in rep.findings if f.severity == "error"]
    assert not errors, f"{name}: {errors}"


@pytest.mark.parametrize("name", sorted(ALL))
def test_a_scene_carries_a_real_control(name, tmp_path):
    """The point of the cinematic variant. A scene with no control is a reveal with extra steps."""
    html = ALL[name]
    rep = _report(tmp_path, html)
    assert rep.text, "the slide rendered nothing"
    assert not _codes(rep) & {"render", "no-slide", "script-error"}, _codes(rep)


def test_the_catalogue_is_documented_and_exported():
    """A scene the skill names but the runtime lacks fails silently at generation time."""
    import re

    from app.skillpack import read
    lib = (RUNTIME_DIR / "lib.js").read_text(encoding="utf-8")
    exported = set(re.findall(r"return \{ (build, compare, calculator, chartFocus, explorer, timeline) \}", lib))
    assert exported, "H.scene export not found in runtime/lib.js"
    names = {n.strip() for n in next(iter(exported)).split(",")}
    skill = read("HP_DECK_SKILL.md")
    for n in names:
        assert f"H.scene.{n}" in skill, f"H.scene.{n} is exported but undocumented"
    for n in re.findall(r"H\.scene\.(\w+)", skill):
        assert n in names, f"H.scene.{n} is documented but not exported"
    # The variant brief has to name the same catalogue, or the planner picks scenes that do not exist.
    variants = read("variants.md")
    for n in names:
        assert n in variants, f"{n} is missing from the variant A brief"


def test_the_planner_is_told_to_name_a_scene():
    from app.skillpack import read
    plan = read("deck_plan.md")
    assert "Name the scene" in plan
    for n in ("compare", "calculator", "chartFocus", "explorer", "timeline", "build"):
        assert n in plan, n


def test_the_scene_chrome_is_styled():
    """Scenes build their own controls, so base.css must carry their classes or they render unstyled."""
    css = (RUNTIME_DIR / "base.css").read_text(encoding="utf-8")
    for cls in (".scene-cap", ".seg-b", ".calc-rows", ".calc-row", ".focus-legend", ".focus-b",
                ".tl-bar", ".tl-dot", "[data-item]", "[data-panel]"):
        assert cls in css, f"{cls} is built by H.scene but not styled in base.css"


def test_json_meta_is_still_parseable():
    """Guards the helper above, not the runtime: a malformed spec would make every test here vacuous."""
    meta = COMPARE.split("<meta>")[1].split("</meta>")[0]
    assert json.loads(meta)["steps"] == 2
