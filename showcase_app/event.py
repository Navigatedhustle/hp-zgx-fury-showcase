"""Shared, inference-free event telemetry. Runtime state is never publication input."""
import asyncio
import hmac
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'state/event-session.sqlite'
PRICING = ROOT / 'config/event-pricing.json'
SAMPLE_SECONDS = 2
TEXT_DEMOS = ('atlas','slides','agent','vision','translate','trailer')
MAX_POWER_GAP = 20


def presenter_key_path():
    # Credentials stay outside the repository, including outside ignored runtime dirs.
    return Path(os.environ.get('FURY_PRESENTER_KEY_FILE', str(Path.home() / '.config/fury-showcase/presenter.key')))


def presenter_key(create=False):
    path = presenter_key_path()
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_urlsafe(24))
    return path.read_text().strip() if path.is_file() else None


def authorized(value):
    key = presenter_key()
    return bool(key and value and hmac.compare_digest(key, value))


def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def prices(today=None):
    data = json.loads(PRICING.read_text())
    today = today or date.today()
    for model in data['models']:
        if model.get('effective_until') and today > date.fromisoformat(model['effective_until']):
            model.update(input=model['subsequent_input'], output=model['subsequent_output'])
    return data


def price_rows(rows, models):
    # The gateway's events primary key is the physical upstream call identity.
    # Source ledgers upsert that same ID; their token totals are never added again.
    eligible = {r['id']: r for r in rows if r.get('demo') in TEXT_DEMOS
                and r.get('status') in ('complete', 'failed', 'cancelled')
                and number(r.get('input_tokens')) and number(r.get('output_tokens'))}
    costs = {}
    for model in models:
        total = 0
        for row in eligible.values():
            long = row['input_tokens'] > model.get('long_threshold', math.inf)
            i, o = (model['long_input'], model['long_output']) if long else (model['input'], model['output'])
            total += (row['input_tokens'] * i + row['output_tokens'] * o) / 1e6
        costs[model['id']] = total
    return eligible, costs


