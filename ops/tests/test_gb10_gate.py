"""Gate decision regressions only; synthetic records are not hardware proof."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gb10_workload', ROOT / 'ops/gb10-workload.py')
workload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workload)


def candidate():
    runs = []
    for purpose, segments, count in [('warmup', ('S1', 'S2', 'S3'), 2), ('live', ('S1', 'S3'), 5)]:
        for segment in segments:
            for _ in range(count):
                runs.append({'purpose': purpose, 'segment': segment, 'status': 'complete',
                    'seconds': 50, 'lanes_resident': True,
                    'runtime_memory': {'swap_limit': '0', 'swap_current_bytes': 0},
                    'memory': {'min_available_bytes': 11 * 2**30, 'swap_in_pages': 0, 'swap_out_pages': 0,
                               'baseline': {'oom_kill': 0}, 'after': {'oom_kill': 0}}})
    return {'runs': runs}


def assess(row, **overrides):
    return workload.assess_gate(row, **({'warmups': 2, 'agent_runs': 5,
        'rush_runs': 5, 'require_no_swap_scope': True} | overrides))


def test_floor_applies_to_measured_rush_and_every_sample_matters():
    row = candidate()
    row['runs'][0]['memory']['min_available_bytes'] = 9 * 2**30
    assert assess(row)['passed']  # Cold Agent minimum remains reported, outside Rush rule.
    row['runs'][-1]['memory']['min_available_bytes'] = 10 * 2**30 - 1
    assert not assess(row)['passed']


@pytest.mark.parametrize('field', ['swap_in_pages', 'swap_out_pages'])
def test_even_one_global_swap_page_fails_despite_zero_scope_swap(field):
    row = candidate()
    row['runs'][-1]['memory'][field] = 1
    assert not assess(row)['passed']
    assert not assess(row)['checks']['rush_zero_global_swap']


@pytest.mark.parametrize('failure', ['oom', 'identity', 'tool', 'scope', 'missing_memory'])
def test_runtime_failure_cannot_pass(failure):
    row = candidate()
    run = row['runs'][-1]
    if failure == 'oom':
        run['memory']['after']['oom_kill'] = 1
    elif failure == 'identity':
        run['lanes_resident'] = False
    elif failure == 'tool':
        run['status'] = 'failed'
    elif failure == 'scope':
        run['runtime_memory']['swap_current_bytes'] = 4096
    else:
        del run['memory']
    assert not assess(row)['passed']


def test_sample_counts_warmups_and_deadlines_are_enforced():
    row = candidate()
    assert assess(row)['passed']
    assert not assess(row, warmups=1)['passed']
    assert not assess(row, rush_runs=4)['passed']
    assert not assess(row, require_no_swap_scope=False)['passed']
    short = copy.deepcopy(row)
    short['runs'].pop()
    assert not assess(short)['passed']
    row['runs'][-1]['seconds'] = 60.001
    assert not assess(row)['passed']
    row = candidate()
    for run in row['runs']:
        if run['purpose'] == 'live' and run['segment'] == 'S1':
            run['seconds'] = 75.001
    assert not assess(row)['passed']
