"""runtime/edit.js — the in-slide half of the direct-manipulation editor.

It had no test coverage at all, and it is the piece a user touches most directly: it decides what can be
selected, what can be resized, and what op the builder is asked to persist. Every gesture it offers must
be one `backend/app/edit.py` will accept — a control that always 400s is worse than no control — so the
assertions here are about the *op that comes out*, run against a real deck in a real browser.

These drive Chromium through Playwright directly rather than through check_spec, because what is under
test is an interaction, not a render.
"""
import asyncio
import json
import sys
import threading

import pytest
from app.assemble import DeckInput, DeckSlide, assemble
from app.config import RUNTIME_DIR
from app.edit import EditError, check_style, ensure_ids
from app.spec import parse_spec

ASSETS = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}

SPEC = """<meta>{"steps":0,"notes":["n"],"sources":""}</meta>
<html>
<h1 class="title">Three ways the fleet leaks time</h1>
<div class="row">
  <div class="card" data-k="a"><b>Patching</b><p>Nine hours a month.</p></div>
  <div class="card" data-k="b"><b>Imaging</b><p>Four hours per starter.</p></div>
  <div class="card" data-k="c"><b>Recovery</b><p>Two days per incident.</p></div>
</div>
</html>
<css>
.row{display:flex;gap:22px;margin-top:26px}
.card{flex:1;border:1.5px solid var(--rule);border-radius:14px;padding:22px}
.title{font-size:50px;font-weight:800}
</css>
<script></script>"""


# ---------------------------------------------------------------- harness
# One browser and one event loop for the whole module, on a dedicated thread. Not an optimisation:
# calling asyncio.run() once per test and launching Chromium each time deadlocks on Windows after a
# handful of rounds. app/qa/render_check.py runs its renderer exactly this way for the same reason.
class _Browser:
    def __init__(self):
        self.loop = None
        self.browser = None
        self._pw = None
        self._ready = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        assert self._ready.wait(90), "Chromium did not start"

    def _run(self):
        self.loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._launch())
        self._ready.set()
        self.loop.run_forever()

    async def _launch(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(120)

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)


BROWSER = _Browser()


@pytest.fixture(scope="module", autouse=True)
def _browser():
    BROWSER.start()
    yield
    BROWSER.stop()


class Deck:
    """One assembled deck in an iframe, with edit mode on and the ops it posts up collected."""

    def __init__(self, tmp_path, spec_text=SPEC):
        spec, _ = parse_spec(spec_text, "e1")
        # The builder stamps ids before it ever turns edit mode on; the runtime addresses elements by them.
        self.spec = ensure_ids(spec)
        self.path = tmp_path / "deck.html"
        self.path.write_text(
            assemble(DeckInput(title="Edit", slides=[DeckSlide(id="e1", spec=self.spec)], assets=ASSETS)),
            encoding="utf-8")
        self.host = tmp_path / "host.html"
        self.host.write_text(
            "<!doctype html><meta charset=utf-8><style>html,body{margin:0}iframe{width:1600px;height:900px;border:0}</style>"
            "<script>window.__ops=[];addEventListener('message',e=>{if(e.data&&e.data.type==='hpdeck')window.__ops.push(e.data)});"
            "function toDeck(m){document.querySelector('iframe').contentWindow.postMessage(m,'*')}</script>"
            f"<iframe src='{self.path.name}'></iframe>", encoding="utf-8")

    def run(self, body: str):
        """Run `body` inside the deck frame, then return {result, ops} with what it posted to its parent.

        A real iframe, because that is the only honest harness: edit.js posts to `window.parent` and
        deliberately does nothing when there is no parent, so faking one would test a path the builder
        never uses. A `file://` frame is a separate origin, so the two halves cannot read each other's
        DOM — hence the split. The gesture runs in the frame; the parent only collects messages, which
        is exactly the arrangement the real builder has.
        """
        async def go():
            ctx = await BROWSER.browser.new_context(viewport={"width": 1610, "height": 940})
            try:
                page = await ctx.new_page()
                await page.goto(self.host.as_uri())
                await page.wait_for_function("document.querySelector('iframe')")
                # not `endswith`: the shell appends a #slide hash as soon as it mounts.
                frame = next(f for f in page.frames if f is not page.main_frame and self.path.name in f.url)
                await frame.wait_for_function("window.DECK && DECK.slides.length")
                await page.evaluate("toDeck({type:'hpdeck', cmd:'edit', on:true})")
                await page.wait_for_timeout(120)
                result = await frame.evaluate(body)
                await page.wait_for_timeout(80)
                return {"result": result, "ops": await page.evaluate("window.__ops")}
            finally:
                await ctx.close()

        return BROWSER.submit(go())

    def select(self, eid: str, body: str = "() => null"):
        """Select `eid` the way the builder does, then evaluate `body` in the frame."""
        return self.run(f"""() => {{
            window.dispatchEvent(new MessageEvent('message', {{data:{{type:'hpdeck', cmd:'select', eid:{json.dumps(eid)}}}}}));
            return new Promise(r => setTimeout(() => r((({body}))()), 120));
        }}""")