class Store:
    def __init__(self, path=DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, name TEXT, started REAL);
                CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, current TEXT);
                CREATE TABLE IF NOT EXISTS samples(session TEXT, at REAL, payload TEXT,
                  PRIMARY KEY(session,at));
            ''')
            if not db.execute('SELECT current FROM settings WHERE id=1').fetchone():
                self.reset('Conference session', db=db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def reset(self, name, db=None):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Use an event name between 1 and 80 characters.')
        if db is None:
            with self.connect() as connection:
                return self.reset(name, db=connection)
        session = {'id': secrets.token_hex(8), 'name': name.strip(), 'started': time.time()}
        db.execute('INSERT INTO sessions VALUES (:id,:name,:started)', session)
        db.execute('INSERT OR REPLACE INTO settings VALUES (1,?)', (session['id'],))
        if self.path == DB:
            from showcase_app.skin import reset
            reset()
        return session

    def current(self):
        with self.connect() as db:
            return dict(db.execute('SELECT s.* FROM sessions s JOIN settings c ON c.current=s.id WHERE c.id=1').fetchone())

    def history(self, session):
        with self.connect() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM samples WHERE session=? ORDER BY at', (session,))]
        # Bound display history while preserving first/last cumulative observations.
        if len(rows) > 360:
            stride = math.ceil(len(rows) / 358)
            rows = [rows[0], *rows[1:-1:stride], rows[-1]]
        return rows

    def append(self, session, row):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO samples VALUES (?,?,?)', (session, row['at'], json.dumps(row)))


def read_power(live, now):
    meter = os.environ.get('FURY_POWER_METER_FILE')
    if meter:
        try:
            value = json.loads(Path(meter).read_text())
            if number(value.get('watts')) and number(value.get('timestamp')) and 0 <= now - value['timestamp'] <= 15:
                return {'watts': value['watts'], 'scope': 'whole system', 'source': 'configured wall meter'}
        except (OSError, ValueError, TypeError):
            pass
        # A configured meter failing must not silently become a different measurement scope.
        return {'watts': None, 'scope': 'whole system', 'source': 'configured wall meter unavailable'}
    try:
        readings = [float(line.split(',')[2]) for line in live['gpu_memory_MiB_util_pct_power_W'].splitlines()]
        watts = sum(readings)
        if readings and all(number(value) for value in readings):
            return {'watts': watts, 'scope': 'GPU only', 'source': 'nvidia-smi power.draw'}
    except (KeyError, ValueError, IndexError, TypeError):
        pass
    return {'watts': None, 'scope': 'GPU only', 'source': 'GPU telemetry unavailable'}


class Monitor:
    def __init__(self, store=None):
        self.store = store or Store()
        self.latest_live = None
        self.latest = None
        self.previous_power = None
        self.session_id = None
        self.lock = asyncio.Lock()
        self.changed = asyncio.Condition()
        self.stream = None

    def snapshot(self, live, now=None):
        now = now or time.time()
        session = self.store.current()
        history = self.store.history(session['id'])
        prior = history[-1] if history else {}
        if session['id'] != self.session_id:
            self.previous_power = None
            self.session_id = session['id']
        pricing = prices()
        with sqlite3.connect('file:'+str(ROOT/'state/slides/app.db')+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute('SELECT * FROM events WHERE started>=?', (session['started'],))]
        eligible, costs = price_rows(rows, pricing['models'])
        known = {r['id']: r for r in rows if r['demo'] in TEXT_DEMOS and number(r.get('output_tokens')) and r['status'] in ('complete', 'failed', 'cancelled')}
        power = read_power(live, now)
        energies = dict(prior.get('energies_kwh', {}))
        coverage = dict(prior.get('coverage_seconds', {}))
        if self.previous_power and power['watts'] is not None:
            at, watts, scope = self.previous_power
            delta = now - at
            if scope == power['scope'] and 0 < delta <= MAX_POWER_GAP:
                energies[scope] = energies.get(scope, 0) + (watts + power['watts']) * .5 * delta / 3_600_000
                coverage[scope] = coverage.get(scope, 0) + delta
        self.previous_power = (now, power['watts'], power['scope']) if power['watts'] is not None else None
        language = live.get('services', {}).get('language', {})
        gateway = language.get('data', {})
        image = live.get('services', {}).get('image', {})
        image_data = image.get('data', {})
        text_active = list(gateway.get('active', {}).values())
        point = {'at': now, 'input': sum(r['input_tokens'] for r in eligible.values()),
                 'output': sum(r['output_tokens'] for r in known.values()), 'requests': len(eligible),
                 'api_usd': costs, 'energies_kwh': energies, 'coverage_seconds': coverage}
        self.store.append(session['id'], point)
        activity = {demo: {'active': sum(r.get('demo') == demo for r in text_active),
                           'queued': sum(r.get('demo') == demo for r in gateway.get('queued', {}).values())}
                    for demo in ('atlas', 'slides', 'agent')}
        activity['image'] = {'active': image_data.get('active'), 'queued': image_data.get('queued')}
        jobs = live.get('services', {}).get('factory_jobs', {}).get('data', {})
        booth = live.get('services', {}).get('presentation_jobs', {}).get('data', {})
        if not language.get('connected'):
            for demo in ('atlas', 'slides', 'agent'):
                activity[demo] = {'active': None, 'queued': None}
        return {'timestamp': now, 'session': session, 'totals': point, 'history': [*history, point],
                'power': power, 'pricing': pricing, 'activity': activity,
                'capacity': {'agent': {'active': jobs.get('active'), 'limit': jobs.get('limit')},
                             'slides': {'active': booth.get('active'), 'pending': booth.get('pending'), 'limit': booth.get('limit')}},
                'unknown_usage_requests': sum(r['demo'] in TEXT_DEMOS and r['status'] in ('complete','failed','cancelled') and (not number(r.get('input_tokens')) or not number(r.get('output_tokens'))) for r in rows),
                'services': {k: {'connected': v.get('connected'), 'ready': v.get('ready')} for k,v in live.get('services',{}).items()},
                'recorded_activity_included': False, 'collection_interval_seconds': SAMPLE_SECONDS,
                'token_scope': 'Reported endpoint usage for unique terminal live requests started since this event reset, including failed calls when final usage is available. Recorded playback excluded. API estimates require both input and output usage.',
                'energy_scope': 'Trapezoidal integration between actual samples; gaps over 20 seconds and missing readings excluded. Includes session idle GPU power. GPU-only energy excludes CPU, cooling and other host electricity.'}

    async def refresh(self, collect):
        async with self.lock:
            live = await collect()
            self.latest_live = live
            self.latest = await asyncio.to_thread(self.snapshot, live)
            self.stream = json.dumps({'telemetry':live.get('telemetry'),'event':self.latest,'skin':live.get('skin')},separators=(',',':'))
        async with self.changed:self.changed.notify_all()

    async def run(self, collect):
        while True:
            began = time.monotonic()
            try:
                await self.refresh(collect)
            except Exception:
                # Retain timestamp so clients can visibly reject stale measurements.
                import logging
                logging.exception('Event telemetry collection failed')
            await asyncio.sleep(max(0.05,SAMPLE_SECONDS-(time.monotonic()-began)))
