from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from showcase_app.security import HostGuard


def client(port=8080):
    app=FastAPI()
    @app.get('/{path:path}')
    def page(path): return HTMLResponse('<h1>Fictional content</h1>')
    app.add_middleware(HostGuard)
    return TestClient(app,base_url='http://localhost:'+str(port))


def test_browser_headers_and_private_caching():
    response=client().get('/api/skin/current')
    assert response.headers.get('x-content-type-options')=='nosniff'
    assert response.headers.get('referrer-policy')=='no-referrer'
    assert response.headers.get('cache-control')=='no-store'
    csp=response.headers.get('content-security-policy','')
    assert "script-src 'self'" in csp and "object-src 'none'" in csp
    assert "frame-ancestors 'self' http://localhost:8080 http://127.0.0.1:8080" in csp


def test_device_permissions_follow_the_actual_workload():
    assert 'camera=(self)' in client().get('/experience/trailer').headers.get('permissions-policy','')
    assert 'camera=()' in client().get('/experience/translate').headers.get('permissions-policy','')
    assert 'microphone=(self)' in client(8200).get('/').headers.get('permissions-policy','')
    assert 'microphone=()' in client(8501).get('/devteam').headers.get('permissions-policy','')
