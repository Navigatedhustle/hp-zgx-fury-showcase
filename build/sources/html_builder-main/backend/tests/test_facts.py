"""The fact ledger.

Each test below names a way the previous bag-of-digits check let a fact through. The point of the
module is that a designed slide may say a fact any way it likes, and may not say a different one.
"""
import pytest
from app import facts as F


def _facts(**content):
    return F.extract(content)


def _raws(fs):
    return [f.raw for f in fs]


# ---------------------------------------------------------------- units are part of the fact
@pytest.mark.parametrize("text, value, unit", [
    ("Revenue grew to $4.2M last year", 4_200_000.0, "currency"),
    ("Adoption reached 40% of seats", 40.0, "percent"),
    ("3.5x faster than the previous generation", 3.5, "multiplier"),
    ("Ships with 2 TB of storage", 2e12, "bytes"),
    ("Renders in 45 seconds", 45.0, "duration"),
    ("12,500 workstations deployed", 12500.0, "plain"),
    ("Cut to 90 minutes", 5400.0, "duration"),
])
def test_a_number_carries_its_unit_and_scale(text, value, unit):
    n = F.parse_numbers(text)
    assert n and n[0].value == pytest.approx(value) and n[0].unit == unit


def test_the_same_digits_with_different_units_are_different_facts():
    """`$4.2M`, `4.2%` and `4.2GB` all normalised to the string "4.2" before this module existed."""
    fs = _facts(title="Q3", text=[{"lines": ["$4.2M in revenue", "4.2% churn", "4.2 GB per render"]}])
    assert len(fs) == 3
    assert {f.unit for f in fs} == {"currency", "percent", "bytes"}


def test_a_units_slip_does_not_satisfy_the_fact():
    fs = [f for f in _facts(text=[{"lines": ["Ships with 2 TB of storage"]}]) if f.kind == "number"]
    got = F.check(fs, "Ships with 2 GB of storage")
    assert got[0].status != "present"


def test_megabytes_beat_the_million_scale_word():
    """"MB" and the scale word "M" overlap; the longer reading has to win or every MB becomes a million."""
    n = F.parse_numbers("500 MB per slide")[0]
    assert n.unit == "bytes" and n.value == pytest.approx(5e8)


# ---------------------------------------------------------------- present, missing, changed
def test_a_fact_may_be_reworded_freely_as_long_as_the_value_holds():
    """The whole reason the ledger is not a verbatim rule: framing is free, the value is not."""
    fs = [f for f in _facts(text=[{"lines": ["Adoption reached 40% of seats in 2024"]}]) if f.kind == "number"]
    fs = [f for f in fs if f.unit == "percent"]
    for rendering in ["40%", "Four in ten seats — 40% — now active", "40 %", "40percent"]:
        assert F.check(fs, rendering)[0].status == "present", rendering


def test_rounding_on_the_slide_is_still_the_same_fact():
    fs = [f for f in _facts(text=[{"lines": ["Utilisation hit 41.80%"]}]) if f.unit == "percent"]
    assert F.check(fs, "Utilisation hit 41.8%")[0].status == "present"


def test_a_dropped_fact_is_missing_not_changed():
    fs = [f for f in _facts(text=[{"lines": ["Revenue grew to $4.2M"]}]) if f.kind == "number"]
    c = F.check(fs, "Revenue grew strongly")[0]
    assert c.status == "missing" and not c.fatal


def test_a_moved_value_in_the_same_claim_is_changed_and_fatal():
    """The distinction the module exists for: a shortfall is not a lie."""
    fs = [f for f in _facts(text=[{"lines": ["Revenue grew to $4.2M this year"]}]) if f.kind == "number"]
    c = F.check(fs, "Revenue grew to $5.1M this year")[0]
    assert c.status == "changed" and c.fatal
    assert "4.2" in c.detail and "5.1" in c.detail


def test_an_unrelated_number_of_the_same_unit_is_not_called_a_change():
    """"changed" has to stay rare or fatal means nothing."""
    fs = [f for f in _facts(text=[{"lines": ["Revenue grew to $4.2M"]}]) if f.kind == "number"]
    c = F.check(fs, "Training costs reached $9.8M across the region")[0]
    assert c.status == "missing"


def test_a_stray_matching_number_elsewhere_no_longer_proves_a_fact_survived():
    """The old check searched a bag of digits, so any 40 vouched for every 40."""
    fs = [f for f in _facts(text=[{"lines": ["Latency fell 40%"]}]) if f.unit == "percent"]
    assert F.check(fs, "Slide 40 of 60. Latency improved.")[0].status == "missing"


