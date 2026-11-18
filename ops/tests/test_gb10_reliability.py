"""Failures retain successful work and support bounded, accountable recovery."""
import asyncio
import copy
import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from showcase_app.gb10_errors import WorkflowError, public_failure, image_failure
from showcase_app.gb10_rush import NanoRush


def test_public_failure_reports_memory_without_exposing_private_exception_text():
    memory = type('OutOfMemoryError', (RuntimeError,), {})('PRIVATE_PROMPT_SENTINEL')
    result = public_failure(memory)
    assert result['code'] == 'image_memory' and result['retryable']
    assert 'PRIVATE_PROMPT_SENTINEL' not in str(result)
    grouped = ExceptionGroup('parallel tools', [ValueError('PRIVATE'), WorkflowError('image_review', 'Review failed')])
    assert public_failure(grouped)['code'] == 'image_review'
    assert image_failure({'error': 'OutOfMemoryError'}).code == 'image_memory'


def test_rush_retry_runs_only_unfinished_work_and_preserves_prior_results(tmp_path):
    async def run():
        runner = object.__new__(NanoRush)
        runner.folder, runner.jobs = tmp_path, {}
        runner.event = lambda *args, **kwargs: None
        runner.audio = False
        calls = []
        async def complete():
            raise AssertionError('A completed task must not run again')
        async def images():
            calls.append('images')
            return {'kit_file': 'pilot-image-kit.zip'}
        runner.risks = runner.app = runner.chart = runner.translate = runner.voice_or_summary = complete
        runner.images = images
        previous = {name: {'name': name, 'status': 'complete', 'result': {'kept': name}}
                    for name in ('risks', 'app', 'chart', 'translation', 'summary')}
        previous['images'] = {'name': 'images', 'status': 'failed', 'failure': {'code': 'image_memory'}}
        original = copy.deepcopy(previous)
        result = await runner.run(previous=previous)
        assert calls == ['images'] and result['done'] == 6
        assert previous == original
        assert result['jobs']['app']['result'] == {'kept': 'app'}
        assert json.loads((tmp_path / 'result.json').read_text())['done'] == 6
    asyncio.run(run())


def stage(monkeypatch):
    import importlib, sys
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    monkeypatch.setenv('FURY_STAGE_RUNTIME', '1')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
    return importlib.import_module('showcase_app.stage_api')


