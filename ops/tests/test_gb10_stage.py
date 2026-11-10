"""Stage invariants exercised without starting or substituting a model."""
import asyncio
import importlib
import os
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def stage_module(monkeypatch):
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    monkeypatch.setenv('FURY_STAGE_RUNTIME', '1')
    sys.path.insert(0, str(ROOT / 'ops'))
    return importlib.import_module('showcase_app.stage_api')


def test_copy_edit_preserves_guard_against_regulatory_claims():
    from showcase_app.gb10_agent import check_claims, operational_wording
    edited, changes = operational_wording({'points': ['Track review compliance weekly']})
    assert changes and edited['points'] == ['Track review completion weekly']
    assert check_claims(edited)
    for claim in ['HIPAA compliant', 'GDPR compliance', 'SOC 2 certified', 'review compliance and ISO 27001 certification']:
        candidate, _ = operational_wording(claim)
        with pytest.raises(ValueError):
            check_claims(candidate)


def test_keepalive_and_warmup_never_enter_live_session_totals(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    with sqlite3.connect(tmp_path / 'usage.sqlite') as db:
        db.execute('CREATE TABLE events(input_tokens, output_tokens, images, pages, images_analyzed, purpose, run_id, status)')
        db.executemany('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', [
            (10, 20, 1, 2, 3, 'live', 'session_S1', 'complete'),
            (999, 999, 999, 999, 999, 'keepalive', 'session_ping', 'complete'),
            (999, 999, 999, 999, 999, 'warmup', 'session_warm', 'complete'),
            (999, 999, 999, 999, 999, 'live', 'other_S1', 'complete'),
            (999, 999, 999, 999, 999, 'live', 'session_failed', 'failed')])
    show = object.__new__(module.Show)
    show.session = 'session'
    show.attempts = [{'segment': 'S1', 'started': 10, 'ended': 12}]
    assert show.totals() == dict(input_tokens=10, output_tokens=20, images=1, pages=2, images_analyzed=3, tokens_per_second=10)


def test_back_and_multiple_pending_next_never_repeat_or_stack(monkeypatch):
    module = stage_module(monkeypatch)
    async def check():
        show = object.__new__(module.Show)
        show.lock = asyncio.Lock()
        show.view = 1
        show.runs = {'S0': {'backup': False}, 'S1': {'backup': False}}
        show.resetting = False
        show.pending = False
        show.task = asyncio.create_task(asyncio.sleep(30))
        try:
            for _ in range(5):
                await show.next()
            assert show.pending is True and show.view == 1
            show.view = 0
            await show.next()
            assert show.view == 1 and len(show.runs) == 2
        finally:
            show.task.cancel()
            await asyncio.gather(show.task, return_exceptions=True)
    asyncio.run(check())


def test_reset_failure_clears_reset_flag_and_blocks_readiness(monkeypatch):
    module = stage_module(monkeypatch)
    show = object.__new__(module.Show)
    show.resetting = False
    show.warm = True
    async def broken(segment):
        show.resetting = True
        raise RuntimeError('Owned lane recovery failed')
    show._reset = broken
    with pytest.raises(RuntimeError):
        asyncio.run(show.reset())
    assert not show.resetting and not show.warm
    assert 'status' in show.warm_error


def test_private_settings_require_boolean_flags(monkeypatch, tmp_path):
    from showcase_app import stage_common
    monkeypatch.setattr(stage_common, 'STATE', tmp_path)
    (tmp_path / 'stage.local.json').write_text('{"audio":"false"}')
    with pytest.raises(ValueError, match='audio'):
        stage_common.local_settings()


def test_ready_cannot_be_green_while_free_mode_owns_the_models(monkeypatch):
    from types import SimpleNamespace
    module = stage_module(monkeypatch)
    show = object.__new__(module.Show)
    show.health = {name: {'ready': True} for name in module.CORE}
    show.warm, show.warm_error, show.recording = True, None, False
    show.viewport = {'width': 1920, 'height': 1080}
    show.settings = {'audio': False}
    show.telemetry = {'cloud_bytes': 0}
    show.backup_checks = lambda: []
    monkeypatch.setattr(module, 'memory', lambda: {'available': 20 * 2**30})
    manager = SimpleNamespace(active=True, switching=False)
    monkeypatch.setattr(module, 'free_mode', manager)
    for key, value in module.CONFIG['offline'].items():
        monkeypatch.setenv(key, value)
    assert not show.readiness()['ready']
    assert show.readiness()['checks'][0]['label'] == 'Presenter Mode'
    manager.active, manager.switching = False, True
    assert not show.readiness()['ready']
    manager.switching = False
    assert show.readiness()['ready']


def test_rejected_second_reset_cannot_unlock_the_running_reset(monkeypatch):
    module = stage_module(monkeypatch)
    async def check():
        show = object.__new__(module.Show)
        show.resetting = False
        show.warm = True
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(segment):
            if show.resetting:
                raise module.HTTPException(409)
            show.resetting = True
            entered.set()
            await release.wait()
        show._reset = slow
        first = asyncio.create_task(show.reset())
        await entered.wait()
        try:
            with pytest.raises(module.HTTPException) as rejected:
                await show.reset()
            assert rejected.value.status_code == 409
            assert show.resetting and show.warm
        finally:
            release.set()
            await first
        assert not show.resetting
    asyncio.run(check())


def test_fast_preparation_skips_full_show_and_records_real_probe_failure(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    show = object.__new__(module.Show)
    show.recording = False
    show.journal = lambda *args, **kwargs: None
    calls = []
    async def broken_probe():
        calls.append('functional')
        raise RuntimeError('Voice unavailable')
    def forbidden(*args, **kwargs):
        pytest.fail('Fast preparation must not execute a full agent or Rush')
    show.functional_warmup = broken_probe
    monkeypatch.setattr(module, 'NanoAgent', forbidden)
    monkeypatch.setattr(module, 'NanoRush', forbidden)
    asyncio.run(show.warmup())
    assert calls == ['functional']
    assert not show.warm and show.preparation['status'] == 'failed'
    assert 'Preparation failed' in show.warm_error


def test_functional_warmup_has_real_language_vision_image_and_audio_probes(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    (tmp_path / 'creative').mkdir()
    artifact = tmp_path / 'creative/probe.png'
    artifact.write_bytes(b'image')
    show = object.__new__(module.Show)
    show.preparation = {}
    calls = []
    async def inference(messages, **options):
        calls.append(options)
        return {'content': 'Ready', 'finish_reason': 'stop'}
    async def image(*args, **options):
        calls.append({'image': True, 'purpose': args[2]})
        return {'files': ['probe.png']}
    class Client:
        def __init__(self, **options): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **options):
            calls.append({'voice': True})
            return type('Audio', (), {'content': b'x' * 200, 'raise_for_status': lambda self: None})()
    monkeypatch.setattr(module, 'infer', inference)
    monkeypatch.setattr(module, 'image_job', image)
    monkeypatch.setattr(module.httpx, 'AsyncClient', Client)
    asyncio.run(show.functional_warmup())
    assert len(calls) == 5
    assert {row['model'] for row in calls if 'model' in row} == {module.LEAD, module.WORKER}
    assert any(row.get('role') == 'vision_probe' for row in calls)
    assert all(row.get('purpose', 'warmup') == 'warmup' for row in calls)
    assert all(step['status'] == 'complete' and step['seconds'] >= 0 for step in show.preparation['steps'])
    assert not artifact.exists()


def test_fast_start_keeps_all_core_checks_and_backup_protection_is_explicit(monkeypatch):
    module = stage_module(monkeypatch)
    show = object.__new__(module.Show)
    show.health = {name: {'ready': True} for name in module.CORE}
    show.warm, show.warm_error, show.recording = True, '', False
    show.viewport = {'width': 1920, 'height': 1080}
    show.settings = {'audio': False, 'require_backups': False}
    show.telemetry = {'cloud_bytes': 0}
    show.backup_checks = lambda: [{'label': 'S1 backup', 'ok': False, 'fix': 'Record this build'}]
    monkeypatch.setattr(module, 'free_mode', None)
    monkeypatch.setattr(module, 'memory', lambda: {'available': 20 * 2**30})
    for key, value in module.CONFIG['offline'].items():
        monkeypatch.setenv(key, value)
    result = show.readiness()
    assert result['ready'] and not result['protected']
    assert len(result['checks']) == 8 and result['backups'][0]['ok'] is False
    show.settings['require_backups'] = True
    assert not show.readiness()['ready']
    show.settings['require_backups'] = False
    show.health['text']['ready'] = False
    assert not show.readiness()['ready']


def test_live_failure_never_plays_missing_or_stale_recording(monkeypatch):
    module = stage_module(monkeypatch)
    show = object.__new__(module.Show)
    show.recording = False
    show.pending = True
    show.runs = {'S1': {'id': 'unit', 'started': 1, 'backup': False, 'status': 'running'}}
    show.backup_checks = lambda: [{'label': 'S1 backup', 'ok': False}]
    show.journal = lambda *args, **kwargs: None
    asyncio.run(show.failover('S1', 'Actual render failed'))
    row = show.runs['S1']
    assert row['status'] == 'failed' and row['backup_unavailable']
    assert not row['backup'] and not show.pending
    show.backup_checks = lambda: [{'label': 'S1 backup', 'ok': True}]
    asyncio.run(show.failover('S1', 'Presenter selected backup'))
    assert row['backup'] and 'failover_elapsed' in row


def test_saved_preparation_is_bound_to_source_and_live_process_identity(monkeypatch, tmp_path):
    import json
    module = stage_module(monkeypatch)
    import control
    monkeypatch.setattr(module, 'STATE', tmp_path)
    show = object.__new__(module.Show)
    show.recording = False
    show.warm_signature = lambda: 'new-source'
    saved = {'version': 2, 'kind': 'functional', 'signature': 'new-source',
             'identities': {name: {'pid': 1} for name in module.CORE}}
    (tmp_path / 'warm.json').write_text(json.dumps(saved))
    monkeypatch.setattr(control, 'unchanged', lambda identity: True)
    monkeypatch.setattr(control, 'identity', lambda process, name: True)
    monkeypatch.setattr(control, 'process', lambda pid: {})
    assert show.reuse_warm()
    show.recording = True
    assert not show.reuse_warm(), 'Recording requires a full rehearsal'
    show.recording = False
    monkeypatch.setattr(control, 'unchanged', lambda identity: False)
    assert not show.reuse_warm()
    monkeypatch.setattr(control, 'unchanged', lambda identity: True)
    show.warm_signature = lambda: 'different-source'
    assert not show.reuse_warm()


def test_preparation_commit_failure_cannot_leave_ready_green(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    import control
    monkeypatch.setattr(module, 'STATE', tmp_path)
    show = object.__new__(module.Show)
    show.recording = False
    async def probes(): pass
    async def health(): return {name: {'ready': True} for name in module.CORE}
    show.functional_warmup = probes
    show.fetch_health = health
    show.warm_signature = lambda: 'source'
    def journal(kind, **data):
        if kind == 'warm_complete':
            raise OSError('Disk full')
    show.journal = journal
    monkeypatch.setattr(control, 'discover', lambda name: {'pid': 1})
    monkeypatch.setattr(control, 'fingerprint', lambda row: row)
    asyncio.run(show.warmup())
    assert not show.warm and not show.full_warm_complete
    assert show.preparation['status'] == 'failed'


def test_full_rehearsal_still_runs_every_workflow_twice(monkeypatch, tmp_path):
    module = stage_module(monkeypatch)
    import control
    monkeypatch.setattr(module, 'STATE', tmp_path)
    show = object.__new__(module.Show)
    show.recording = True
    show.settings = {'audio': False}
    show.journal = lambda *args, **kwargs: None
    show.warm_signature = lambda: 'source'
    calls = []
    class Agent:
        def __init__(self, run_id, **options): pass
        async def run(self): calls.append('agent'); return {'seconds': 1}
    class Rush:
        def __init__(self, run_id, **options): pass
        async def run(self): calls.append('rush'); return {'seconds': 1, 'done': 6}
    async def vision(*args): calls.append('vision'); return {'seconds': 1}
    async def tiny(*args): calls.append('keepalive')
    async def health(): return {name: {'ready': True} for name in module.CORE}
    show.fetch_health = health
    show.tiny_warm = tiny
    monkeypatch.setattr(module, 'NanoAgent', Agent)
    monkeypatch.setattr(module, 'NanoRush', Rush)
    monkeypatch.setattr(module, 'run_vision', vision)
    monkeypatch.setattr(control, 'discover', lambda name: {'pid': 1})
    monkeypatch.setattr(control, 'fingerprint', lambda row: row)
    asyncio.run(show.warmup())
    assert calls == ['agent', 'vision', 'rush'] * 2 + ['keepalive']
    assert show.warm and show.full_warm_complete
    assert show.preparation['kind'] == 'rehearsal'


def test_nano_uses_original_supplied_hp_logo(monkeypatch):
    module = stage_module(monkeypatch)
    response = asyncio.run(module.logo())
    assert response.media_type == 'image/png'
    assert Path(response.path) == ROOT / 'showcase_app/assets/hp-logo-keyline.png'
