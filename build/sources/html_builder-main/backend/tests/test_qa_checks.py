"""The deeper QA checks: every step is inspected, not just the last one; contrast is measured against the
pixels actually behind the text; repairs are compared visually; a curated accessibility pass runs.

These render in headless Chromium, so they live next to test_render_and_pipeline rather than the fast tests.
"""
import asyncio
import tempfile
from pathlib import Path

from conftest import ROOT
from PIL import Image, ImageDraw

from app.config import RUNTIME_DIR
from app.qa.pixels import image_diff, measure_contrast
from app.qa.render_check import check_spec
from app.skillpack import examples
from app.spec import parse_spec

ASSETS = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}

# Codes this module added on top of the checks that already existed.
NEW_CODES = {"contrast-image", "a11y-image-alt", "a11y-button-name", "a11y-aria-valid-attr",
             "a11y-aria-valid-attr-value", "a11y-aria-required-attr", "a11y-duplicate-id"}


def _check(spec_text: str, out_dir, slide_id: str = "t", assets: dict | None = None, prev_dir=None):
    spec, _ = parse_spec(spec_text, slide_id)
    return asyncio.run(check_spec(spec, slide_id, ASSETS if assets is None else assets, out_dir, prev_dir=prev_dir))


def _codes(rep) -> set[str]:
    return {f.code for f in rep.findings}


# ---------------------------------------------------------------- 1. every step is checked
# The regression test for the bug this module exists to fix: the DOM check used to run only after the last
# goto, so a cinematic variant could overlap, clip or overflow halfway through and reach a human unnoticed.
STEP_TRAP = """<meta>{"steps":3,"notes":["n"]}</meta>
<html><div class="a">Alpha statement here</div><div class="b">Beta statement here</div></html>
<css>
.a,.b{position:absolute;top:320px;width:440px;font-size:42px;font-weight:700;color:#111;background:#fff}
.a{left:100px}
.b{left:1000px}
</css>
<script>
function go(r, step){
  r.querySelector('.b').style.left = (step === 2) ? '100px' : '1000px';
}
</script>"""


def test_a_slide_broken_only_at_an_intermediate_step_is_caught(tmp_path):
    rep = _check(STEP_TRAP, tmp_path)
    overlaps = [f for f in rep.findings if f.code == "overlap"]
    assert overlaps, [f"{f.code}: {f.message}" for f in rep.findings]
    assert overlaps[0].severity == "error"
    # the step is on the finding and spelled out in the message, so a repair prompt can name it
    assert overlaps[0].step == 2
    assert "step 2 of 3" in overlaps[0].message
    # and it really is invisible at the end: the final state of this slide is clean
    assert not [f for f in rep.findings if f.step == rep.steps and f.severity == "error"]


def test_the_final_step_still_supplies_the_text_and_the_screenshots(tmp_path):
    rep = _check(STEP_TRAP, tmp_path)
    assert rep.steps == 3
    assert rep.shots == ["shot_0.png", "shot_final.png"]
    assert (tmp_path / "shot_0.png").exists() and (tmp_path / "shot_final.png").exists()
    assert "Alpha statement here" in rep.text and "Beta statement here" in rep.text
    # findings from the final step are not annotated with a step number in their message
    for f in rep.findings:
        if f.step == rep.steps:
            assert "seen at step" not in f.message


def test_a_slide_with_no_steps_is_checked_once_and_keeps_one_screenshot(tmp_path):
    rep = _check('<meta>{"steps":0}</meta><html><h1 class="title">One shot</h1></html><css></css><script></script>',
                 tmp_path)
    assert rep.steps == 0 and rep.shots == ["shot_final.png"]
    assert not (tmp_path / "shot_0.png").exists()
    assert all(f.step is None for f in rep.findings)
    assert not rep.errors


# ---------------------------------------------------------------- 2. contrast against real pixels
def _split_photo(path, dark: int = 28, light: int = 226) -> None:
    """A deliberately two-faced backdrop: dark on the left, bright on the right, with enough noise to be a
    photograph rather than a flat fill. Mean luminance is mid-grey, so a check that averaged the region
    would pass white text on it — only the worst part of the region tells the truth."""
    img = Image.new("RGB", (1600, 900))
    px = img.load()
    seed = 12345
    for y in range(900):
        for x in range(0, 1600, 8):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            n = (seed >> 16) % 24 - 12
            v = max(0, min(255, (dark if x < 800 else light) + n))
            for dx in range(8):
                px[x + dx, y] = (v, v, v)
    img.save(path)


HERO = """<meta>{"steps":0,"theme":"dark","bleed":true}</meta>
<html><img class="bg-img" src="asset:photo" alt="test backdrop">%s
<div class="on-top center fill"><div class="hero">Readable over anything at all</div></div></html>
<css>.hero{font-size:64px;font-weight:800;color:#fff;letter-spacing:-.02em}</css>
<script></script>"""

SCRIM = '<div class="bg-shade"></div>'