def test_retry_allocates_new_run_identity_and_keeps_completed_artifacts(monkeypatch, tmp_path):
    module = stage(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    async def run():
        show = object.__new__(module.Show)
        show.lock, show.view, show.resetting, show.maintenance, show.task = asyncio.Lock(), 3, False, False, None
        show.session, show.serial, show.pending = 'a'*32, 1, False
        old = {'id': show.session + '_S3_1', 'status': 'partial', 'jobs': {
            'app': {'status': 'complete', 'result': {'file': 'calculator.html'}}, 'images': {'status': 'failed'}}}
        show.runs, show.attempts = {'S3': old}, [old]
        source = tmp_path / 'outputs' / old['id'] / 'S3'
        source.mkdir(parents=True)
        (source / 'calculator.html').write_text('prior validated app')
        (source / 'linked.txt').symlink_to('/etc/passwd')
        async def health(): return {name: {'ready': True} for name in module.CORE}
        async def execute(segment): pass
        show.fetch_health, show.execute = health, execute
        show.journal = lambda *args, **kwargs: None
        await show.retry_current()
        await show.task
        row = show.current()
        assert row['id'] != old['id'] and row['retry_of'] == old['id'] and row['retained_jobs'] == 1
        target = tmp_path / 'outputs' / row['id'] / 'S3'
        assert (target / 'calculator.html').read_text() == 'prior validated app'
        assert not (target / 'linked.txt').exists()
        assert len(show.attempts) == 2 and old['status'] == 'partial'
    asyncio.run(run())


@pytest.mark.parametrize('done', [5, 6])
def test_rush_partial_results_are_retained_without_false_full_success(monkeypatch, tmp_path, done):
    module = stage(monkeypatch)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    result_jobs = {name: {'name': name, 'status': 'complete', 'result': {'kept': True}}
                   for name in ('risks', 'app', 'images', 'chart', 'translation', 'summary')}
    if done == 5:
        result_jobs['images'] = {'name': 'images', 'status': 'failed', 'failure': public_failure(WorkflowError('image_memory', 'Memory is busy'))}
    class Runner:
        def __init__(self, *args, **kwargs): pass
        async def run(self): return {'done': done, 'jobs': result_jobs}
    monkeypatch.setattr(module, 'NanoRush', Runner)
    monkeypatch.setattr(module, 'swap_counters', lambda: {'pswpin': 0, 'pswpout': 0})
    with sqlite3.connect(tmp_path / 'usage.sqlite') as db:
        db.execute('CREATE TABLE events(id,run_id)')
        db.execute('CREATE TABLE routing(id,requested,actual,reason,started)')
    async def run():
        show = object.__new__(module.Show)
        row = {'id': 'unit_S3_1', 'status': 'running', 'started': time.time(), 'revision': 0,
               'backup': False, 'jobs': {}, 'vm_baseline': {'pswpin': 0, 'pswpout': 0}, 'minimum_memavailable': 1}
        show.runs, show.settings, show.recording, show.active_segment, show.pending = {'S3': row}, {'audio': False}, False, 'S3', False
        show.journal = lambda *args, **kwargs: None
        async def no_backup(*args): raise AssertionError('Unprotected partial work must remain live')
        show.failover = no_backup
        await show.execute('S3')
        assert row['status'] == ('partial' if done == 5 else 'complete')
        assert row['result']['done'] == done and row['jobs']['app']['result']['kept']
        if done == 5: assert row['failure_details']['code'] == 'image_memory'
    asyncio.run(run())


def test_watchdog_does_not_invalidate_completed_scenes(monkeypatch):
    module = stage(monkeypatch)
    async def run():
        show = object.__new__(module.Show)
        show.stopping, show.resetting, show.view, show.active_segment = False, False, 3, None
        show.runs = {'S3': {'status': 'complete', 'backup': False}}
        async def forbidden(): raise AssertionError('Completed scene should stay complete')
        async def finish(seconds): show.stopping = True
        show.fetch_health = forbidden
        monkeypatch.setattr(module.asyncio, 'sleep', finish)
        await show.watchdog()
        assert show.runs['S3']['status'] == 'complete'
    asyncio.run(run())


def test_manual_missing_backup_does_not_mark_good_live_results_failed(monkeypatch):
    module = stage(monkeypatch)
    row = {'status': 'complete', 'backup': False}
    show = SimpleNamespace(view=3, current=lambda: row, backup_checks=lambda: [], journal=lambda *a, **kw: None)
    monkeypatch.setattr(module, 'show', show)
    monkeypatch.setattr(module, 'free_mode', SimpleNamespace(active=False, switching=False))
    with pytest.raises(module.HTTPException) as error:
        asyncio.run(module.control(module.Command(action='backup')))
    assert error.value.status_code == 409 and row == {'status': 'complete', 'backup': False}


def test_rush_lane_outage_does_not_cancel_unrelated_work(monkeypatch):
    module = stage(monkeypatch)
    async def run():
        show = object.__new__(module.Show)
        row = {'status': 'running', 'backup': False, 'started': time.time()}
        show.stopping, show.resetting, show.view, show.active_segment = False, False, 3, 'S3'
        show.runs, show.unresponsive_since = {'S3': row}, {}
        show.journal = lambda *args, **kwargs: None
        async def health(): return {name: {'ready': name != 'image'} for name in module.CORE}
        async def forbidden(*args): raise AssertionError('An image outage must not cancel unrelated Rush jobs')
        async def finish(seconds): show.stopping = True
        show.fetch_health, show.failover = health, forbidden
        show.task = SimpleNamespace(cancel=lambda: (_ for _ in ()).throw(AssertionError('Cancelled all jobs')))
        monkeypatch.setattr(module.asyncio, 'sleep', finish)
        await show.watchdog()
        assert row['status'] == 'running' and row['lane_warnings'] == ['image']
    asyncio.run(run())


def test_retry_cannot_start_after_concurrent_exit_or_scene_change(monkeypatch):
    module = stage(monkeypatch)
    async def run():
        show = object.__new__(module.Show)
        show.lock, show.resetting, show.maintenance, show.task = asyncio.Lock(), False, False, None
        show.session, show.view, show.pending = 'a'*32, 3, False
        row = {'id': 'old', 'status': 'partial'}
        show.runs = {'S3': row}
        entered, release = asyncio.Event(), asyncio.Event()
        async def health():
            entered.set();await release.wait()
            return {name: {'ready': True} for name in module.CORE}
        show.fetch_health = health
        show.start_segment = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Started stale work'))
        task = asyncio.create_task(show.retry_current())
        await entered.wait()
        show.session, show.view = 'b'*32, -1
        release.set()
        with pytest.raises(module.HTTPException) as error:
            await task
        assert error.value.status_code == 409 and show.task is None
    asyncio.run(run())


def test_stale_presenter_link_returns_to_active_free_mode_instead_of_false_preparation(monkeypatch):
    module = stage(monkeypatch)
    manager = SimpleNamespace(active=True)
    monkeypatch.setattr(module, 'free_mode', manager)
    response = asyncio.run(module.page(SimpleNamespace(url=SimpleNamespace(path='/stage'))))
    assert response.status_code == 307 and response.headers['location'] == '/free'
    assert manager.active
    manager.active = False
    response = asyncio.run(module.page(SimpleNamespace(url=SimpleNamespace(path='/stage'))))
    assert isinstance(response, module.FileResponse)


def test_closing_summary_does_not_require_failed_services_to_be_restarted(monkeypatch, tmp_path):
    module = stage(monkeypatch);monkeypatch.setattr(module,'STATE',tmp_path)
    monkeypatch.setattr(module,'swap_counters',lambda:{'pswpin':0,'pswpout':0})
    with sqlite3.connect(tmp_path/'usage.sqlite') as db:
        db.execute('CREATE TABLE events(id,run_id)');db.execute('CREATE TABLE routing(id,requested,actual,reason,started)')
    async def run():
        show=object.__new__(module.Show)
        row={'id':'unit_S4_1','status':'running','started':time.time(),'revision':0,'backup':False,'jobs':{},'minimum_memavailable':1,'vm_baseline':{'pswpin':0,'pswpout':0}}
        show.runs,show.active_segment,show.pending,show.telemetry={'S4':row},'S4',False,{'cloud_bytes':0}
        show.totals=lambda:{'images':1};show.journal=lambda *a,**kw:None
        async def health():return {name:{'ready':name!='image'} for name in module.CORE}
        show.fetch_health=health
        await show.execute('S4')
        assert row['status']=='complete' and row['result']['unavailable_lanes']==['image']
    asyncio.run(run())
