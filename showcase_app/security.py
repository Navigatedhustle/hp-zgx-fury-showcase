"""Local HTTP boundaries shared by the demo applications and model servers."""
import json
import asyncio
import time
import functools
import hmac
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

LOOPBACK = frozenset(('localhost', '127.0.0.1', '::1'))
PORTS = frozenset((8000, 8001, 8080, 8100, 8200, 8202, 8204, 8501, 8765, 8800, 5173, 8510))
WEB_PORTS = frozenset((443, 8080, 8200, 8501, 8765, 8800))
TOKEN_PATH = Path(__file__).resolve().parents[1] / 'state/request-csrf-token'


def configured_hosts():
    """Only explicit operator configuration; never derive trust from a request."""
    names = set(LOOPBACK)
    for name in os.environ.get('FURY_SERVE_HOSTNAMES', '').split(','):
        name = name.strip().lower()
        if not name:
            continue
        if len(name) > 253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', name):
            raise RuntimeError('Invalid configured private Serve hostname')
        if '..' in name or any(label.startswith('-') or label.endswith('-') for label in name.split('.')):
            raise RuntimeError('Invalid configured private Serve hostname')
        names.add(name)
    return frozenset(names)


def authority(value):
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or any(c in value for c in '/\\?#@,'):
        return None
    try:
        parsed = urlsplit('http://' + value)
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return None
        return parsed.hostname.lower(), port
    except ValueError:
        return None


def origin_allowed(value, hosts=None):
    if not value or value == 'null':
        return False
    hosts = configured_hosts() if hosts is None else hosts
    try:
        parsed = urlsplit(value)
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            return False
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if host not in hosts:
            return False
        if host in LOOPBACK:
            return parsed.scheme == 'http' and port in PORTS
        return parsed.scheme == 'https' and port in WEB_PORTS
    except ValueError:
        return False


