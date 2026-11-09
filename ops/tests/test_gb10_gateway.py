"""GB10 routing/accounting failure fixtures; hardware qualification is separate."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    spec = importlib.util.spec_from_file_location('gb10_gateway_fixture', ROOT / 'showcase_app/gateway.py')
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    g.DB = tmp_path / 'usage.sqlite'
    g.connect().close()
    return g


def test_busy_lead_routes_non_agent_visibly_and_logs_it(gateway, monkeypatch):
    g = gateway
    real = httpx.AsyncClient
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Fixture response'}}],
                                         'usage': {'prompt_tokens': 5, 'completion_tokens': 2}})

    monkeypatch.setattr(g.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with TestClient(g.app) as client:
        g.active['agent-fixture'] = {'demo': 'stage_agent', 'model': g.LEAD}
        try:
            response = client.post('/stage/rush/v1/chat/completions', json={'model': g.LEAD,
                'messages': [{'role': 'user', 'content': 'Fixture'}], 'max_tokens': 8})
        finally:
            g.active.clear()
    assert response.status_code == 200
    route = response.json()['fury_routing']
    assert route == {'requested': g.LEAD, 'model': g.MODEL, 'reason': 'Routed to Qwen3.6: gpt-oss-120b is busy'}
    assert sent[0]['model'] == g.MODEL
    with g.connect() as db:
        assert db.execute('SELECT requested,actual,reason,external_calls FROM routing').fetchone() == (g.LEAD, g.MODEL, route['reason'], 0)
    assert (g.total._value, g.normal._value, g.lead_slots._value, g.text_slots._value) == (5, 5, 2, 3)


def test_unknown_alias_and_foreign_origin_cannot_reach_any_backend(gateway):
    with TestClient(gateway.app) as client:
        payload = {'model': 'substitute', 'messages': []}
        assert client.post('/stage/rush/v1/chat/completions', json=payload).status_code == 400
        payload['model'] = gateway.LEAD
        assert client.post('/stage/agent/v1/chat/completions', json=payload,
                           headers={'origin': 'https://foreign.invalid'}).status_code == 403
    with gateway.connect() as db:
        assert db.execute('SELECT count(*) FROM routing').fetchone()[0] == 0


def test_keepalive_is_bounded_and_tagged_outside_live_accounting(gateway, monkeypatch):
    g = gateway
    real = httpx.AsyncClient
    monkeypatch.setattr(g.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={'choices': [], 'usage': {'prompt_tokens': 4, 'completion_tokens': 2}})), **kw))
    payload = {'model': g.MODEL, 'messages': [{'role': 'user', 'content': 'Warm'}], 'max_tokens': 8}
    headers = {'x-stage-purpose': 'keepalive', 'x-stage-run': 'idle-fixture'}
    with TestClient(g.app) as client:
        assert client.post('/stage/keepalive/v1/chat/completions', json={**payload, 'max_tokens': 9}, headers=headers).status_code == 422
        assert client.post('/stage/keepalive/v1/chat/completions', json=payload, headers=headers).status_code == 200
    with g.connect() as db:
        assert db.execute('SELECT output_tokens,purpose FROM events').fetchone() == (2, 'keepalive')
        assert db.execute("SELECT coalesce(sum(output_tokens),0) FROM events WHERE purpose='live'").fetchone()[0] == 0
