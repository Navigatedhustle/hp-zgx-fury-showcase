"""Hardware selection must leave Fury definitions and process ownership intact."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gb10_runtime', ROOT / 'ops/gb10_runtime.py')
gb10 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gb10)


def test_explicit_profile_keeps_fury_defaults():
    script = "import json,runtime; print(json.dumps({'components':runtime.COMPONENTS,'serve':runtime.SERVE}))"
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'ops')}
    env.pop('FURY_PROFILE', None)
    fury = json.loads(subprocess.check_output([sys.executable, '-c', script], cwd=ROOT, env=env))
    nano = json.loads(subprocess.check_output([sys.executable, '-c', script], cwd=ROOT, env={**env, 'FURY_PROFILE': 'gb10'}))
    assert fury['components']['lead']['port'] == 8100
    assert fury['components']['text']['model'] == 'unsloth/Qwen3.6-27B-NVFP4'
    assert 'agent' in fury['components'] and 'asr' in fury['components']
    assert fury['components']['tts']['command'][3] == 'atlas.tts_server:app'
    assert nano['components']['tts']['command'][3] == 'showcase_app.gb10_voice_api:app'
    assert set(nano['components']) == {'lead', 'text', 'image', 'tts', 'gateway'}
    assert nano['serve'] == {}
    assert all(item['command'][item['command'].index('--host') + 1] == '127.0.0.1' for item in nano['components'].values())


def test_context_floor_and_explicit_residency():
    for item in gb10.components().values():
        if item.get('engine') != 'llama.cpp':
            continue
        cmd = item['command']
        assert int(cmd[cmd.index('--ctx-size') + 1]) // int(cmd[cmd.index('--parallel') + 1]) >= 16384
        assert cmd[cmd.index('--fit') + 1] == 'off'
        assert cmd[cmd.index('--lazy-mode') + 1] == 'off'
        assert '--jinja' in cmd and '--offline' in cmd
        assert cmd[cmd.index('--cache-ram') + 1] == '0'
        assert cmd[cmd.index('--ubatch-size') + 1] == '128'
    assert gb10.environment()['HF_HUB_OFFLINE'] == '1'
    assert gb10.environment()['TRANSFORMERS_OFFLINE'] == '1'


def test_unsupported_quant_never_substituted(monkeypatch):
    monkeypatch.setenv('FURY_GB10_QUANT', 'unknown')
    with pytest.raises(ValueError, match='no model substitution'):
        gb10.components()


def test_own_native_process_requires_exact_executable_and_args():
    script = '''
import control, json, os
from runtime import ROOT, COMPONENTS
cmd=COMPONENTS['lead']['command']
row={'uid':os.getuid(),'cwd':str(ROOT),'exe':str((ROOT/cmd[0]).resolve()),'args':cmd}
assert control.identity(row,'lead')
assert not control.identity({**row,'cwd':'/tmp/unrelated'},'lead')
assert not control.identity({**row,'exe':'/tmp/llama-server'},'lead')
assert not control.identity({**row,'args':cmd+['--port','1']},'lead')
print('verified')
'''
    assert subprocess.check_output([sys.executable, '-c', script], cwd=ROOT,
        env={**os.environ, 'PYTHONPATH': str(ROOT / 'ops'), 'FURY_PROFILE': 'gb10'}, text=True).strip() == 'verified'
