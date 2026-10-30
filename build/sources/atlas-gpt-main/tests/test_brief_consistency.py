"""A brief must belong to the displayed answer, even with multiple clients."""
from fastapi.testclient import TestClient
from atlas import server, briefs


def test_brief_keeps_the_answer_selected_by_its_client(monkeypatch):
    async def no_model(): return False
    async def no_judgment(output): return None
    monkeypatch.setattr(server.brain, 'health', no_model)
    monkeypatch.setattr(server.decisions, 'health', no_model)
    monkeypatch.setattr(server.decisions, 'judge', no_judgment)
    monkeypatch.setattr(briefs, 'export', lambda result: {'question': result['question']})
    with TestClient(server.app) as client:
        first = client.post('/api/query', json={'question': "What's our projected Q4 revenue and profit?", 'fast': True, 'llm_narration': False}).json()
        second = client.post('/api/query', json={'question': 'How many reps do we need to hire?', 'fast': True, 'llm_narration': False}).json()
        assert first['result_id'] != second['result_id']
        brief = client.post('/api/brief', json={'question': first['question'], 'result_id': first['result_id']})
        assert brief.status_code == 200
        assert brief.json()['question'] == first['question']
        spoken = client.post('/api/query', json={'question': 'send me that', 'result_id': first['result_id'], 'fast': True}).json()
        assert spoken['artifacts']['question'] == first['question']
        wrong_persona = client.post('/api/brief', json={'question': first['question'], 'persona': 'university', 'result_id': first['result_id']})
        assert wrong_persona.status_code == 409
        expired = client.post('/api/brief', json={'question': first['question'], 'result_id': 'unknown-answer'})
        assert expired.status_code == 409
