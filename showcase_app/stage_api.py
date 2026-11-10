"""Single-presenter GB10 stage, real tools, local artifacts and recorded failover."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Literal

from showcase_app.stage_common import ROOT, STATE, build_identity, local_settings, memory, network_state, profile, swap_counters

if os.getenv('FURY_PROFILE') != 'gb10':
    raise RuntimeError('Executive Stage requires the GB10 profile')
sys.path.insert(0, str(ROOT / 'ops'))
sys.path.insert(0, str(ROOT / 'build/sources/atlas-gpt-main'))
from atlas.offline_guard import install, connects
install()
from showcase_app.gb10_agent import NanoAgent, image_job
from showcase_app.gb10_client import infer, LEAD, WORKER
from showcase_app.gb10_rush import NanoRush, VOICE_LINE
from showcase_app.gb10_vision import run_vision
from showcase_app.gb10_security import StageRequestGuard
from showcase_app.gb10_miniapp import CSP as APP_CSP

CONFIG = profile()
BEATS = list(CONFIG['segments'])
STATIC = ROOT / 'showcase_app/stage'
CORE = ('lead', 'text', 'image', 'tts', 'gateway')
PORTS = {name: CONFIG['lanes'][name]['port'] for name in CORE if name != 'gateway'} | {'gateway': CONFIG['gateway_port']}
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"


class Show:
    def __init__(self):
        self.build = build_identity()
        self.settings = local_settings()
        self.session = uuid.uuid4().hex
        self.view = -1
        self.runs = {}
        self.attempts = []
        self.serial = 0
        self.task = None
        self.active_segment = None
        self.warm_task = None
        self.pending = False
        self.warm = False
        self.full_warm_complete = False
        self.resetting = False
        self.warm_error = ''
        self.health = {}
        self.telemetry = {}
        self.viewport = {}
        self.lock = asyncio.Lock()
        self.recording = os.getenv('FURY_STAGE_RECORD') == '1'
        self.keepalive_at = 0
        self.stopping = False
        self.unresponsive_since = {}
        self.journal('session', build=self.build['id'])

    def warm_signature(self):
        digest = hashlib.sha256()
        for name in ('showcase_app/gb10_agent.py', 'showcase_app/gb10_rush.py', 'showcase_app/gb10_vision.py', 'showcase_app/gb10_client.py', 'showcase_app/gb10_image_policy.py', 'showcase_app/gb10_miniapp.py', 'config/gb10.json', 'config/model-files.json'):
            digest.update((ROOT / name).read_bytes())
        digest.update(str(bool(self.settings['audio'])).encode())
        return digest.hexdigest()

    def reuse_warm(self):
        import control
        try:
            saved = json.loads((STATE / 'warm.json').read_text())
            return saved['signature'] == self.warm_signature() and saved['passes'] == 2 and all(
                control.unchanged(saved['identities'][name]) and control.identity(control.process(saved['identities'][name]['pid']), name) for name in CORE)
        except (OSError, ValueError, KeyError):
            return False

    def journal(self, kind, **data):
        folder = STATE / 'runs'
        folder.mkdir(exist_ok=True)
        with (folder / (self.session + '.jsonl')).open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'at': time.time(), **data}, ensure_ascii=False) + '\n')

    def current(self):
        return self.runs.get(BEATS[self.view]) if self.view >= 0 else None

    def emit(self, segment, event):
        row = self.runs[segment]
        kind = event.get('kind')
        if kind == 'step':
            row['steps'][event['step']['tool']] = event['step']
        elif kind == 'artifact':
            row['artifacts'][event['artifact']] = event['data']
        elif kind == 'job':
            row['jobs'][event['job']['name']] = event['job']
        elif kind in ('image_progress', 'images_progress'):
            row['image_progress'] = event['job']
        elif kind == 'actions':
            row['actions'] = event['actions']
        elif kind == 'readout':
            row['readout'] = event['text']
        elif kind == 'plan':
            row['plan'] = event['plan']
            row['rehearsed'] = event['rehearsed']
        elif kind == 'plan_stream':
            row['plan_text'] = event['text']
        elif kind == 'app_validating':
            row['app_validating'] = True
        elif kind == 'artifact_rejected':
            row['artifact_revision'] = event
        elif kind == 'wording_edited':
            row['wording_edited'] = event['label']
        row['revision'] += 1
        # Plan deltas are retained with actual times; no image payload is logged.
        self.journal('beat_event', segment=segment, run_id=row['id'], event=event)

    async def fetch_health(self):
        import control
        try:
            registry = json.loads((ROOT / 'state/supervisor.json').read_text())
        except (OSError, ValueError):
            registry = {}
        async with httpx.AsyncClient(trust_env=False, timeout=.3) as client:
            async def check(name, port):
                try:
                    if registry.get(name, {}).get('stopping'):
                        return name, {'ready': False, 'probe_status': 'Owned process is stopping'}
                    saved = registry.get(name, {}).get('leader')
                    if not saved or not control.unchanged(saved) or not control.identity(control.process(saved['pid']), name):
                        return name, {'ready': False, 'probe_status': 'Owned process is not running'}
                    response = await client.get(f'http://127.0.0.1:{port}/health')
                    value = response.json()
                    ready = value.get('status') == 'ok' if name in ('lead', 'text') else value.get('ready', False)
                    return name, {**value, 'ready': response.status_code == 200 and ready,
                                  'probe_status': 'HTTP ' + str(response.status_code)}
                except httpx.TimeoutException:
                    # GPU work and post-render collection can briefly hold the
                    # Python GIL. An alive owned process with resident weights
                    # is distinct from a failed HTTP response or process exit.
                    prior = self.health.get(name, {})
                    return name, {**prior, 'ready': prior.get('ready', False),
                                  'probe_status': 'Health response delayed', 'unresponsive': True}
                except (httpx.HTTPError, ValueError) as exc:
                    return name, {'ready': False, 'probe_status': type(exc).__name__}
            return dict(await asyncio.gather(*(check(n, p) for n, p in PORTS.items())))

    async def telemetry_loop(self):
        while not self.stopping:
            self.health = await self.fetch_health()
            metrics = memory()
            metrics['network'] = network_state()
            metrics['gpu'] = {'utilization': None, 'power': None, 'temperature': None}
            try:
                process = await asyncio.create_subprocess_exec('nvidia-smi', '--query-gpu=utilization.gpu,power.draw,temperature.gpu',
                    '--format=csv,noheader,nounits', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                raw, _ = await asyncio.wait_for(process.communicate(), 2)
                values = raw.decode().strip().split(',')
                for key, value in zip(metrics['gpu'], values):
                    try:
                        parsed = float(value.strip())
                        metrics['gpu'][key] = parsed if math.isfinite(parsed) else None
                    except ValueError:
                        pass
            except (OSError, asyncio.TimeoutError):
                pass
            metrics['clock'] = time.strftime('%H:%M:%S')
            metrics['disk_free'] = shutil.disk_usage(ROOT).free
            if self.view == -1 or 'audio' not in self.telemetry:
                try:
                    process = await asyncio.create_subprocess_exec('wpctl', 'inspect', '@DEFAULT_AUDIO_SINK@',
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                    raw, _ = await asyncio.wait_for(process.communicate(), 2)
                    metrics['audio'] = {'hdmi': process.returncode == 0 and 'hdmi' in raw.decode().lower()}
                except (OSError, asyncio.TimeoutError):
                    metrics['audio'] = {'hdmi': False}
            else:
                metrics['audio'] = self.telemetry['audio']
            gateway = self.health.get('gateway', {})
            metrics['external_calls'] = gateway.get('external_api_calls')
            metrics['cloud_bytes'] = 0 if gateway.get('local_only') and gateway.get('external_api_calls') == 0 and connects['blocked'] == 0 else None
            metrics['totals'] = self.totals()
            with sqlite3.connect(STATE / 'usage.sqlite') as db:
                counts = db.execute("SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0) FROM events WHERE run_id LIKE ? AND purpose='live' AND status='complete' AND role NOT IN ('whiteboard','chart','image_text_check')", (self.session + '%',)).fetchone()
                metrics['pricing_totals'] = {'input_tokens': counts[0], 'output_tokens': counts[1]}
                metrics['routing'] = [dict(zip(('reason', 'at'), item)) for item in db.execute(
                    "SELECT r.reason,r.started FROM routing r JOIN events e ON e.id=r.id WHERE e.run_id LIKE ? AND e.purpose='live' AND r.reason!='' ORDER BY r.started DESC LIMIT 1", (self.session + '%',))]
            self.telemetry = metrics
            await asyncio.sleep(.75)

    def totals(self):
        result = {'input_tokens': 0, 'output_tokens': 0, 'images': 0, 'pages': 0, 'images_analyzed': 0, 'tokens_per_second': 0}
        path = STATE / 'usage.sqlite'
        if not path.exists():
            return result
        with sqlite3.connect(path, timeout=2) as db:
            values = db.execute('SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(images),0),COALESCE(SUM(pages),0),COALESCE(SUM(images_analyzed),0) FROM events WHERE purpose=? AND run_id LIKE ? AND status=?', ('live', self.session + '%', 'complete')).fetchone()
        result.update(dict(zip(list(result), values)))
        active_seconds = sum((row.get('ended', time.time()) - row['started']) for row in self.attempts if row['segment'] in ('S1', 'S2', 'S3'))
        result['tokens_per_second'] = result['output_tokens'] / max(1, active_seconds)
        return result

    def backup_checks(self):
        checks = []
        for segment in BEATS:
            path = STATE / 'backup' / (segment + '.mp4')
            meta = path.with_suffix('.json')
            try:
                info = json.loads(meta.read_text())
                ok = path.is_file() and path.stat().st_size > 10000 and path.stat().st_mtime >= self.build['created'] and info['build'] == self.build['id'] and info.get('verified', {}).get('decode') is True and info.get('label_burned') == 'Recorded run'
            except (OSError, ValueError, KeyError):
                ok = False
            checks.append({'label': segment + ' backup', 'ok': ok, 'fix': 'Run ./launch.sh stage record to create a backup for this build.'})
        return checks

    def readiness(self):
        m = memory()
        checks = [
            {'label': 'Four models resident', 'ok': all(self.health.get(n, {}).get('ready') for n in CORE), 'fix': 'Run ./launch.sh stage to load the local lanes.'},
            {'label': 'Models warmed', 'ok': self.warm, 'fix': self.warm_error or 'Warm-up is running. Wait for both passes to finish.'},
            {'label': 'Unified memory reserve', 'ok': m['available'] >= CONFIG['minimum_memavailable_gib'] * 2**30, 'fix': 'Close unrelated applications, then run ./launch.sh stage reset.'},
            {'label': 'Local inference only', 'ok': all(os.getenv(k) == v for k, v in CONFIG['offline'].items()) and self.telemetry.get('cloud_bytes') == 0, 'fix': 'Restart with ./launch.sh stage so the offline profile is applied.'},
            {'label': 'Display ' + str(self.viewport.get('width', '?')) + ' × ' + str(self.viewport.get('height', '?')), 'ok': self.viewport.get('width', 0) >= 1280 and self.viewport.get('height', 0) >= 720, 'fix': 'Connect HDMI at its native resolution and open the stage kiosk.'},
            {'label': 'Audio ' + ('on · HDMI' if self.settings['audio'] else 'off'), 'ok': not self.settings['audio'] or (self.health.get('tts', {}).get('ready', False) and self.telemetry.get('audio', {}).get('hdmi', False)), 'fix': 'Select the HDMI sink with the AV team or turn audio off.'},
            {'label': 'Disk free', 'ok': shutil.disk_usage(ROOT).free > 5 * 2**30, 'fix': 'Make 5 GiB free for session recordings. Do not delete model weights.'},
            {'label': 'Clock ' + time.strftime('%H:%M'), 'ok': time.time() > 1735689600, 'fix': 'Check the desktop clock before the show.'},
        ]
        backups = self.backup_checks()
        checks.extend(backups)
        ready = all(check['ok'] for check in checks if not self.recording or check not in backups)
        return {'ready': ready, 'checks': checks, 'recording': self.recording}

    def snapshot(self):
        row = self.current()
        if row:
            row = {**row, 'elapsed': (row.get('ended', time.time()) - row['started'])}
        return {'session': self.session, 'view': self.view, 'beat': BEATS[self.view] if self.view >= 0 else 'READY',
                'running': self.task is not None and not self.task.done(),
                'run': row, 'pending': self.pending, 'warming': not self.warm, 'resetting': self.resetting, 'settings': self.settings,
                'telemetry': self.telemetry, 'health': self.health, 'readiness': self.readiness(), 'warm_error': self.warm_error,
                'build': self.build['id'][:12]}

    async def failover(self, segment, reason):
        row = self.runs[segment]
        if row['backup']:
            return
        if self.recording and not (STATE / 'backup' / (segment + '.mp4')).exists():
            row.update(recording_error=reason, failure=reason)
            self.journal('recording_failed', segment=segment, reason=reason)
            return
        row.update(backup=True, failover_at=time.time(), failover_elapsed=time.time() - row['started'], failure=reason)
        self.journal('failover', segment=segment, run_id=row['id'], reason=reason, elapsed=row['failover_elapsed'])

    async def watchdog(self):
        while not self.stopping:
            if self.resetting:
                await asyncio.sleep(.1)
                continue
            row = self.current()
            active_name = self.active_segment
            active = self.runs.get(active_name)
            if (row and not row['backup']) or (active and active['status'] == 'running'):
                checks = await self.fetch_health()
                if self.resetting:
                    continue
                failed = []
                for name in CORE:
                    if checks[name].get('unresponsive'):
                        self.unresponsive_since.setdefault(name, time.monotonic())
                        if time.monotonic() - self.unresponsive_since[name] > 2:
                            failed.append(name)
                    else:
                        self.unresponsive_since.pop(name, None)
                        if not checks[name].get('ready'):
                            failed.append(name)
                if failed:
                    self.journal('lane_unhealthy', lanes=failed, probes={name: checks[name].get('probe_status') for name in failed})
                    affected = {active_name} if active_name else set()
                    if row:
                        affected.add(BEATS[self.view])
                    for segment in affected:
                        if segment in self.runs:
                            await self.failover(segment, 'Local lane unavailable: ' + ', '.join(failed))
                    if self.task and not self.task.done():
                        self.task.cancel()
                elif active and active['status'] == 'running' and time.time() - active['started'] > CONFIG['segments'][active_name]['deadline']:
                    await self.failover(active_name, 'Live run deadline reached')
                    if self.task:
                        self.task.cancel()
            await asyncio.sleep(.15)

    async def execute(self, segment):
        row = self.runs[segment]
        try:
            emit = lambda event: self.emit(segment, event)
            if segment == 'S1':
                result = await NanoAgent(row['id'], audio=self.settings['audio'], emit=emit).run()
            elif segment == 'S2':
                result = await run_vision(row['id'], emit=emit)
            elif segment == 'S3':
                result = await NanoRush(row['id'], audio=self.settings['audio'], emit=emit).run()
                if result['done'] != 6:
                    raise RuntimeError('One or more Rush jobs failed validation')
            else:
                self.health = await self.fetch_health()
                if not all(self.health[n]['ready'] for n in CORE):
                    raise RuntimeError('Model residency check failed')
                result = {'totals': self.totals(), 'cloud_bytes': self.telemetry.get('cloud_bytes')}
            row.update(status='complete', result=result)
        except asyncio.CancelledError:
            row['status'] = 'interrupted'
        except Exception as exc:
            logging.exception('Stage live run failed: %s', segment)
            row['status'] = 'failed'
            await self.failover(segment, type(exc).__name__)
        finally:
            row['ended'] = time.time()
            counters = swap_counters()
            row['swap_in_pages'] = counters['pswpin'] - row['vm_baseline']['pswpin']
            row['swap_out_pages'] = counters['pswpout'] - row['vm_baseline']['pswpout']
            with sqlite3.connect(STATE / 'usage.sqlite') as db:
                row['routing'] = [dict(zip(('requested', 'actual', 'reason', 'at'), item)) for item in db.execute(
                    'SELECT r.requested,r.actual,r.reason,r.started FROM routing r JOIN events e ON e.id=r.id WHERE e.run_id=?', (row['id'],))]
            for route in row['routing']:
                self.journal('routing', run_id=row['id'], **route)
            if self.active_segment == segment:
                self.active_segment = None
            row['revision'] += 1
            self.journal('beat_end', segment=segment, run_id=row['id'], seconds=row['ended'] - row['started'], status=row['status'], backup=row['backup'], memory=memory(), minimum_memavailable=row['minimum_memavailable'], swap_in_pages=row['swap_in_pages'], swap_out_pages=row['swap_out_pages'])
            if self.pending:
                self.pending = False
                if not row.get('recording_error'):
                    if row['backup']:
                        await asyncio.sleep(.4)
                    asyncio.create_task(self.next())

    async def next(self):
        async with self.lock:
            candidate = min(4, self.view + 1)
            if BEATS[candidate] in self.runs and not self.resetting:
                self.view = candidate
                return
            if self.resetting:
                self.pending = True
                return
            if self.view < 0 and not self.readiness()['ready']:
                raise HTTPException(409, 'Ready checklist has unresolved items')
            if self.task and not self.task.done() and not (self.current() or {}).get('backup'):
                self.pending = True
                return
            if self.task and not self.task.done():
                self.pending = False
                self.task.cancel()
                await self.task
            self.view = min(4, self.view + 1)
            segment = BEATS[self.view]
            if segment in self.runs:
                return
            self.serial += 1
            row = {'id': self.session + '_' + segment + '_' + str(self.serial), 'started': time.time(),
                   'segment': segment, 'status': 'running', 'backup': False, 'steps': {}, 'artifacts': {}, 'jobs': {}, 'revision': 0,
                   'minimum_memavailable': memory()['available'], 'vm_baseline': swap_counters()}
            self.runs[segment] = row
            self.attempts.append(row)
            self.active_segment = segment
            self.journal('beat_start', segment=segment, run_id=row['id'])
            self.task = asyncio.create_task(self.execute(segment))

    async def recover(self):
        import control
        async def operate(action, name):
            process = await asyncio.create_subprocess_exec(str(ROOT / '.venv/bin/python'), str(ROOT / 'ops/control.py'), action, name,
                cwd=ROOT, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            if await process.wait():
                raise RuntimeError('Could not recover ' + name + '; run ./launch.sh stage status')
        # The qualified image loader materializes CPU weights before upload.
        # Free the owned native weights during a cold image recovery, then
        # reload in the measured order. No unrelated process is signalled.
        if not control.discover('image') or not control.ready('image'):
            for name in ('lead', 'text'):
                if control.discover(name):
                    await operate('stop', name)
        for name in ('image', 'tts', 'text', 'lead', 'gateway'):
            existing = control.discover(name)
            if not existing or not control.ready(name):
                await operate('restart' if existing else 'start', name)

    async def tiny_warm(self, purpose='keepalive'):
        run_id = purpose + '_' + uuid.uuid4().hex
        async def text(model):
            return await infer([{'role': 'user', 'content': 'Say Ready.'}], model=model, caller='keepalive',
                               run_id=run_id, purpose=purpose, max_tokens=8)
        async def voice():
            async with httpx.AsyncClient(trust_env=False, timeout=12) as client:
                response = await client.post(f'http://127.0.0.1:{PORTS["tts"]}/v1/audio/speech', json={'input': 'Ready.', 'voice': 'am_michael'})
                response.raise_for_status()
        results = await asyncio.gather(text(LEAD), text(WORKER), voice(),
            image_job('A single original blue paper square, no text.', run_id, purpose, width=1024, height=576))
        for name in results[-1]['files']:
            (STATE / 'creative' / name).unlink(missing_ok=True)
        self.journal('keepalive', purpose=purpose, elapsed=time.time())

    async def warmup(self):
        try:
            for number in (1, 2):
                for segment, runner in [('S1', lambda rid: NanoAgent(rid, purpose='warmup', audio=self.settings['audio'], emit=lambda event: self.journal('warm_event', event=event)).run()),
                                        ('S2', lambda rid: run_vision(rid, 'warmup')),
                                        ('S3', lambda rid: NanoRush(rid, purpose='warmup', audio=self.settings['audio']).run())]:
                    result = await runner('warm_' + uuid.uuid4().hex)
                    if segment == 'S3' and result['done'] != 6:
                        raise RuntimeError('Rush warm-up did not complete all six jobs')
                    self.journal('warmup', segment=segment, pass_number=number, seconds=result.get('seconds'))
            await self.tiny_warm('warmup')
            self.warm = True
            self.full_warm_complete = True
            self.keepalive_at = time.monotonic()
            import control
            identities = {name: control.fingerprint(control.discover(name)) for name in CORE}
            (STATE / 'warm.json').write_text(json.dumps({'signature': self.warm_signature(), 'passes': 2, 'identities': identities, 'at': time.time()}))
            self.journal('warm_complete')
        except Exception as exc:
            logging.exception('Exact-input stage warm-up failed')
            self.warm_error = 'Warm-up failed: ' + type(exc).__name__ + '. Run ./launch.sh stage reset.'
            self.journal('warm_failed', error=type(exc).__name__)

    async def keepalive(self):
        while not self.stopping:
            await asyncio.sleep(1)
            if self.warm and self.view == -1 and time.monotonic() - self.keepalive_at >= 60:
                self.keepalive_at = time.monotonic()
                try:
                    await self.tiny_warm()
                except Exception as exc:
                    self.warm = False
                    self.warm_error = 'Keep-alive failed. Run ./launch.sh stage reset.'
                    self.journal('keepalive_failed', error=type(exc).__name__)

    async def reset(self, segment=False):
        # A rejected concurrent reset must never clear the first reset's flag.
        if self.resetting:
            raise HTTPException(409, 'A reset is already running')
        try:
            await self._reset(segment)
        except Exception:
            self.warm = False
            self.warm_error = 'Reset did not recover every lane. Run ./launch.sh stage status, then ./launch.sh stage reset.'
            raise
        finally:
            self.resetting = False

    async def _reset(self, segment=False):
        if self.resetting:
            raise HTTPException(409, 'A reset is already running')
        began = time.monotonic()
        self.resetting = True
        self.pending = False
        if self.task and not self.task.done():
            self.task.cancel()
            await self.task
        if self.warm_task and not self.warm_task.done():
            self.warm_task.cancel()
            await asyncio.gather(self.warm_task, return_exceptions=True)
        self.warm = False
        await self.recover()
        idle_deadline = time.monotonic() + 20
        while True:
            health = await self.fetch_health()
            if not health['image'].get('active') and not health['image'].get('queued'):
                break
            if time.monotonic() > idle_deadline:
                self.resetting = False
                raise HTTPException(503, 'The image lane did not finish cancelling. Run ./launch.sh stage reset.')
            await asyncio.sleep(.1)
        if self.full_warm_complete:
            await self.tiny_warm('warmup')
        else:
            await self.warmup()
            if not self.warm:
                self.resetting = False
                raise HTTPException(503, self.warm_error)
        self.resetting = False
        if segment and self.view >= 0:
            index = self.view
            for name in BEATS[index:]:
                self.runs.pop(name, None)
            self.view -= 1
            self.warm = True
            await self.next()
        else:
            self.pending = False
            self.journal('session_end', totals=self.totals())
            with sqlite3.connect(STATE / 'usage.sqlite') as db:
                ids = [x[0] for x in db.execute('SELECT id FROM events WHERE run_id LIKE ? AND role=?', (self.session + '%', 'image'))]
            for identifier in ids:
                if re.fullmatch(r'[a-f0-9]{32}', identifier):
                    for suffix in ('', '-1', '-2', '-3', '-4'):
                        (STATE / 'creative' / (identifier + suffix + '.png')).unlink(missing_ok=True)
            for folder in (STATE / 'outputs').glob(self.session + '*'):
                if folder.is_dir() and not folder.is_symlink():
                    shutil.rmtree(folder)
            self.session = uuid.uuid4().hex
            self.runs = {}
            self.attempts = []
            self.view = -1
            self.warm = True
            self.warm_error = ''
            self.keepalive_at = time.monotonic()
            self.journal('session', build=self.build['id'])
        self.journal('reset', seconds=time.monotonic() - began, segment=segment)

    async def memory_sampler(self):
        while not self.stopping:
            available = memory()['available']
            for row in self.attempts:
                if row['status'] == 'running':
                    row['minimum_memavailable'] = min(row['minimum_memavailable'], available)
            await asyncio.sleep(.1)


show = Show()


@asynccontextmanager
async def lifespan(app):
    tasks = [asyncio.create_task(show.telemetry_loop()), asyncio.create_task(show.watchdog()),
             asyncio.create_task(show.keepalive()), asyncio.create_task(show.memory_sampler())]
    if show.reuse_warm():
        show.warm = show.full_warm_complete = True
        show.journal('warm_reused', signature=show.warm_signature())
    else:
        show.warm_task = asyncio.create_task(show.warmup())
        tasks.append(show.warm_task)
    yield
    show.stopping = True
    if show.task:
        show.task.cancel()
    if show.warm_task:
        show.warm_task.cancel()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(StageRequestGuard, limit=65536)


@app.middleware('http')
async def headers(request, call_next):
    if request.headers.get('host') not in ('127.0.0.1:18808', 'localhost:18808'):
        return JSONResponse({'error': 'Only the local stage host is allowed'}, status_code=403)
    response = await call_next(request)
    response.headers['Content-Security-Policy'] = APP_CSP if request.url.path.endswith('/calculator.html') else CSP
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/health')
async def health():
    return {'ready': True, 'warmed': show.warm, 'recording': show.recording, 'build': show.build['id']}


@app.get('/stage')
@app.get('/stage/keys')
@app.get('/stage/models')
async def page():
    return FileResponse(STATIC / 'index.html')


@app.get('/stage/assets/{name}')
async def asset(name: str):
    if name not in ('stage.js', 'stage.css'):
        raise HTTPException(404)
    return FileResponse(STATIC / name)


@app.get('/stage/api/state')
async def state():
    return show.snapshot()


@app.get('/stage/api/events')
async def events(request: Request):
    async def stream():
        while not await request.is_disconnected():
            yield 'data: ' + json.dumps(show.snapshot(), ensure_ascii=False) + '\n\n'
            await asyncio.sleep(.15)
    return StreamingResponse(stream(), media_type='text/event-stream')


class Command(BaseModel):
    action: Literal['next', 'back', 'backup', 'reset', 'reset_segment', 'settings', 'viewport']
    audio: bool | None = None
    projector_boost: bool | None = None
    width: int = 0
    height: int = 0


@app.post('/stage/api/control')
async def control(command: Command):
    show.journal('control', action=command.action)
    if command.action == 'next':
        await show.next()
    elif command.action == 'back':
        show.view = max(-1, show.view - 1)
    elif command.action == 'backup':
        if show.view >= 0:
            row = show.current()
            if row['backup']:
                row['backup'] = False
            else:
                await show.failover(BEATS[show.view], 'Presenter selected backup')
    elif command.action in ('reset', 'reset_segment'):
        await show.reset(command.action == 'reset_segment')
    elif command.action == 'settings' and show.view == -1:
        if command.audio is not None and command.audio != show.settings['audio']:
            if not show.warm:
                raise HTTPException(409, 'Wait for the current warm-up before changing the audio setting')
            show.settings['audio'] = command.audio
            show.warm = show.full_warm_complete = False
            show.warm_task = asyncio.create_task(show.warmup())
        for key in ('audio', 'projector_boost'):
            if (value := getattr(command, key)) is not None:
                show.settings[key] = value
    elif command.action == 'viewport':
        show.viewport = {'width': command.width, 'height': command.height}
    return show.snapshot()


@app.get('/stage/api/models')
async def models():
    result = []
    async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
        for name, lane in CONFIG['lanes'].items():
            item = dict(lane)
            item['ready'] = show.health.get(name, {}).get('ready', False)
            try:
                if name in ('lead', 'text'):
                    data = (await client.get(f'http://127.0.0.1:{lane["port"]}/v1/models')).json()
                    item['parameters'] = data['data'][0]['meta']['n_params'] + item.get('projector_parameters', 0)
                elif name == 'image':
                    item['parameters'] = show.health['image']['parameter_count']
                else:
                    data = (await client.get(f'http://127.0.0.1:{lane["port"]}/gb10/memory')).json()
                    item['parameters'] = data['parameters']
            except (httpx.HTTPError, ValueError, KeyError):
                item['parameters'] = None
            result.append(item)
    return {'models': result, 'parameters_loaded': sum(item['parameters'] for item in result if item['ready'] and item['parameters'])}


@app.get('/stage/api/pricing')
async def pricing():
    return json.loads((ROOT / 'config/event-pricing.json').read_text()).get('gb10', {})


class VideoFrame(BaseModel):
    run_id: str
    at: float
    media_time: float


@app.post('/stage/api/control-frame')
async def video_frame(frame: VideoFrame):
    row = show.current()
    if not row or frame.run_id != row['id']:
        raise HTTPException(409)
    show.journal('backup_first_frame', run_id=frame.run_id, media_time=frame.media_time,
                 latency_seconds=frame.at - row.get('failover_at', frame.at))
    return {'ok': True}


@app.get('/stage/backup/{segment}.mp4')
async def backup(segment: str):
    if segment not in BEATS or not (path := STATE / 'backup' / (segment + '.mp4')).is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='video/mp4')


@app.get('/stage/sample/{name}')
async def sample(name: str):
    if name not in ('whiteboard.png', 'chart.png'):
        raise HTTPException(404)
    return FileResponse(ROOT / 'samples/stage/vision' / name)


@app.get('/stage/creative/{name}')
async def creative(name: str):
    if not re.fullmatch(r'[a-f0-9]{32}(?:-[1-4])?\.png', name):
        raise HTTPException(404)
    path = STATE / 'creative' / name
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/stage/artifact/{run_id}/{segment}/{name}')
async def artifact(run_id: str, segment: str, name: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id) or segment not in BEATS or name not in ('calculator.html', 'briefing.html', 'calculator.png', 'summary.pcm', 'voice.pcm'):
        raise HTTPException(404)
    path = STATE / 'outputs' / run_id / segment / name
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/stage/logo')
async def logo():
    path = ROOT / 'state/brand/hp_logo.svg'
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/svg+xml')
