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