# ---------------------------------------------------------------- notes are not the slide
def test_a_supporting_fact_may_live_in_the_notes():
    fs = [f for f in _facts(text=[{"lines": ["Revenue grew to $4.2M"]}]) if f.kind == "number"]
    c = F.check(fs, "Revenue grew strongly", "Revenue grew to $4.2M")[0]
    assert c.status == "notes" and c.ok


def test_a_key_fact_in_the_notes_only_is_not_ok():
    """The loophole that let a deck pass fidelity with every figure behind the presenter view."""
    fs = [f for f in _facts(text=[{"lines": ["Revenue grew to $4.2M"]}]) if f.kind == "number"]
    for f in fs:
        f.tier = "key"
    c = F.check(fs, "Revenue grew strongly", "Revenue grew to $4.2M")[0]
    assert c.status == "notes" and not c.ok
    assert F.ledger(fs, "Revenue grew strongly", "Revenue grew to $4.2M").hidden


# ---------------------------------------------------------------- invented facts
def test_a_fabricated_figure_is_reported():
    fs = _facts(text=[{"lines": ["Adoption reached 40%"]}])
    assert "92%" in F.invented(fs, "Adoption reached 40%, and 92% of users stayed")


def test_plain_numbers_the_design_introduces_are_not_fabrications():
    """Step counters, "1 of 6" and axis ticks are the runtime's, not claims about the world."""
    fs = _facts(text=[{"lines": ["Adoption reached 40%"]}])
    assert F.invented(fs, "Adoption reached 40%. Step 2 of 4. 2024 2025 2026") == []


# ---------------------------------------------------------------- names
def test_a_single_word_product_name_is_a_fact():
    """`Zscaler`, `ZBook`, `NVFP4` — invisible to a check that required two capitalised words."""
    fs = _facts(text=[{"lines": ["Secured by Zscaler on every ZBook"]}])
    assert {"Zscaler", "ZBook"} <= set(_raws(fs))


def test_a_sentence_opener_is_not_a_name():
    fs = _facts(text=[{"lines": ["Security matters to every team"]}])
    assert [f for f in fs if f.kind == "name"] == []


def test_a_name_split_across_elements_still_counts():
    fs = [f for f in _facts(text=[{"lines": ["The HP Z8 Fury G5 workstation"]}]) if f.kind == "name"]
    assert fs and F.check(fs, "<em>HP</em> <b>Z8 Fury</b> <span>G5</span>")[0].status == "present"


# ---------------------------------------------------------------- structured sources
def test_table_cells_and_chart_series_become_facts_without_being_read():
    content = {
        "tables": [[["Region", "Seats"], ["EMEA", "12,500"], ["APAC", "8,300"]]],
        "charts": [{"type": "bar", "title": "Growth", "categories": ["2023", "2024"],
                    "series": [{"name": "Revenue", "values": [4.2, 6.8]}]}],
    }
    vals = {f.value for f in F.extract(content) if f.kind == "number"}
    assert {12500.0, 8300.0} <= vals, "table cells"
    assert {4.2, 6.8} <= vals, "chart series values come from python-pptx exactly"


def test_the_ledger_is_deterministic():
    content = {"title": "Q3 results", "text": [{"lines": ["$4.2M revenue", "40% growth"]}]}
    a, b = F.extract(content), F.extract(content)
    assert F.dump(a) == F.dump(b)


def test_a_ledger_is_capped_so_a_dense_slide_is_split_not_checked_harder():
    content = {"text": [{"lines": [f"metric {i} reached {i + 10}%" for i in range(200)]}]}
    assert len(F.extract(content)) <= F._MAX_FACTS


# ---------------------------------------------------------------- round-tripping
def test_facts_survive_the_database_column():
    fs = _facts(title="Q3", text=[{"lines": ["$4.2M revenue at 40% margin"]}])
    assert F.dump(F.load(F.dump(fs))) == F.dump(fs)


def test_an_unreadable_stored_fact_is_dropped_not_raised():
    assert F.load([{"nonsense": True}, None, 7]) == []


def test_the_generator_is_told_which_facts_must_be_visible():
    fs = _facts(text=[{"lines": ["$4.2M revenue", "40% margin"]}])
    fs[0].tier = "key"
    out = F.for_prompt(fs)
    assert any("4.2" in x for x in out["must_be_visible"])
    assert not any("4.2" in x for x in out["must_survive"])
