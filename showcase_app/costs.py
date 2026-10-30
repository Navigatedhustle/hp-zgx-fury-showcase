"""Counterfactual text API pricing and overlap-safe request-time estimates.

Sources checked 2026-10-16. This reprices local tokens; it does not call cloud APIs.
"""
import math
from datetime import date

PRICING_CHECKED = '2026-10-16'
MODELS = [
    {'id': 'gpt-6-astra', 'name': 'GPT-6 Astra', 'provider': 'OpenAI',
     'input': 10., 'output': 50., 'long_threshold': 272000, 'long_input': 20., 'long_output': 75.,
     'note': 'Standard; prompts >272K use $20 input / $75 output.',
     'source': 'https://developers.openai.com/api/docs/models/gpt-6-astra'},
    {'id': 'claude-fable-5-1', 'name': 'Claude Fable 5.1', 'provider': 'Anthropic',
     'input': 10., 'output': 50., 'note': 'Standard base-token rates.',
     'source': 'https://platform.claude.com/docs/en/about-claude/pricing'},
    {'id': 'claude-opus-5-5', 'name': 'Claude Opus 5.5', 'provider': 'Anthropic',
     'input': 4., 'output': 20., 'note': 'Standard base-token rates.',
     'source': 'https://platform.claude.com/docs/en/about-claude/pricing'},
    {'id': 'gemini-4-argon', 'name': 'Gemini 4 Argon', 'provider': 'Google',
     'input': 2., 'output': 10.,
     'note': 'Promotional rates through 30 Nov 2026; $4 / $20 from 1 Dec 2026.',
     'source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon'},
]
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
