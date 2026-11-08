import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from showcase_app.security import HostGuard
from showcase_app.visitor_store import VisitorStore


def test_declared_and_chunked_bodies_are_bounded_before_parsing():
    app=FastAPI(); consumed=[]
    @app.post('/api/translate')
    async def upload(request:Request):
        consumed.append(True)
        return {'bytes':len(await request.body())}
    app.add_middleware(HostGuard)
    c=TestClient(app,base_url='http://localhost:8080')
    r=c.post('/api/translate',content=b'{}',headers={'Content-Type':'application/json','Content-Length':str(1024**3)})
    assert r.status_code==413 and not consumed
    r=c.post('/api/translate',content=(b'x'*1024**2 for _ in range(10)),headers={'Content-Type':'application/octet-stream'})
    assert r.status_code==413
    assert c.post('/api/translate',content=b'fictional small document').status_code==200


def test_empty_consent_sessions_have_an_admission_cap(tmp_path):
    store=VisitorStore(tmp_path/'visitors')
    try:
        for _ in range(64):store.consent()
        with pytest.raises(ValueError,match='full'):store.consent()
        assert len(list(store.root.iterdir()))==64
    finally:store.start()