def _eid_of(spec, selector_class: str) -> str:
    import re
    m = re.search(rf'class="[^"]*{selector_class}[^"]*"[^>]*data-eid="([^"]+)"', spec.html)
    if not m:
        m = re.search(rf'data-eid="([^"]+)"[^>]*class="[^"]*{selector_class}', spec.html)
    assert m, f"no data-eid on .{selector_class} in {spec.html[:400]}"
    return m.group(1)


# ---------------------------------------------------------------- selection
def test_edit_mode_reports_a_selection_with_the_flags_the_toolbar_needs(tmp_path):
    d = Deck(tmp_path)
    eid = _eid_of(d.spec, "title")
    got = [o for o in d.select(eid)["ops"] if o["event"] == "edit-select"]
    assert got, "selecting an element must report it back to the builder"
    sel = got[-1]
    assert sel["eid"] == eid and sel["tag"] == "h1"
    assert sel["canText"] is True, "a leaf heading is editable text"
    assert "rect" in sel and sel["rect"]["w"] > 0


def test_a_container_with_children_is_not_offered_text_editing(tmp_path):
    """edit.py raises `has-children` for that, so offering it would always 400."""
    d = Deck(tmp_path)
    eid = _eid_of(d.spec, "card")
    got = [o for o in d.select(eid)["ops"] if o["event"] == "edit-select"]
    assert got[-1]["canText"] is False


# ---------------------------------------------------------------- resize
DRAG = """() => {
    const el = DECK.slides[0].root.querySelector('[data-eid=%s]');
    const h = document.querySelector('#hp-edit .h-%s');
    if (!h || h.style.display === 'none') return {error:'no handle', display: h && h.style.display};
    const r = h.getBoundingClientRect();
    const x = r.left + 5, y = r.top + 5;
    const at = (n, b) => new PointerEvent(n, {bubbles:true, clientX:b.x, clientY:b.y, button:0, pointerId:1});
    h.dispatchEvent(at('pointerdown', {x, y}));
    window.dispatchEvent(at('pointermove', {x:x + %d, y:y + %d}));
    window.dispatchEvent(at('pointerup', {x:x + %d, y:y + %d}));
    return {width: el.style.width, height: el.style.height};
}"""


def _drag(tmp_path, cls, dir_, dx, dy):
    d = Deck(tmp_path)
    eid = _eid_of(d.spec, cls)
    out = d.select(eid, DRAG % (json.dumps(eid), dir_, dx, dy, dx, dy))
    return {**(out["result"] or {}), "ops": [o for o in out["ops"] if o["event"] == "edit-op"]}


def test_dragging_the_east_handle_emits_a_width_change(tmp_path):
    out = _drag(tmp_path, "card", "e", 120, 0)
    assert "error" not in out, out
    ops = [o["op"] for o in out["ops"] if o["op"]["op"] == "set_style"]
    assert ops, f"a resize must emit set_style, got {out}"
    style = ops[-1]["style"]
    assert "width" in style and style["width"].endswith("px")
    assert "height" not in style, "an east drag changes width only"


def test_a_flex_child_also_gets_flex_basis(tmp_path):
    """`.card` is `flex:1`, so a sibling eats the space and width alone looks like it did nothing."""
    out = _drag(tmp_path, "card", "e", 120, 0)
    style = [o["op"] for o in out["ops"] if o["op"]["op"] == "set_style"][-1]["style"]
    assert style.get("flex-basis") == style["width"]


def test_dragging_a_corner_changes_both_axes(tmp_path):
    out = _drag(tmp_path, "card", "se", 80, 60)
    style = [o["op"] for o in out["ops"] if o["op"]["op"] == "set_style"][-1]["style"]
    assert "width" in style and "height" in style


