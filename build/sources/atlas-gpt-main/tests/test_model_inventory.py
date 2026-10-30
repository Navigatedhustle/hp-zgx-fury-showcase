"""Two booth screens cannot duplicate a model in shared asynchronous discovery."""
import asyncio
import httpx
from atlas import server


def test_concurrent_model_discovery_keeps_each_engine_once(monkeypatch):
    client_type = httpx.AsyncClient
    async def response(request):
        if request.url.port == 8202:
            await asyncio.sleep(.005)
            data = {'data': [{'id': 'local-recognizer', 'capability': 'transcription'}]}
        elif request.url.port == 8204:
            await asyncio.sleep(.025)
            data = {'data': [{'id': 'local-voice', 'capability': 'speech', 'latency_ms': 123}]}
        else:
            data = {'ready': True, 'model': 'local-detector', 'latency_ms': 8}
        return httpx.Response(200, json=data)
    def client(**kwargs):
        return client_type(transport=httpx.MockTransport(response), **kwargs)
    async def offline_model(): return False
    monkeypatch.setattr(server.httpx, 'AsyncClient', client)
    monkeypatch.setattr(server.brain, 'health', offline_model)
    monkeypatch.setattr(server.decisions, 'health', offline_model)
    monkeypatch.setattr(server.brain, 'loaded', False)
    monkeypatch.setattr(server.decisions, 'loaded', False)
    monkeypatch.setattr(server.telemetry, 'read', lambda: {})
    async def collect(): return await asyncio.gather(server.stats(), server.stats())
    for result in asyncio.run(collect()):
        names = [model['name'] for model in result['models']]
        assert names.count('local-voice') == 1
        assert names.count('local-recognizer') == 1
        voice = next(model for model in result['models'] if model['name'] == 'local-voice')
        assert voice['latency_ms'] == 123
