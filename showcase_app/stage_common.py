"""Local configuration and build identity for the GB10 stage only."""
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'state/stage'
STATE.mkdir(parents=True, exist_ok=True)


def profile():
    return json.loads((ROOT / 'config/gb10.json').read_text())


def local_settings():
    defaults = {'audio': False, 'projector_boost': False, 'customer_skin': False,
                'presenter_poster': False, 'live_camera': False}
    path = STATE / 'stage.local.json'
    if path.exists():
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('stage.local.json must contain an object')
        for key in defaults:
            if key in value and not isinstance(value[key], bool):
                raise ValueError(key + ' must be true or false')
        defaults.update(value)
    return defaults


def build_identity():
    files = [*ROOT.glob('showcase_app/*.py'), *ROOT.glob('showcase_app/stage/*'),
             *ROOT.glob('ops/*gb10*'), ROOT / 'ops/control.py', ROOT / 'ops/runtime.py',
             ROOT / 'launch.sh', ROOT / 'config/gb10.json', ROOT / 'config/gb10-build.json',
             ROOT / 'config/model-files.json', ROOT / 'config/event-pricing.json',
             *ROOT.glob('samples/stage/**/*')]
    digest = hashlib.sha256()
    for path in sorted(p for p in files if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes())
    identifier = digest.hexdigest()
    path = STATE / 'build.json'
    prior = json.loads(path.read_text()) if path.exists() else {}
    if prior.get('id') != identifier:
        prior = {'id': identifier, 'created': time.time()}
        path.write_text(json.dumps(prior, indent=2) + '\n')
    return prior


def memory():
    fields = {line.split(':')[0]: int(line.split()[1]) * 1024
              for line in Path('/proc/meminfo').read_text().splitlines()}
    return {'total': fields['MemTotal'], 'available': fields['MemAvailable'],
            'used': fields['MemTotal'] - fields['MemAvailable'], 'free': fields['MemFree']}


def network_state():
    routes = Path('/proc/net/route').read_text().splitlines()[1:]
    ipv4 = any(len(parts := row.split()) > 3 and parts[1] == '00000000'
               and int(parts[3], 16) & 1 for row in routes)
    ipv6 = any(len(parts := row.split()) >= 10 and parts[0] == '0' * 32 and parts[1] == '00'
               and int(parts[8], 16) & 1 for row in Path('/proc/net/ipv6_route').read_text().splitlines())
    return 'Local only' if ipv4 or ipv6 else 'Offline'


def swap_counters():
    return {parts[0]: int(parts[1]) for line in Path('/proc/vmstat').read_text().splitlines()
            if (parts := line.split())[0] in ('pswpin', 'pswpout', 'oom_kill')}