def test_a_resize_is_measured_in_stage_pixels_not_screen_pixels(tmp_path):
    """The 1600x900 stage is transform-scaled to the viewport, so a screen delta is the wrong number.
    At a 1600px viewport the scale is ~1, so the committed width must be close to the drag distance."""
    out = _drag(tmp_path, "card", "e", 100, 0)
    style = [o["op"] for o in out["ops"] if o["op"]["op"] == "set_style"][-1]["style"]
    width = int(style["width"].removesuffix("px"))
    # three cards, 22px gaps, 1448px content box -> ~468px each; +100 stage px
    assert 520 < width < 620, f"{width}px is not a stage-pixel measurement"


def test_every_style_a_resize_emits_is_one_the_server_accepts(tmp_path):
    """The rule for the whole editor: never offer a gesture that always 400s."""
    out = _drag(tmp_path, "card", "se", 90, 70)
    for op in (o["op"] for o in out["ops"] if o["op"]["op"] == "set_style"):
        for prop, value in op["style"].items():
            assert check_style(prop, value) in ("layout", "cosmetic"), f"{prop}: {value}"


def test_the_handles_are_hidden_when_nothing_is_selected(tmp_path):
    d = Deck(tmp_path)
    shown = d.run("""() => {
        const hs = Array.from(document.querySelectorAll('#hp-edit .hnd'));
        return {count: hs.length, visible: hs.filter(h => h.style.display === 'block').length};
    }""")["result"]
    assert shown["count"] == 8, "eight handles, one per direction"
    assert shown["visible"] == 0


# ---------------------------------------------------------------- the allowlist behind it
@pytest.mark.parametrize("prop, value", [
    ("width", "480px"), ("height", "260px"), ("flex-basis", "480px"),
    ("grid-template-columns", "repeat(3, 1fr)"), ("grid-template-columns", "1fr 2fr"),
    ("flex-direction", "column"), ("gap", "22px"), ("padding", "22px"), ("align-items", "center"),
])
def test_the_layout_panel_only_offers_what_the_server_takes(prop, value):
    assert check_style(prop, value) == "layout"


@pytest.mark.parametrize("prop, value", [
    ("position", "absolute"), ("transform", "translate(10px, 4px)"), ("inset", "0"),
    ("z-index", "5"), ("float", "left"),
])
def test_taking_an_element_out_of_the_flow_is_still_refused(prop, value):
    """Resizing works *with* the 1600x900 flow the slide's CSS was written against. Free positioning
    would break that, so it stays refused and the drag writes sizes rather than coordinates."""
    with pytest.raises(EditError):
        check_style(prop, value)


# ---------------------------------------------------------------- resizing a picture
# Tester feedback: "the stack image was too small and we couldn't make it bigger". `.figure img` is capped at
# 80% of its frame and at its natural size, so a drag that only wrote width/height did nothing past the cap.
IMG_SPEC = """<meta>{"steps":0,"notes":["n"],"sources":""}</meta>
<html>
<h1 class="title">Our stack</h1>
<figure class="figure" style="width:700px;height:420px"><img class="pic" src="asset:hp" alt="stack" style="width:200px"></figure>
</html>
<css></css>
<script></script>"""


def test_dragging_a_picture_lifts_the_figure_cap_and_keeps_its_ratio(tmp_path):
    d = Deck(tmp_path, IMG_SPEC)
    eid = _eid_of(d.spec, "pic")
    out = d.select(eid, DRAG % (json.dumps(eid), "se", 500, 20, 500, 20))
    assert "error" not in (out["result"] or {}), out
    style = [o["op"] for o in out["ops"] if o.get("event") == "edit-op" and o["op"]["op"] == "set_style"][-1]["style"]
    assert int(style["width"].removesuffix("px")) > 650, "grew past 80% of a 700px frame"
    assert style["height"] == "auto", "a picture keeps its proportions; the height follows the width"
    assert style["max-width"] == "none" and style["max-height"] == "none"
    for prop, value in style.items():
        assert check_style(prop, value) in ("layout", "cosmetic"), f"{prop}: {value}"


def test_dragging_a_picture_from_the_bottom_edge_still_resizes_it(tmp_path):
    d = Deck(tmp_path, IMG_SPEC)
    eid = _eid_of(d.spec, "pic")
    out = d.select(eid, DRAG % (json.dumps(eid), "s", 0, 120, 0, 120))
    style = [o["op"] for o in out["ops"] if o.get("event") == "edit-op" and o["op"]["op"] == "set_style"][-1]["style"]
    assert "width" in style and style["height"] == "auto"
