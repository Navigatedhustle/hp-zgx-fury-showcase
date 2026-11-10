#!/usr/bin/env python3
"""GB10 stage lifecycle using the existing verified process controller."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATE = ROOT / 'state/stage'
STATE.mkdir(parents=True, exist_ok=True)


def request(action):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({'action': action}).encode()
    req = urllib.request.Request('http://127.0.0.1:18808/stage/api/control', data=body,
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=180) as response:
        return json.load(response)


def controller(action, *names):
    subprocess.run([str(ROOT / '.venv/bin/python'), 'ops/control.py', action, *names], cwd=ROOT, env=os.environ, check=True)


def free_request(path='', body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('http://127.0.0.1:18808/free/api/' + (path or 'state'),
        data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try:
        with opener.open(req, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and body is None:
            return {'mode': 'presenter', 'jobs': []}
        try:
            detail = json.load(exc).get('detail', str(exc))
        except (ValueError, OSError):
            detail = str(exc)
        raise RuntimeError(detail) from exc


def open_free():
    print('Free Mode: http://127.0.0.1:18808/free · seven interactive experiences; shared resident models.')
    if os.getenv('FURY_NO_BROWSER') != '1':
        subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / 'ops/open-nano-browser.py')], check=False)


def start_models():
    import control
    # Match Show.recover: the CPU materialization/upload peak needs room that
    # resident language weights would occupy during a cold creative reload.
    if not control.discover('image') or not control.ready('image'):
        for name in ('lead', 'text'):
            if control.discover(name):
                controller('stop', name)
    for name in ('image', 'tts', 'text', 'lead', 'gateway'):
        controller('start', name)


def desktop_environment():
    result = {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + str(os.getuid()) + '/bus'}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            values = dict(part.split(b'=', 1) for part in (process / 'environ').read_bytes().split(b'\0') if b'=' in part)
            if b'DISPLAY' in values and b'XAUTHORITY' in values:
                authority = Path(os.fsdecode(values[b'XAUTHORITY']))
                if authority.stat().st_uid == os.getuid():
                    result.update(DISPLAY=os.fsdecode(values[b'DISPLAY']), XAUTHORITY=str(authority))
                    break
        except (OSError, ValueError):
            continue
    return result


def hygiene(restore=False):
    path = STATE / 'display-restore.json'
    if restore:
        if path.exists():
            for item in json.loads(path.read_text()):
                subprocess.run(['gsettings', 'set', item['schema'], item['key'], item['original']], check=True)
            path.unlink()
        return
    specs = [('org.gnome.desktop.session', 'idle-delay', 'uint32 0'),
             ('org.gnome.desktop.screensaver', 'lock-enabled', 'false'),
             ('org.gnome.desktop.screensaver', 'idle-activation-enabled', 'false'),
             ('org.gnome.desktop.notifications', 'show-banners', 'false'),
             ('org.gnome.desktop.notifications', 'show-in-lock-screen', 'false'),
             ('com.ubuntu.update-notifier', 'no-show-notifications', 'true')]
    if path.exists():
        return
    saved = []
    for schema, key, value in specs:
        old = subprocess.run(['gsettings', 'get', schema, key], text=True, capture_output=True)
        if old.returncode:
            continue
        saved.append({'schema': schema, 'key': key, 'original': old.stdout.strip()})
        # Save before mutation, including when an individual setting fails.
        path.write_text(json.dumps(saved, indent=2))
        subprocess.run(['gsettings', 'set', schema, key, value], check=True)
    commands = ['gsettings set ' + shlex.quote(x['schema']) + ' ' + shlex.quote(x['key']) + ' ' + shlex.quote(x['original']) for x in saved]
    (STATE / 'restore-display.sh').write_text('#!/bin/sh\n' + '\n'.join(commands) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', nargs='?', default='start', choices=['start', 'status', 'reset', 'stop', 'record', 'rehearse'])
    args = parser.parse_args()
    plan = json.loads((ROOT / 'config/gb10.json').read_text())
    os.environ.update(FURY_PROFILE='gb10', FURY_STAGE_RUNTIME='1',
        FURY_GB10_QUANT=plan['lanes']['text']['quant'], FURY_GB10_FLUX_ENCODER=plan['flux_encoder'],
        FURY_GB10_VOICE_DEVICE=plan['lanes']['tts']['device'], FURY_GB10_RELEASE_WEIGHT_CACHE='1',
        FURY_GB10_LEAD_LOAD_MODE=plan['lanes']['lead']['loading'], FURY_GB10_TEXT_LOAD_MODE=plan['lanes']['text']['loading'],
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT / '.cache/ms-playwright'), **plan['offline'])
    os.environ.update(desktop_environment())
    free = os.getenv('FURY_FREE_MODE') == '1'
    if free and args.action not in ('start', 'status', 'stop'):
        raise RuntimeError('Use ./launch.sh free [start|status|stop]. Show reset and recording belong to ./launch.sh stage.')
    if args.action in ('start', 'record') and os.getenv('FURY_STAGE_SCOPE') != '1':
        os.execvp('systemd-run', ['systemd-run', '--user', '--scope', '--quiet', '--unit=nanoexec-stage-' + str(os.getpid()),
            '--property=MemorySwapMax=0', '/usr/bin/env', 'FURY_STAGE_SCOPE=1', sys.executable, __file__, args.action])
    if args.action == 'status':
        controller('status')
        if free:
            try:
                snapshot = free_request()
                print('Mode: ' + snapshot['mode'] + '; active Free Mode jobs: ' + str(sum(row['status'] in ('queued', 'running', 'cancelling') for row in snapshot['jobs'])))
            except (OSError, ValueError, RuntimeError):
                print('Free Mode is unavailable. Run ./launch.sh free to start it.')
            return
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:18808/stage/api/state', timeout=3) as response:
                state = json.load(response)
            checks = state['readiness']['checks']
            mode = 'Backup recording preparation' if state['readiness']['recording'] else ('Protected show' if state['readiness'].get('protected') else 'Fast live stage')
            print(mode + ': ' + str(sum(bool(row['ok']) for row in checks)) + ' of ' + str(len(checks)) + ' Ready checks green')
            for row in checks:
                if not row['ok']:
                    print(row['label'] + ': ' + row['fix'])
        except (OSError, ValueError, KeyError):
            print('Stage page is unavailable. Run ./launch.sh stage to start it.')
    elif args.action == 'stop':
        controller('stop')
        hygiene(restore=True)
    elif args.action == 'rehearse':
        request('rehearse')
        print('Full two-pass rehearsal started. Track progress at http://127.0.0.1:18808/stage')
    elif args.action == 'reset':
        began = time.monotonic()
        result = request('reset')
        print('Stage reset in %.2f s; Ready checks: %s' % (time.monotonic() - began, 'green' if result['readiness']['ready'] else 'unresolved'))
    else:
        import control
        running_page = control.discover('stage')
        if running_page:
            if free:
                free_request('mode', {'mode': 'free'})
                open_free()
                return
            current_free = free_request()
            if any(row['status'] in ('queued', 'running', 'cancelling') for row in current_free['jobs']):
                raise RuntimeError('Free Mode has active work. Wait or cancel it before launching the presenter show.')
            if args.action == 'start':
                free_request('mode', {'mode': 'presenter'})
                hygiene()
                controller('start', 'kiosk')
                print('Executive Stage: http://127.0.0.1:18808/stage · shared models retained; short functional preparation.')
                return
        if args.action == 'record':
            os.environ.update(FURY_STAGE_RECORD='1', FURY_STAGE_CAPTURE='1')
        if not free:
            hygiene()
        # Reload the page service and kiosk with this invocation's explicit
        # recording mode, instead of adopting a previous recording session.
        controller('stop', 'stage', 'kiosk')
        from ops.gb10_file_cache import release_model_cache
        for lane in plan['lanes'].values():
            # Clear pre-existing clean hash/download cache before allocating
            # GPU weights; this advisory never changes file contents.
            directory = next(row['directory'] for row in json.loads((ROOT / 'config/model-files.json').read_text())['gb10'] if row['repo'] == lane['repository'])
            release_model_cache(directory, plan['lanes']['text']['quant'])
        rehearsal = STATE / 'plans/rehearsed.json'
        rehearsal.parent.mkdir(exist_ok=True)
        if not rehearsal.exists():
            rehearsal.write_bytes((ROOT / 'samples/stage/rehearsed-plan.json').read_bytes())
        # The controller iterates its definition order for a multi-name request.
        # Unified-memory loading must follow the order measured in Gate 1.
        start_models()
        controller('start', 'stage')
        if free:
            open_free()
            return
        if not os.getenv('DISPLAY') and os.getenv('FURY_STAGE_HEADLESS') != '1':
            raise RuntimeError('Sign into the local desktop, then run ./launch.sh stage again. Models remain resident.')
        controller('start', 'kiosk')
        print('Executive Stage: http://127.0.0.1:18808/stage · short functional preparation; full rehearsal is optional.')
        if args.action == 'record':
            try:
                subprocess.run([sys.executable, 'ops/gb10-record.py'], cwd=ROOT, check=True)
            except subprocess.CalledProcessError:
                controller('stop', 'kiosk')
                raise RuntimeError('Backup recording failed. Capture has stopped and models remain resident. Fix the reported live error, then run ./launch.sh stage record again.')
            os.environ.pop('FURY_STAGE_RECORD', None)
            os.environ.pop('FURY_STAGE_CAPTURE', None)
            controller('stop', 'stage', 'kiosk')
            controller('start', 'stage')
            controller('start', 'kiosk')
            print('Five backups decoded and seeked successfully. Normal stage readiness now requires all five.')


if __name__ == '__main__':
    main()
