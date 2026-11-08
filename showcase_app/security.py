"""Exact Host validation for local apps and configured private Serve hostnames."""

import json

import os

import re

from urllib.parse import urlsplit

LOOPBACK = frozenset(('localhost', '127.0.0.1', '::1'))

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
        self.app = app
        self.hosts = configured_hosts()

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        values = [v.decode('latin1') for k, v in scope['headers'] if k.lower() == b'host']
        target = authority(values[0]) if len(values) == 1 else None
        if target is None or target[0] not in self.hosts:
            return await reject(scope, send, 400, 'Use localhost or the configured private Serve hostname')
        return await self.app(scope, receive, send)
