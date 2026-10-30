"""Charts on the finished slide are held to the source PowerPoint chart: rendered in Chromium, the data H.chart was
built from is read back and compared with what python-pptx read out of the source."""
import asyncio

import pytest

from app.config import RUNTIME_DIR
from app.qa.charts import chart_findings, family
from app.qa.render_check import check_spec
from app.spec import parse_spec

ASSETS = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}
SOURCE = [{"type": "column_clustered", "title": "Cloud GPU spend ($K)",
           "categories": ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"],
           "series": [{"name": "Spend", "values": [180, 220, 310, 420]}]}]


def _slide(js: str, steps: int = 1) -> str:
    return (f'<meta>{{"pattern":"chart","title":"Spend","steps":{steps},"notes":["n"]}}</meta>'
            '<html><h1 class="title">Cloud GPU spend is rising</h1><div class="plot"></div></html>'
            '<css>.plot{height:520px}</css>'
            f'<script>let c; function go(root, step){{ const p = root.querySelector(".plot"); {js} }}</script>')


def _render(tmp_path, js: str, steps: int = 1):
    spec, _ = parse_spec(_slide(js, steps), "c")
    rep = asyncio.run(check_spec(spec, "c", ASSETS, tmp_path))
    return rep, chart_findings(SOURCE, rep.charts, rep.unverified_charts, "chart")


EXACT = ('if (!c) c = H.chart.bars(p, {labels:["Q1 2025","Q2 2025","Q3 2025","Q4 2025"], values:[180,220,310,420]});'
         ' c.show(step >= 1 ? 4 : 0);')


def test_the_exact_source_data_passes(tmp_path):
    rep, found = _render(tmp_path, EXACT)
    assert rep.charts and rep.charts[0]["labels"][0] == "Q1 2025"
    assert found == [], [f.message for f in found]


def test_a_changed_value_is_fatal(tmp_path):
    _, found = _render(tmp_path, EXACT.replace("310", "350"))
    changed = [f for f in found if f.code == "chart-changed"]
    assert changed and changed[0].fatal and "Q3 2025" in changed[0].message


def test_honest_rescaling_is_accepted(tmp_path):
    js = EXACT.replace("[180,220,310,420]", "[0.18,0.22,0.31,0.42]")  # the same data in $M
    _, found = _render(tmp_path, js)
    assert not [f for f in found if f.code == "chart-changed"]


def test_a_dropped_category_forces_a_repair(tmp_path):
    js = ('if (!c) c = H.chart.bars(p, {labels:["Q1 2025","Q2 2025","Q3 2025"], values:[180,220,310]});'
          ' c.show(step >= 1 ? 3 : 0);')
    _, found = _render(tmp_path, js)
    assert any(f.code == "chart-missing" and f.severity == "error" and "Q4 2025" in f.message for f in found)


def test_a_different_chart_type_is_a_warning(tmp_path):
    js = ('if (!c) c = H.chart.line(p, {labels:["Q1 2025","Q2 2025","Q3 2025","Q4 2025"], values:[180,220,310,420]});'
          ' c.show(step >= 1 ? 1 : 0);')
    _, found = _render(tmp_path, js)
    assert [f.code for f in found] == ["chart-type"] and found[0].severity == "warn"


def test_a_clipped_axis_is_an_error(tmp_path):
    _, found = _render(tmp_path, EXACT.replace("values:[180,220,310,420]", "values:[180,220,310,420], max:300"))
    assert any(f.code == "chart-scale" for f in found)


def test_data_still_hidden_at_the_final_step_is_an_error(tmp_path):
    _, found = _render(tmp_path, EXACT.replace("c.show(step >= 1 ? 4 : 0)", "c.show(step >= 1 ? 2 : 0)"))
    assert any(f.code == "chart-hidden" for f in found)


def test_a_chart_the_audience_drives_is_not_held_to_the_source_values(tmp_path):
    _, found = _render(tmp_path, EXACT + " c.set([1,2,3,4]);")
    assert not [f for f in found if f.code == "chart-changed"]


def test_a_hand_drawn_chart_cannot_be_verified(tmp_path):
    bars = "".join(f'<rect x="{i * 60}" y="{300 - v}" width="40" height="{v}"/>' for i, v in enumerate([180, 220, 310, 420]))
    js = f'p.innerHTML = \'<svg width="400" height="320">{bars}</svg>\';'
    _, found = _render(tmp_path, js, steps=0)
    assert [f.code for f in found] == ["chart-unverified"]


def test_a_missing_chart_on_a_chart_slide_is_an_error():
    found = chart_findings(SOURCE, [], 0, "chart")
    assert found[0].code == "chart-missing" and found[0].severity == "error"


@pytest.mark.parametrize("t,fam", [("column_clustered", "bars"), ("bar_stacked", "stacked"), ("line_markers", "line"),
                                   ("pie", "part"), ("doughnut", "part"), ("groupedBars", "bars"), ("donut", "part")])
def test_chart_families(t, fam):
    assert family(t) == fam
