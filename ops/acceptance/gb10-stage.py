#!/usr/bin/env python3
"""Actual native-kiosk rehearsal, offline socket, idle and controlled failure proof.

Requires the normal, fully warmed GB10 stage and current decoded backups.
No health-only, synthetic adapter or recording-bootstrap run is accepted.
Evidence stays in ignored state/stage/proof; publish only reviewed aggregates.
"""
import argparse
import gzip
import asyncio
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'ops')]
os.environ.update(FURY_PROFILE='gb10', FURY_STAGE_RUNTIME='1')
from showcase_app.stage_common import memory, swap_counters
import control

BASE = 'http://127.0.0.1:18808'
BEATS = ['S0', 'S1', 'S2', 'S3', 'S4']
KEYS = ['ArrowRight', 'PageDown', ' ', 'Enter', 'ArrowRight']
DWELL = [40, 110, 50, 60, 40]
TARGET = [40, 75, 30, 60, 40]


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)


class Proof:
    def __init__(self, mode):
        self.folder = ROOT / 'state/stage/proof' / (mode + '-' + str(int(time.time())))
        self.folder.mkdir(parents=True)
        self.mode = mode
        self.rows = []
        self.stop_sockets = False
        self.socket_errors = []
        self.socket_samples = 0

    def save(self, name, value):
        (self.folder / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    async def wait_for(self, predicate, timeout=10):
        # CDP evaluate accepts a function without adding unsafe-eval to stage CSP.
        deadline = time.monotonic() + timeout
        while not await self.page.evaluate(predicate):
            if time.monotonic() >= deadline:
                raise TimeoutError('Native stage predicate did not become true')
            await asyncio.sleep(.02)

    async def state(self):
        response = await self.client.get(BASE + '/stage/api/state')
        response.raise_for_status()
        return response.json()

    async def ready(self):
        deadline = time.monotonic() + 600
        while True:
            s = await self.state()
            if s['readiness']['recording']:
                raise RuntimeError('Recording bootstrap is not stage acceptance')
            if s['readiness']['ready']:
                return s
            if s['warm_error'] or time.monotonic() > deadline:
                raise RuntimeError(s['readiness'])
            await asyncio.sleep(.5)

    async def reset(self):
        began = time.monotonic()
        process = await asyncio.create_subprocess_exec(str(ROOT / 'launch.sh'), 'stage', 'reset', cwd=ROOT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), 65)
        if process.returncode or time.monotonic() - began >= 60:
            raise RuntimeError('Reset failed or exceeded 60 seconds: ' + output.decode())
        await self.ready()
        await self.page.reload(wait_until='domcontentloaded')
        await asyncio.sleep(.7)
        if (await self.state())['view'] != -1:
            raise RuntimeError('Reset did not return to Ready')
        return time.monotonic() - began

    async def segment(self, number, dwell=True):
        await self.page.keyboard.press(KEYS[number])
        began = time.monotonic()
        previous = BEATS[number - 1] if number else 'READY'
        while True:
            s = await self.state()
            row = s['run']
            if s['beat'] != BEATS[number] or not row:
                # A real keyboard event starts an asynchronous browser fetch.
                # Observe that single press; never resend it or skip a beat.
                if s['beat'] == previous and time.monotonic() - began < 3:
                    await asyncio.sleep(.02)
                    continue
                raise RuntimeError('Unexpected beat after clicker Next')
            if row['backup'] or row.get('recording_error') or row['status'] in ('failed', 'interrupted'):
                self.save('failed-' + BEATS[number] + '.json', s)
                raise RuntimeError('Live segment failed: ' + str(row.get('failure', row['status'])))
            if row['status'] == 'complete':
                seconds = row['ended'] - row['started']
                if seconds > TARGET[number]:
                    raise RuntimeError(BEATS[number] + ' exceeded its target')
                if number == 3 and (row['minimum_memavailable'] < 10 * 2**30 or row.get('swap_in_pages') or row.get('swap_out_pages')):
                    raise RuntimeError('Rush violated the measured memory or zero global swap plan')
                if not dwell or time.monotonic() - began >= DWELL[number]:
                    return s
            if time.monotonic() - began > max(DWELL[number] + 10, 95):
                raise RuntimeError('Show deadline exceeded')
            await asyncio.sleep(.15)

    async def full_show(self, index, reset=True):
        reset_seconds = await self.reset() if reset else 0
        began = time.monotonic()
        segments = []
        for number in range(5):
            s = await self.segment(number)
            row = s['run']
            segments.append({'segment': s['beat'], 'seconds': row['ended'] - row['started'],
                'minimum_memavailable_bytes': row['minimum_memavailable'],
                'swap_in_pages': row.get('swap_in_pages'), 'swap_out_pages': row.get('swap_out_pages'),
                'failover': row['backup'], 'status': row['status']})
            self.save(str(index) + '-' + s['beat'] + '.json', s)
            print(self.mode, index, s['beat'], round(segments[-1]['seconds'], 3), 's', flush=True)
            if index == 1:
                await asyncio.sleep(.3)
                await self.page.screenshot(path=str(self.folder / (s['beat'] + '-1920x1080.png')))
        result = {'run': index, 'segments': segments, 'wall_seconds': time.monotonic() - began,
                  'reset_seconds': reset_seconds, 'totals': s['telemetry']['totals']}
        if result['wall_seconds'] > 420:
            raise RuntimeError('The show exceeded seven minutes')
        self.rows.append(result)
        self.save('runs.json', self.rows)
        return result

    async def sockets(self):
        """Capture all host sockets; attribute app sockets by verified ownership."""
        with gzip.open(self.folder / 'all-sockets.log.gz', 'wt', compresslevel=1) as log:
            while not self.stop_sockets:
                processes = {p['pid']: p for p in control.processes()}
                owners = {row['pid'] for name in control.COMPONENTS if (row := control.discover(name))}
                changed = True
                while changed:
                    descendants = {p['pid'] for p in processes.values() if p['ppid'] in owners}
                    changed = bool(descendants - owners)
                    owners |= descendants
                process = await asyncio.create_subprocess_exec('ss', '-Htunap', stdout=asyncio.subprocess.PIPE)
                output, _ = await process.communicate()
                raw = output.decode()
                unix = await asyncio.create_subprocess_exec('ss', '-Hxap', stdout=asyncio.subprocess.PIPE)
                unix_output, _ = await unix.communicate()
                log.write(str(time.time()) + '\nTCP and UDP\n' + raw + 'Local Unix sockets\n' + unix_output.decode())
                log.flush()
                for line in raw.splitlines():
                    if not ({int(pid) for pid in re.findall(r'pid=(\d+)', line)} & owners):
                        continue
                    # ss fields: protocol state recv send local peer ...
                    endpoints = line.split()[4:6]
                    if len(endpoints) != 2 or not endpoints[0].startswith(('127.', '[::1]:', '::1:')) or not (endpoints[1].startswith(('127.', '[::1]:', '::1:')) or endpoints[1] in ('*:*', '0.0.0.0:*', '[::]:*')):
                        self.socket_errors.append(line)
                self.socket_samples += 1
                await asyncio.sleep(.5)

    async def verify_offline_environment(self):
        identities = {}
        for name in control.COMPONENTS:
            row = control.discover(name)
            if not row:
                raise RuntimeError('Missing owned stage component: ' + name)
            env = dict(x.split(b'=', 1) for x in Path('/proc', str(row['pid']), 'environ').read_bytes().split(b'\0') if b'=' in x)
            if any(env.get(key) != b'1' for key in (b'HF_HUB_OFFLINE', b'TRANSFORMERS_OFFLINE')):
                raise RuntimeError('Offline model environment missing: ' + name)
            identities[name] = control.fingerprint(row)
        self.save('identities.json', identities)

    async def offline(self):
        await self.verify_offline_environment()
        task = asyncio.create_task(self.sockets())
        try:
            for index in range(1, 4):
                await self.full_show(index)
        finally:
            self.stop_sockets = True
            await task
        if self.socket_errors:
            self.save('unexpected-app-sockets.json', self.socket_errors)
            raise RuntimeError('A stage-owned Internet socket was not loopback')

    async def chaos(self):
        for index, lane in enumerate(['lead', 'lead', 'text', 'image', 'gateway']):
            await self.reset()
            for before in range(index):
                await self.segment(before, dwell=False)
                await asyncio.sleep(.7)
            await self.page.keyboard.press(KEYS[index])
            await asyncio.sleep(.3 if index in (0, 4) else 1)
            owned = control.discover(lane)
            if not owned or not control.identity(control.process(owned['pid']), lane):
                raise RuntimeError('Chaos refuses to signal an unverified lane')
            self.save('chaos-' + BEATS[index] + '-identity.json', control.fingerprint(owned))
            async with self.page.expect_request('**/stage/api/control-frame', timeout=3000) as first_frame:
                stopped_at = time.time()
                process = await asyncio.create_subprocess_exec(sys.executable, 'ops/control.py', 'stop', lane, cwd=ROOT,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            frame = (await first_frame.value).post_data_json
            latency = frame['at'] - stopped_at
            await self.wait_for("()=>!document.querySelector('#backup').hidden && Number(getComputedStyle(document.querySelector('#backup')).opacity)>=.99", timeout=1)
            visible_latency = time.time() - stopped_at
            s = await self.state()
            if not s['run']['backup'] or latency > 1 or visible_latency > 1 or abs(frame['media_time'] - s['run']['failover_elapsed']) > .35:
                raise RuntimeError('Failover latency or elapsed seek failed: ' + str((latency, frame, s['run'])))
            await asyncio.sleep(.3)
            await self.page.screenshot(path=str(self.folder / ('chaos-' + BEATS[index] + '.png')))
            output, _ = await process.communicate()
            if process.returncode:
                raise RuntimeError(output.decode())
            reset_seconds = await self.reset()
            self.rows.append({'segment': BEATS[index], 'lane': lane, 'first_frame_seconds_from_stop': latency,
                'full_crossfade_seconds_from_stop': visible_latency, 'seek_media_time': frame['media_time'], 'reset_seconds': reset_seconds})
            self.save('chaos.json', self.rows)
            print('Chaos', BEATS[index], 'first frame', round(latency, 3), 'reset', round(reset_seconds, 3), flush=True)

    async def idle(self):
        await self.reset()
        await asyncio.sleep(1)
        session = (await self.state())['session']
        baseline = (await self.state())['telemetry']['totals']
        began = time.monotonic()
        while time.monotonic() - began < 45 * 60:
            s = await self.state()
            if s['view'] != -1 or s['session'] != session or not s['readiness']['ready']:
                raise RuntimeError('Ready became cold or unhealthy during the idle test')
            if s['telemetry']['totals'] != baseline:
                raise RuntimeError('Keep alive changed session totals or throughput')
            self.save('idle-progress.json', {'elapsed': time.monotonic() - began, 'session_totals_unchanged': True})
            await asyncio.sleep(1)
        # This actual post-idle show can be the first of ten consecutive shows.
        # Preserve its idle caches and session: no reset before this run.
        idle_seconds = time.monotonic() - began
        result = await self.full_show(1, reset=False)
        self.save('idle.json', {'idle_seconds': idle_seconds, 'session_totals_unchanged': True,
                              'post_idle_show': result})

    async def run(self):
        async with httpx.AsyncClient(trust_env=False, timeout=70) as client, async_playwright() as p:
            self.client = client
            browser = await p.chromium.connect_over_cdp('http://127.0.0.1:18810')
            self.page = browser.contexts[0].pages[0]
            if await self.page.evaluate('innerWidth!==1920||innerHeight!==1080'):
                raise RuntimeError('Native show proof requires the actual 1920x1080 kiosk')
            health = (await client.get('http://127.0.0.1:18809/health')).json()
            if health.get('headless') is not False or not control.discover('kiosk'):
                raise RuntimeError('Headless or unverified browser is not native HDMI stage acceptance')
            await self.ready()
            self.save('start.json', {'at': time.time(), 'memory': memory(), 'swap': swap_counters(), 'build': (await self.state())['build']})
            if self.mode in ('rehearsals', 'final'):
                await self.verify_offline_environment()
                capture = asyncio.create_task(self.sockets())
                try:
                    if self.mode == 'final':
                        await self.idle()
                    for index in range(2 if self.mode == 'final' else 1, 11):
                        await self.full_show(index)
                finally:
                    self.stop_sockets = True
                    await capture
                if self.socket_errors:
                    self.save('unexpected-app-sockets.json', self.socket_errors)
                    raise RuntimeError('A stage-owned network socket was not loopback')
            elif self.mode == 'offline':
                await self.offline()
            elif self.mode == 'chaos':
                await self.chaos()
            else:
                await self.idle()
            summary = {'mode': self.mode, 'passed': True, 'runs': len(self.rows), 'at': time.time(), 'socket_samples': self.socket_samples}
            if self.mode in ('rehearsals', 'offline', 'final'):
                summary['offline_full_shows_with_all_socket_capture'] = len(self.rows)
                summary['network_scope'] = 'All host TCP, UDP and Unix sockets captured. Owned stage process trees used loopback network connections and local Unix IPC only. Existing SSH and unrelated host processes are outside the application claim.'
                summary['segments'] = {beat: {'p50': statistics.median(v := [r['segments'][i]['seconds'] for r in self.rows]), 'p95': percentile(v, .95)} for i, beat in enumerate(BEATS)}
                summary['minimum_memavailable_bytes'] = min(s['minimum_memavailable_bytes'] for r in self.rows for s in r['segments'])
            if self.mode == 'final':
                summary['idle_seconds_before_first_show'] = json.loads((self.folder / 'idle.json').read_text())['idle_seconds']
            self.save('summary.json', summary)
            print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['rehearsals', 'offline', 'chaos', 'idle', 'final'])
    asyncio.run(Proof(parser.parse_args().mode).run())
