"""Browser boundary regressions use existing app routes without model inference."""
import pytest
from fastapi.testclient import TestClient
from showcase_app import operator
from fastapi import FastAPI


@pytest.mark.parametrize('host', ['attacker.invalid', 'localhost.attacker.invalid', '127.0.0.1.attacker.invalid'])
def test_operator_rejects_dns_rebinding_host(host):
    client = TestClient(operator.app, base_url='http://localhost:8080')
    response = client.get('/api/languages', headers={'Host': host})
    assert response.status_code == 400


@pytest.mark.parametrize('host', ['localhost:8080', '127.0.0.1:8080'])
def test_operator_retains_loopback_access(host):
    client = TestClient(operator.app, base_url='http://' + host)
    assert client.get('/api/languages').status_code == 200


def test_only_explicit_private_proxy_hostname_is_allowed(monkeypatch):
    from showcase_app.security import HostGuard
    monkeypatch.setenv('FURY_SERVE_HOSTNAMES', 'fury-demo.internal')
    app = FastAPI()
    app.add_middleware(HostGuard)
    @app.get('/')
    def home():
        return {'ok': True}
    client = TestClient(app, base_url='https://fury-demo.internal')
    assert client.get('/').status_code == 200
    assert client.get('/', headers={'Host': 'another-demo.internal'}).status_code == 400
    assert client.get('/', headers={'Host': 'fury-demo.internal.attacker.invalid'}).status_code == 400


def test_duplicate_host_header_is_not_accepted():
    client = TestClient(operator.app, base_url='http://localhost:8080')
    response = client.get('/api/languages', headers=[('Host', 'localhost'), ('Host', 'attacker.invalid')])
    assert response.status_code == 400


@pytest.mark.parametrize('origin', [
    'https://attacker.invalid', 'http://localhost:9999', 'null',
    'http://localhost:8080@attacker.invalid', 'http://localhost:8080/other',
])
def test_operator_rejects_untrusted_origin_before_work(origin):
    client = TestClient(operator.app, base_url='http://localhost:8080')
    response = client.post('/api/vision', json={}, headers={'Origin': origin})
    assert response.status_code == 403


def test_plain_text_cannot_reset_appearance(monkeypatch, tmp_path):
    monkeypatch.setattr(operator, 'ROOT', tmp_path)
    active = tmp_path / 'state/skin/active.json'
    active.parent.mkdir(parents=True)
    active.write_text('{"fictional": true}')
    client = TestClient(operator.app, base_url='http://localhost:8080')
    response = client.post('/api/appearance/reset', content='{}', headers={
        'Origin': 'http://localhost:8080', 'Content-Type': 'text/plain',
    })
    assert response.status_code == 415
    assert active.exists()


def test_same_origin_json_retains_presenter_reset_without_pin(monkeypatch, tmp_path):
    monkeypatch.setattr(operator, 'ROOT', tmp_path)
    active = tmp_path / 'state/skin/active.json'
    active.parent.mkdir(parents=True)
    active.write_text('{"fictional": true}')
    client = TestClient(operator.app, base_url='http://localhost:8080')
    assert client.post('/api/appearance/reset', json={}, headers={'Origin': 'http://localhost:8080'}).status_code == 200
    assert not active.exists()


def test_security_token_is_not_readable_cross_origin():
    client = TestClient(operator.app, base_url='http://localhost:8080')
    response = client.get('/api/security/csrf-token', headers={'Origin': 'https://attacker.invalid'})
    assert response.status_code == 403


def test_binary_requests_need_token_and_still_check_origin(monkeypatch, tmp_path):
    from fastapi import Request
    from showcase_app import security
    monkeypatch.setattr(security, 'TOKEN_PATH', tmp_path / 'request-token')
    security.csrf_token.cache_clear()
    app = FastAPI()
    app.add_middleware(security.RequestGuard)
    app.add_middleware(security.HostGuard)
    @app.post('/binary')
    async def binary(request: Request):
        return {'bytes': len(await request.body())}
    try:
        client = TestClient(app, base_url='http://localhost:8080')
        response = client.get('/api/security/csrf-token')
        assert response.headers['cache-control'] == 'no-store'
        token = response.json()['token']
        assert client.post('/binary', content=b'fictional', headers={'Content-Type': 'image/png'}).status_code == 415
        headers = {'Content-Type': 'image/png', 'X-Fury-CSRF': token, 'Origin': 'http://localhost:8080'}
        assert client.post('/binary', content=b'fictional', headers=headers).json() == {'bytes': 9}
        headers['Origin'] = 'https://attacker.invalid'
        assert client.post('/binary', content=b'fictional', headers=headers).status_code == 403
        assert (tmp_path / 'request-token').stat().st_mode & 0o777 == 0o600
    finally:
        security.csrf_token.cache_clear()


def test_unsafe_token_storage_fails_closed(monkeypatch, tmp_path):
    from showcase_app import security
    path = tmp_path / 'request-token'
    path.write_text('a' * 64)
    path.chmod(0o644)
    monkeypatch.setattr(security, 'TOKEN_PATH', path)
    security.csrf_token.cache_clear()
    app = FastAPI()
    app.add_middleware(security.RequestGuard)
    try:
        client = TestClient(app, base_url='http://localhost:8080')
        assert client.get('/api/security/csrf-token').status_code == 503
        assert client.post('/binary', content=b'x', headers={'X-Fury-CSRF': 'a' * 64}).status_code == 503
    finally:
        security.csrf_token.cache_clear()


def test_cross_site_websocket_is_closed_before_accept():
    from fastapi import WebSocket
    from starlette.websockets import WebSocketDisconnect
    from showcase_app import security
    app = FastAPI()
    app.add_middleware(security.RequestGuard)
    app.add_middleware(security.HostGuard)
    @app.websocket('/ws')
    async def socket(ws: WebSocket):
        await ws.accept()
        await ws.send_text('accepted')
        await ws.close()
    client = TestClient(app, base_url='http://localhost:8080')
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect('ws://localhost:8080/ws', headers={'Origin': 'https://attacker.invalid'}):
            pass
    assert rejected.value.code == 1008
    with client.websocket_connect('ws://localhost:8080/ws', headers={'Origin': 'http://localhost:8080'}) as accepted:
        assert accepted.receive_text() == 'accepted'


def test_model_lifespan_bounds_native_http_shutdown():
    import asyncio
    from types import SimpleNamespace
    from showcase_app.security import ModelLifecycleGuard
    config=SimpleNamespace(timeout_graceful_shutdown=None)
    app=SimpleNamespace(state=SimpleNamespace(server=SimpleNamespace(config=config)))
    called=[]
    async def inner(scope,receive,send):called.append(scope['type'])
    async def receive():return {'type':'lifespan.startup'}
    async def send(message):pass
    asyncio.run(ModelLifecycleGuard(inner)({'type':'lifespan','app':app},receive,send))
    assert called==['lifespan'] and config.timeout_graceful_shutdown==15
