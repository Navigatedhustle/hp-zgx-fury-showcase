import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gb10_benchmark', ROOT / 'ops/gb10-benchmark.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_table_shapes_preserve_identical_values():
    expected = {'columns': ['Quarter', 'Jobs'], 'rows': [['Q1', 12], ['Q2', 18]]}
    named = {'columns': ['Quarter', 'Jobs'], 'rows': [{'Quarter': 'Q1', 'Jobs': '12'}, {'Quarter': 'Q2', 'Jobs': '18'}]}
    assert bench.extraction_matches('chart.png', named, expected)
    named['rows'][1]['Jobs'] = '19'
    assert not bench.extraction_matches('chart.png', named, expected)


def test_missing_or_invented_chart_fields_fail():
    expected = {'columns': ['Quarter', 'Jobs'], 'rows': [['Q1', 12]]}
    assert not bench.extraction_matches('chart.png', {'columns': expected['columns'], 'rows': [{'Quarter': 'Q1'}]}, expected)
    assert not bench.extraction_matches('chart.png', {'columns': expected['columns'], 'rows': [['Q1', 12], ['Q2', 18]]}, expected)


def test_owner_and_date_must_belong_to_correct_action():
    truth = [{'action': 'Review plan', 'owner': 'Alex', 'date': '2027-04-12'}]
    assert bench.extraction_matches('whiteboard.png', [{'action': 'REVIEW PLAN', 'owner': 'ALEX', 'date': '2027-04-12'}], truth)
    assert not bench.extraction_matches('whiteboard.png', [{'action': 'REVIEW PLAN', 'owner': 'CASEY', 'date': '2027-04-12'}], truth)
def test_column_metadata_cannot_disagree_with_the_rows():
    from showcase_app.gb10_quality import extraction_matches
    truth = {'columns': ['Quarter', 'Jobs'], 'rows': [['Q1', 12]]}
    actual = {'columns': [{'name': 'Quarter', 'values': ['Q1']}, {'name': 'Jobs', 'values': [12]}], 'rows': [{'Quarter': 'Q1', 'Jobs': 12}]}
    assert extraction_matches('chart.png', actual, truth)
    actual['columns'][1]['values'] = [13]
    assert not extraction_matches('chart.png', actual, truth)

