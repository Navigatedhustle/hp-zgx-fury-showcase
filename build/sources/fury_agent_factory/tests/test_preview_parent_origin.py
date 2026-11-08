"""Opaque preview bridge checks origin as well as the expected Window object."""
import asyncio
from playwright.sync_api import sync_playwright
import devteam_routes


def test_preview_ignores_wrong_origin_result_and_accepts_its_parent(monkeypatch):
    async def fixture(*args):
        return {'html': '<h1>Fictional fixture</h1>', 'css': '', 'js': '', 'version': {'version': 1}, 'run_id': 'fixture'}
    monkeypatch.setattr(devteam_routes, 'preview', fixture)
    response = asyncio.run(devteam_routes.preview_frame())
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'])
        try:
            page = browser.new_page()
            page.route('**/__guard_parent', lambda route: route.fulfill(content_type='text/html', body='''
            <iframe id="frame" sandbox="allow-scripts" src="/__guard_frame"></iframe>
            <script>window.addEventListener('message',e=>{if(e.source===document.getElementById('frame').contentWindow&&e.data?.kind==='fury-api')window.requestId=e.data.id});</script>'''))
            page.route('**/__guard_frame', lambda route: route.fulfill(status=200, headers=dict(response.headers), body=response.body))
            page.goto('http://localhost:8501/__guard_parent')
            child = page.frames[1]
            child.wait_for_function('typeof window.furyApi === "function"')
            child.evaluate("()=>{window.result=null;window.furyApi('GET','/hotels').then(v=>window.result=v)}")
            page.wait_for_function('window.requestId === 1')
            child.evaluate("dispatchEvent(new MessageEvent('message',{source:parent,origin:'https://attacker.invalid',data:{kind:'fury-result',id:1,response:{forged:true}}}))")
            page.wait_for_timeout(100)
            assert child.evaluate('window.result') is None
            page.evaluate("document.getElementById('frame').contentWindow.postMessage({kind:'fury-result',id:1,response:{legitimate:true}},'*')")
            child.wait_for_function('window.result?.legitimate === true')
        finally:
            browser.close()
