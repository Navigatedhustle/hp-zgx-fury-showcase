"""Precise layout: near-miss alignment, uneven gaps, ragged cards, content in the margin, title drift.
Every gold example stays free of these errors (test_render_and_pipeline::test_gold_examples_render_without_errors)."""
import asyncio

from app.config import RUNTIME_DIR
from app.qa.render_check import check_spec
from app.spec import parse_spec

ASSETS = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}


def _codes(tmp_path, html: str, css: str = "") -> dict[str, str]:
    raw = f'<meta>{{"pattern":"cards","title":"T","steps":0,"notes":["n"]}}</meta><html>{html}</html><css>{css}</css><script></script>'
    spec, _ = parse_spec(raw, "l")
    rep = asyncio.run(check_spec(spec, "l", ASSETS, tmp_path))
    return {f.code: f.severity for f in rep.findings}


ROW = ('<h1 class="title">Three ways the fleet leaks time</h1><div class="row">'
       '<div class="card a"><b>Patching</b><p>Nine hours a month.</p></div>'
       '<div class="card b"><b>Imaging</b><p>Four hours per starter.</p></div>'
       '<div class="card c"><b>Recovery</b><p>Two days per incident.</p></div></div>')
BASE = ".row{display:flex;gap:22px;margin-top:26px;align-items:flex-start}.card{flex:1;height:200px}"


def test_a_clean_row_passes(tmp_path):
    got = _codes(tmp_path, ROW, BASE)
    assert not {"misaligned", "uneven-gap", "ragged", "margin", "title-drift"} & set(got), got


def test_a_card_a_few_pixels_low_is_an_error(tmp_path):
    got = _codes(tmp_path, ROW, BASE + ".b{margin-top:3px}")
    assert got.get("misaligned") == "error"


def test_a_deliberate_offset_is_not_flagged(tmp_path):
    got = _codes(tmp_path, ROW, BASE + ".b{margin-top:40px}")
    assert "misaligned" not in got


def test_uneven_gaps_are_a_warning(tmp_path):
    got = _codes(tmp_path, ROW, BASE + ".b{margin-right:18px}")
    assert got.get("uneven-gap") == "warn"


def test_ragged_cards_are_a_warning(tmp_path):
    got = _codes(tmp_path, ROW, ".row{display:flex;gap:22px;align-items:flex-start}.card{flex:1}.a{height:120px}.b{height:220px}")
    assert got.get("ragged") == "warn"


def test_content_in_the_margin_is_an_error(tmp_path):
    got = _codes(tmp_path, ROW + '<p class="spill">A footnote pushed into the margin</p>',
                 BASE + ".spill{margin-left:-40px}")
    assert got.get("margin") == "error"


def test_a_corner_logo_placed_on_purpose_is_allowed(tmp_path):
    got = _codes(tmp_path, ROW + '<img class="corner" src="asset:hp" alt="HP">',
                 BASE + ".corner{position:absolute;left:20px;top:20px;width:60px}")
    assert "margin" not in got


def test_a_drifting_title_is_a_warning(tmp_path):
    got = _codes(tmp_path, ROW, BASE + ".title{margin-left:6px}")
    assert got.get("title-drift") == "warn"