def test_light_text_on_a_photo_fails_and_the_same_text_over_a_scrim_passes(tmp_path):
    photo = tmp_path / "photo.png"
    _split_photo(photo)
    assets = dict(ASSETS, photo=photo)

    bare = _check(HERO % "", tmp_path / "bare", slide_id="bare", assets=assets)
    assert "contrast-image" in _codes(bare), [f"{f.code}: {f.message}" for f in bare.findings]
    assert "Readable over anything" in next(f for f in bare.findings if f.code == "contrast-image").message

    scrimmed = _check(HERO % SCRIM, tmp_path / "scrim", slide_id="scrim", assets=assets)
    assert "contrast-image" not in _codes(scrimmed), [f"{f.code}: {f.message}" for f in scrimmed.findings]
    assert not scrimmed.errors


def test_the_worst_region_decides_not_the_mean():
    """White text across the split photo: averaged it is a comfortable pass, judged on its worst region it
    is not. The sampler must report the second number."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "split.png"
        _split_photo(p)
        wide = measure_contrast(p, [{"x": 200, "y": 400, "w": 1200, "h": 80, "color": [255, 255, 255], "size": 64,
                                     "label": "white band"}])
        dark_only = measure_contrast(p, [{"x": 100, "y": 400, "w": 500, "h": 80, "color": [255, 255, 255], "size": 64,
                                          "label": "white band"}])
    assert wide and dark_only
    assert wide[0]["ratio"] < 1.6          # the bright half defeats the text
    assert dark_only[0]["ratio"] > 8.0     # the same text on the dark half is fine


def test_text_on_a_coloured_panel_over_a_photo_is_judged_against_the_panel(tmp_path):
    """The false-positive guard: an opaque panel between the text and the photo is what the text sits on."""
    photo = tmp_path / "photo.png"
    _split_photo(photo)
    spec = ("""<meta>{"steps":0,"bleed":true}</meta>
<html><img class="bg-img" src="asset:photo" alt="backdrop">
<div class="panel">Dark ink on a solid white panel</div></html>
<css>.panel{position:absolute;left:200px;top:360px;width:1200px;padding:40px;background:#fff;color:#111;
font-size:48px;font-weight:700}</css>
<script></script>""")
    rep = _check(spec, tmp_path / "panel", slide_id="panel", assets=dict(ASSETS, photo=photo))
    assert "contrast-image" not in _codes(rep) and "contrast" not in _codes(rep), \
        [f"{f.code}: {f.message}" for f in rep.findings]


# ---------------------------------------------------------------- 3. visual diff between iterations
def _canvas(path, *, box=None, noise: int = 0) -> None:
    img = Image.new("RGB", (1600, 900), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([120, 120, 700, 500], fill=(0, 100, 160))
    if box:
        d.rectangle(box, fill=(200, 30, 60))
    if noise:
        for i in range(400):  # a scatter of single pixels: real bytes change, nothing structural moves
            d.point(((i * 37) % 1600, (i * 53) % 900), fill=(250 - noise, 250, 250))
    img.save(path)


def test_image_diff_separates_a_real_change_from_a_no_op_repair(tmp_path):
    a, same, jitter, moved = (tmp_path / n for n in ("a.png", "same.png", "jitter.png", "moved.png"))
    _canvas(a, box=[900, 200, 1200, 400])
    _canvas(same, box=[900, 200, 1200, 400])
    _canvas(jitter, box=[900, 200, 1200, 400], noise=9)
    _canvas(moved, box=[900, 500, 1200, 700])

    identical = image_diff(a, same)
    assert identical.identical and identical.changed_ratio == 0 and identical.changed_blocks == 0

    noop = image_diff(a, jitter)
    assert not noop.identical          # the bytes differ, so md5 alone would call this a change
    assert noop.changed_blocks < 0.01  # structurally it is the same slide

    real = image_diff(a, moved)
    assert real.changed_blocks > 0.05 and real.changed_ratio > 0.02
    assert real.mean_abs_diff > noop.mean_abs_diff * 10
    assert real.max_abs_diff > 50

    assert image_diff(tmp_path / "missing.png", a) is None


def test_check_spec_reports_the_diff_against_the_previous_iteration(tmp_path):
    slide = '<meta>{"steps":0}</meta><html><h1 class="title">%s</h1></html><css></css><script></script>'
    first = _check(slide % "Original wording", tmp_path / "iter0")
    assert first.diff is None  # nothing to compare against

    again = _check(slide % "Original wording", tmp_path / "iter1", prev_dir=tmp_path / "iter0")
    assert again.diff is not None and again.diff.shot == "shot_final.png"
    assert again.diff.changed_blocks == 0  # a repair that changed nothing

    changed = _check(slide % "Completely different wording on the slide", tmp_path / "iter2",
                     prev_dir=tmp_path / "iter1")
    assert changed.diff.changed_blocks > again.diff.changed_blocks
    assert changed.diff.mean_abs_diff > 0


def test_steps_that_barely_move_are_flagged_even_when_the_bytes_differ(tmp_path):
    spec = """<meta>{"steps":2}</meta>
