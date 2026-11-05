"""Counterfactual text API pricing and overlap-safe request-time estimates.

Sources checked 2026-10-16. This reprices local tokens; it does not call cloud APIs.
"""
import math
from datetime import date

# The conference and retained API use the same locally cached official prices.
import json
from pathlib import Path
_CONFIGURATION=json.loads((Path(__file__).resolve().parents[1]/'config/event-pricing.json').read_text())
PRICING_CHECKED = _CONFIGURATION['checked']
MODELS = _CONFIGURATION['models']
TEXT_DEMOS = ('atlas', 'slides', 'agent')


def valid_number(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def union_seconds(rows):
    """Union of request wall-time intervals (includes queue wait, excludes gaps)."""
    intervals = sorted((r['started'], r['started'] + r['seconds']) for r in rows)
    total = 0.
    end = float('-inf')
    for start, stop in intervals:
        total += max(0., stop - max(start, end))
        end = max(end, stop)
    return total


def comparison(rows, today=None):
    today = today or date.today()
    models = [dict(m) for m in MODELS]
    if today >= date(2026, 12, 1):
        models[-1].update(input=4., output=20.)
    scopes = {}
    for scope in ('all', *TEXT_DEMOS):
        population = [r for r in rows if r['demo'] in TEXT_DEMOS and (scope == 'all' or r['demo'] == scope)]
        eligible = [r for r in population if r['status'] == 'complete' and
                    all(valid_number(r.get(k)) for k in ('input_tokens', 'output_tokens', 'started', 'seconds'))]
        costs = []
        for m in models:
            value = 0.
            for r in eligible:
                long = r['input_tokens'] > m.get('long_threshold', float('inf'))
                i, o = (m['long_input'], m['long_output']) if long else (m['input'], m['output'])
                value += (r['input_tokens'] * i + r['output_tokens'] * o) / 1_000_000
            costs.append({'model_id': m['id'], 'usd': value})
        scopes[scope] = {'requests': len(eligible), 'excluded_requests': len(population) - len(eligible),
                         'input': sum(r['input_tokens'] for r in eligible),
                         'output': sum(r['output_tokens'] for r in eligible),
                         'wall_seconds': union_seconds(eligible),
                         'first_started': min((r['started'] for r in eligible), default=None),
                         'last_ended': max((r['started'] + r['seconds'] for r in eligible), default=None),
                         'api_costs': costs}
    return {'pricing_checked': PRICING_CHECKED, 'currency': 'USD', 'models': models, 'scopes': scopes}