async def reject(scope, send, status, detail):
    if scope['type'] == 'websocket':
        await send({'type': 'websocket.close', 'code': 1008, 'reason': detail})
        return
    body = json.dumps({'detail': detail}).encode()
    await send({'type': 'http.response.start', 'status': status, 'headers': [
        (b'content-type', b'application/json'), (b'content-length', str(len(body)).encode()),
        (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
    ]})
    await send({'type': 'http.response.body', 'body': body})


class HostGuard:
    def __init__(self, app):
        self.app = ResourceGuard(BrowserHeaders(app))
        self.hosts = configured_hosts()

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        values = [v.decode('latin1') for k, v in scope['headers'] if k.lower() == b'host']
        target = authority(values[0]) if len(values) == 1 else None
        if target is None or target[0] not in self.hosts:
            return await reject(scope, send, 400, 'Use localhost or the configured private Serve hostname')
        return await self.app(scope, receive, send)


@functools.lru_cache(maxsize=1)
def csrf_token():
    """Distinct from visitor/creative authorization; never reuse those secrets."""
    TOKEN_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not TOKEN_PATH.exists():
        # Publish a complete value atomically across concurrently starting apps.
        with tempfile.NamedTemporaryFile(dir=TOKEN_PATH.parent, prefix='.csrf-', delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(secrets.token_hex(32).encode())
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(temporary, TOKEN_PATH, follow_symlinks=False)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    descriptor = os.open(TOKEN_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
            raise RuntimeError('Unsafe request-token storage')
        value = os.read(descriptor, 65).decode('ascii')
    finally:
        os.close(descriptor)
    if not re.fullmatch('[0-9a-f]{64}', value):
        raise RuntimeError('Invalid request-token storage')
    return value


def csrf_headers():
    """For local service clients that send binary or multipart bodies."""
    return {'X-Fury-CSRF': csrf_token()}


class RequestGuard:
    def __init__(self, app):
        self.app = app
        self.hosts = configured_hosts()

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        origins = [v.decode('latin1') for k, v in scope['headers'] if k.lower() == b'origin']
        headers = {k.lower(): v.decode('latin1') for k, v in scope['headers']}
        if (len(origins) > 1 or (origins and not origin_allowed(origins[0], self.hosts))
                or headers.get(b'sec-fetch-site') == 'cross-site'):
            return await reject(scope, send, 403, 'Use the controls on an allowed local station')
        if scope['type'] == 'websocket':
            # Native local clients may omit Origin; browser origins are exact-checked.
            return await self.app(scope, receive, send)
        if scope['path'] == '/api/security/csrf-token' and scope['method'] == 'GET':
            try:
                body = json.dumps({'token': csrf_token()}).encode()
            except (OSError, ValueError, RuntimeError, UnicodeError):
                return await reject(scope, send, 503, 'Request protection is unavailable; ask the operator')
            await send({'type': 'http.response.start', 'status': 200, 'headers': [
                (b'content-type', b'application/json'), (b'cache-control', b'no-store'),
                (b'x-content-type-options', b'nosniff'), (b'content-length', str(len(body)).encode()),
            ]})
            return await send({'type': 'http.response.body', 'body': body})
        if scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
            kind = headers.get(b'content-type', '').split(';', 1)[0].strip().lower()
            is_json = kind == 'application/json' or (kind.startswith('application/') and kind.endswith('+json'))
            if not is_json:
                token = headers.get(b'x-fury-csrf', '')
                try:
                    valid = bool(re.fullmatch('[0-9a-f]{64}', token)) and hmac.compare_digest(token, csrf_token())
                except (OSError, ValueError, RuntimeError, UnicodeError):
                    return await reject(scope, send, 503, 'Request protection is unavailable; ask the operator')
                if not valid:
                    return await reject(scope, send, 415, 'Use JSON or the station request token')
        return await self.app(scope, receive, send)


# Model-authored slide scripts are deliberately supported, inside an opaque origin.
DOCUMENT_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; "
                "object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; "
                "form-action 'none'; sandbox allow-scripts allow-modals")


class GeneratedDocumentGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def protected(message):
            if message['type'] == 'http.response.start' and scope.get('path', '').startswith('/api/'):
                headers = list(message.get('headers', []))
                if any(k.lower() == b'content-type' and b'text/html' in v for k, v in headers):
                    headers = [(k, v) for k, v in headers if k.lower() not in (b'content-security-policy', b'cache-control')]
                    headers += [(b'content-security-policy', DOCUMENT_CSP.encode()), (b'cache-control', b'no-store')]
                    message = {**message, 'headers': headers}
            await send(message)
        return await self.app(scope, receive, protected)


class BrowserHeaders:
    """Apply browser defaults without relaxing any application-specific CSP."""
    def __init__(self, app):
        self.app = app
        self.hosts = configured_hosts()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        target = authority(next((v.decode('latin1') for k,v in scope['headers'] if k.lower()==b'host'), ''))
        host = target[0] if target else 'localhost'
        port = target[1] if target and target[1] else scope.get('server', ('',80))[1]
        path = scope.get('path','/')
        from showcase_app.frame_policy import station_ancestors
        origins = [f'http://{name}:{p}' for name in ('localhost','127.0.0.1') for p in WEB_PORTS if p != 443]
        origins += [f'https://{name}' + (f':{p}' if p != 443 else '') for name in sorted(self.hosts-LOOPBACK) for p in WEB_PORTS]
        policy = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                  "img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; "
                  "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
                  "frame-src 'self' " + ' '.join(origins) + "; frame-ancestors " + station_ancestors(host))
        camera = 'self' if port == 8080 and path in ('/experience/trailer','/experience/vision','/','/demos') else ''
        microphone = 'self' if port == 8200 else ''
        if port == 8080 and path in ('/','/demos'):
            microphone = ' '.join('"'+o+'"' for o in origins if o.endswith(':8200'))
        permissions = f'camera=({camera}), microphone=({microphone}), geolocation=(), payment=(), usb=(), serial=(), bluetooth=()'
        async def protected(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                present = {k.lower() for k,v in headers}
                defaults = {b'x-content-type-options': b'nosniff', b'referrer-policy': b'no-referrer',
                            b'permissions-policy': permissions.encode(), b'content-security-policy': policy.encode()}
                headers += [(k,v) for k,v in defaults.items() if k not in present]
                # Shared/customer/visitor responses never enter a browser disk cache.
                if not path.startswith(('/showcase-assets/','/assets/','/static/')):
                    headers = [(k,v) for k,v in headers if k.lower()!=b'cache-control']
                    headers.append((b'cache-control', b'no-store'))
                message = {**message, 'headers': headers}
            await send(message)
        return await self.app(scope, receive, protected)


class ResourceGuard:
    """Bound request parsing and held connections before framework allocation."""
    def __init__(self, app):
        self.app=app
        self.http=0; self.streams=0; self.websockets=0; self.uploads=0
        self.upload_rates={}

    async def __call__(self, scope, receive, send):
        kind=scope['type']
        if kind not in ('http','websocket'):
            return await self.app(scope,receive,send)
        headers={k.lower():v.decode('latin1') for k,v in scope['headers']}
        path=scope.get('path','')
        streaming=kind=='http' and (any(x in path for x in ('/events','/stream','/stages/','telemetry')) or 'text/event-stream' in headers.get(b'accept',''))
        upload=kind=='http' and scope.get('method') in ('POST','PUT','PATCH') and headers.get(b'content-type','').startswith(('multipart/','application/octet-stream','image/'))
        maximum=320*1024**2 if path in ('/api/projects','/api/library/upload') else 16*1024**2
        if path.startswith('/skin/'):maximum=2*1024**2
        if path=='/api/translate':maximum=9*1024**2
        if path.startswith('/api/projects/') and path.endswith('/docs'):maximum=52*1024**2
        if kind=='http':
            try:
                values=[v for k,v in scope['headers'] if k.lower()==b'content-length']
                if len(values)>1:raise ValueError()
                length=int(values[0]) if values else 0
                if length<0:raise ValueError()
            except ValueError:
                return await reject(scope,send,400,'Invalid request length')
            if length>maximum:return await reject(scope,send,413,'Request exceeds the supported size')
        if self.http>=64 or (streaming and self.streams>=24) or (kind=='websocket' and self.websockets>=8) or (upload and self.uploads>=4):
            return await reject(scope,send,429,'This station is busy; retry shortly')
        if upload:
            peer=(scope.get('client') or ('local',0))[0];now=time.monotonic()
            tokens,at=self.upload_rates.get(peer,(12,now));tokens=min(12,tokens+(now-at)*.5)
            if tokens<1:return await reject(scope,send,429,'Upload rate limit reached; retry shortly')
            if peer not in self.upload_rates and len(self.upload_rates)>=128:self.upload_rates.pop(next(iter(self.upload_rates)))
            self.upload_rates[peer]=(tokens-1,now)
        self.http+=kind=='http';self.websockets+=kind=='websocket';self.streams+=streaming;self.uploads+=upload
        size=0;deadline=time.monotonic()+120;body_done=False
        async def bounded_receive():
            nonlocal size,body_done
            from starlette.exceptions import HTTPException
            if kind=='http' and body_done:return await receive()
            timeout=min(30,max(.01,deadline-time.monotonic())) if kind=='http' else 60
            try:message=await asyncio.wait_for(receive(),timeout)
            except TimeoutError:
                if kind=='websocket':return {'type':'websocket.disconnect','code':1008}
                raise HTTPException(408,'Request upload timed out')
            if message['type']=='http.request':
                body_done=not message.get('more_body',False)
                size+=len(message.get('body',b''))
                if size>maximum:raise HTTPException(413,'Request exceeds the supported size')
            if message['type']=='websocket.receive' and (len(message.get('bytes') or b'')>2000000 or len(message.get('text') or '')>8192):
                await send({'type':'websocket.close','code':1009})
                return {'type':'websocket.disconnect','code':1009}
            return message
        async def bounded_send(message):
            await asyncio.wait_for(send(message),15)
        try:
            return await self.app(scope,bounded_receive,bounded_send)
        finally:
            self.http-=kind=='http';self.websockets-=kind=='websocket';self.streams-=streaming;self.uploads-=upload