<html><h1 class="title">A slide that claims to animate</h1><div class="dot"></div></html>
<css>.dot{position:absolute;left:40px;top:820px;width:8px;height:8px;background:#0096D6}</css>
<script>function go(r, step){ r.querySelector('.dot').style.left = (40 + step) + 'px'; }</script>"""
    rep = _check(spec, tmp_path)
    steps = [f for f in rep.findings if f.code == "steps"]
    assert steps and "all but identical" in steps[0].message, [f.message for f in rep.findings]


# ---------------------------------------------------------------- 4. accessibility
A11Y_TRAP = """<meta>{"steps":0}</meta>
<html>
<h1 class="title">Accessibility trap</h1>
<img src="asset:nano" width="120">
<button class="btn" id="dup"></button>
<div id="dup">second use of the same id</div>
<div role="checkbox" tabindex="0">A checkbox with no state</div>
<div aria-lable="typo in the attribute name">Mislabelled</div>
<div aria-expanded="yes" aria-describedby="nowhere">Bad values</div>
</html>
<css>.btn{width:40px;height:40px}</css>
<script></script>"""


def test_the_accessibility_pass_flags_the_curated_rules(tmp_path):
    rep = _check(A11Y_TRAP, tmp_path)
    codes = _codes(rep)
    assert {"a11y-image-alt", "a11y-button-name", "a11y-duplicate-id", "a11y-aria-valid-attr",
            "a11y-aria-valid-attr-value", "a11y-aria-required-attr"} <= codes, sorted(codes)
    # a floor, never a blocker: automated a11y coverage is a fraction of the real thing
    assert all(f.severity == "warn" for f in rep.findings if f.code.startswith("a11y-"))
    assert not [f for f in rep.errors if f.code.startswith("a11y-")]


def test_decorative_and_labelled_markup_does_not_trip_the_accessibility_pass(tmp_path):
    ok = """<meta>{"steps":0}</meta>
<html>
<h1 class="title">Everything declared</h1>
<img src="asset:nano" alt="">
<img src="asset:fury" alt="HP ZGX Fury tower">
<button class="btn" aria-label="Next">&gt;</button>
<button class="btn">Visible label</button>
<div id="legend">Legend</div>
<div role="checkbox" aria-checked="false" aria-labelledby="legend">Opted out</div>
</html>
<css></css>
<script></script>"""
    rep = _check(ok, tmp_path)
    assert not [f for f in rep.findings if f.code.startswith("a11y-")], [f.message for f in rep.findings]


# ---------------------------------------------------------------- 5. the calibration set stays clean
def test_gold_examples_stay_clean_under_every_new_check(tmp_path):
    """The gold specs are the tuning set for all of the above: per-step checks, pixel contrast, the
    accessibility rules and the structural `steps` comparison must all stay silent on them."""
    async def run():
        out = []
        for i, ex in enumerate(examples()):
            spec, _ = parse_spec(ex.output, f"g{i}")
            out.append((ex.name, await check_spec(spec, f"g{i}", ASSETS, tmp_path / str(i))))
        return out

    for name, rep in asyncio.run(run()):
        assert not rep.errors, (name, [e.message for e in rep.errors])
        offenders = [f.message for f in rep.findings if f.code in NEW_CODES or f.code == "steps"]
        assert not offenders, (name, offenders)


def test_the_qa_module_has_no_dead_exports():
    """spec.unscope_css and ParsedDeck.slide_width/height were set and never read; they are gone."""
    from app import spec as spec_mod
    from app.ingest.pptx_parse import ParsedDeck

    assert not hasattr(spec_mod, "unscope_css")
    assert "slide_width" not in ParsedDeck.model_fields and "slide_height" not in ParsedDeck.model_fields
    assert not (ROOT / "backend" / "app" / "qa" / "vendor").exists()  # axe-core is not vendored; see qa/a11y.py


# ---------------------------------------------------------------- browser fallback
class _FakeChromium:
    """Playwright's `chromium` with only some channels installed."""

    def __init__(self, installed):
        self.installed, self.tried = installed, []

    async def launch(self, args=None, channel=None):
        self.tried.append(channel)
        if channel not in self.installed:
            raise RuntimeError(f"Executable doesn't exist for {channel or 'bundled chromium'}")
        return f"browser:{channel}"


def test_a_blocked_chromium_download_falls_back_to_edge():
    """Corporate networks block Playwright's Chromium download; every Windows laptop has Edge."""
    import asyncio
    from app.qa import render_check as rc

    pw = type("PW", (), {"chromium": _FakeChromium({"msedge"})})()
    assert asyncio.run(rc._launch(pw)) == "browser:msedge"
    assert pw.chromium.tried == [None, "msedge"]


def test_the_bundled_chromium_is_preferred_and_a_total_failure_names_the_first_error():
    import asyncio
    import pytest
    from app.qa import render_check as rc

    pw = type("PW", (), {"chromium": _FakeChromium({None, "msedge"})})()
    assert asyncio.run(rc._launch(pw)) == "browser:None"
    pw = type("PW", (), {"chromium": _FakeChromium(set())})()
    with pytest.raises(RuntimeError, match="bundled chromium"):
        asyncio.run(rc._launch(pw))
