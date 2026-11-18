"""Projection arithmetic and truthful missing-data handling, without model inference."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_projection(expression):
    node = shutil.which('node')
    if not node:
        candidates = list((ROOT / '.venv/lib').glob('python*/site-packages/playwright/driver/node'))
        node = str(candidates[0]) if candidates else None
    if not node:
        pytest.skip('JavaScript runtime unavailable')
    script = '''const fs=require('fs'),vm=require('vm');
const context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync('showcase_app/stage/economics.js','utf8'),context);
const api=context.window.NanoEconomics;
const config=JSON.parse(fs.readFileSync('config/event-pricing.json','utf8')).gb10.projection;
const tokens={input_tokens:1000,output_tokens:2000};
console.log(JSON.stringify(''' + expression + '));'
    return json.loads(subprocess.check_output([node, '-e', script], cwd=ROOT, text=True))


def test_team_month_and_year_use_customer_employee_and_day_multipliers():
    value = run_projection('api.project(tokens,config)')
    assert (value['dailyRuns'], value['monthlyRuns'], value['annualRuns']) == (2000, 60000, 720000)
    assert value['monthly'] == dict(input=60000000, output=120000000, total=180000000)
    assert value['annual'] == dict(input=720000000, output=1440000000, total=2160000000)
    assert value['rows'][1]['monthly'] == 5280  # 60M * $8 + 120M * $40
    assert value['rows'][1]['annual'] == pytest.approx(63360)
    assert value['rows'][3]['monthly'] == 2640  # Opus: $4 / $20
    assert value['rows'][4]['monthly'] == 1320  # Gemini: dated promotional $2 / $10


def test_electricity_is_for_the_fleet_and_updates_independently_of_cloud():
    value = run_projection('api.project(tokens,config)')
    assert value['kwh'] == 6720
    assert value['rows'][0]['monthly'] == 1008
    assert value['rows'][0]['annual'] == 12096
    changed = run_projection('api.project(tokens,config,{devices:1,watts:100,hours_per_day:24,usd_per_kwh:0.2})')
    assert changed['kwh'] == pytest.approx(72)
    assert changed['rows'][0]['monthly'] == pytest.approx(14.4)
    assert changed['rows'][1:] == value['rows'][1:]


def test_missing_or_invalid_tokens_never_become_free_cloud_usage():
    assert run_projection('[undefined,null,{}, {input_tokens:0,output_tokens:0}, {input_tokens:null,output_tokens:20}, {input_tokens:-1,output_tokens:20}].map(x=>api.project(x,config))') == [None] * 6
    assert run_projection('api.project(tokens,null)') is None


def test_close_stays_visible_and_scopes_pricing_and_electricity():
    html = run_projection('api.render({telemetry:{pricing_totals:tokens,cloud_bytes:0,external_calls:0}},config,{},"EXIT")')
    assert 'Monthly cost' in html and 'Yearly cost' in html
    assert '120,000,000' in html and '1,440,000,000' in html
    assert 'Electricity only' in html and 'Assumed power' in html
    assert 'held constant' in html and 'model outputs differ' in html
    source = (ROOT / 'showcase_app/stage/stage.js').read_text()
    close = source.split('function close(s){', 1)[1].split('\n', 1)[0]
    assert 'NanoEconomics.render' in close and 'wall' not in close
    assert 'economics.js' in (ROOT / 'showcase_app/stage/index.html').read_text()
