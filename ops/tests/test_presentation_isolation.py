"""Real browser proof for model-authored presentation code and its editing bridge."""
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build/sources/html_builder-main/backend'))


def test_model_script_cannot_read_parent_or_call_local_api_but_editor_works():
    from app import assemble as a
    from app.spec import parse_spec
    from playwright.sync_api import sync_playwright
    spec, _ = parse_spec('<meta>{"steps":1}</meta><html><h1 data-eid="title">Fictional deck</h1></html><css></css><script></script>', 's1')
    spec.js = '''function mount(){
      window.probe={executed:true,parentRead:false,storage:false};
      try{window.parent.document.body.dataset.compromised='yes';probe.parentRead=true}catch{}
      try{localStorage.setItem('probe','yes');probe.storage=true}catch{}
      fetch('/api/mutate',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});
    }'''
    html = a.assemble(a.DeckInput('Fictional deck', [a.DeckSlide('s1', spec)]), embed=True).encode()
    ts = (ROOT/'build/sources/html_builder-main/frontend/src/components/SlideFrame.tsx').read_text()
    sandbox = re.search('sandbox="([^"]+)"', ts).group(1)
    mutations = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            if self.path.startswith('/deck'):
                self.send_header('Content-Security-Policy', getattr(a, 'DOCUMENT_CSP', ''))
                body = html
            else:
                body = ("<script>window.messages=[];addEventListener('message',e=>{if(e.source===document.querySelector('iframe').contentWindow)messages.push({origin:e.origin,data:e.data})});</script>"
                        + '<iframe sandbox="'+sandbox+'" src="/deck"></iframe>').encode()
            self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            mutations.append(self.path); self.send_response(200); self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto('http://127.0.0.1:'+str(server.server_port))
            frame = page.frames[1]
            frame.wait_for_function('window.probe?.executed')
            page.wait_for_timeout(200)
            probe = frame.evaluate('probe')
            assert not probe['parentRead'], 'Model JavaScript can access the application parent DOM'
            assert not probe['storage'], 'Generated scripts retain the application storage origin'
            assert mutations == [], 'Generated code reached a local API'
            page.evaluate("document.querySelector('iframe').contentWindow.postMessage({type:'hpdeck',cmd:'edit',on:true},'*')")
            frame.wait_for_selector('#hp-edit', state='attached')
            assert page.evaluate("messages.some(m=>m.origin==='null'&&m.data.event==='state')")
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
