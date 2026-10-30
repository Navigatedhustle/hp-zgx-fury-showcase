"""Synthetic loopback HTTP fixtures. Not a model or hardware benchmark."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from engine import Run, Settings, cloud_cost, normalise_usage, load_evidence

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        model=payload['model']
        with self.server.lock:
            self.server.active+=1
            self.server.peak=max(self.server.peak,self.server.active)
        try:
            time.sleep(0.12 if model!='slow' else 1.0)
            if model=='error':
                self.send_response(503); self.end_headers(); return
            usage=None if model=='missing' else {'prompt_tokens':100,'completion_tokens':20,
                                                'prompt_tokens_details':{'cached_tokens':50}}
            finish='length' if model=='truncated' else 'stop'
            if payload.get('stream'):
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.end_headers()
                chunks=[{'choices':[{'delta':{'content':'SYNTHETIC TEST OUTPUT [DATA:S1]'},'finish_reason':None}]},
                        {'choices':[{'delta':{},'finish_reason':finish}]},
                        {'choices':[],'usage':usage}]
                for chunk in chunks:
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            else:
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'message':{'content':'SYNTHETIC TEST OUTPUT [DATA:S1]'},'finish_reason':finish}], 'usage':usage}).encode())
        except (BrokenPipeError,ConnectionResetError):
            pass
        finally:
            with self.server.lock: self.server.active-=1

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.lock=threading.Lock(); self.server.active=0; self.server.peak=0
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/v1'
        self.rates=dict(enabled=True,input=2.0,output=10.0,cached=0.2,cloud_cache_fraction=0.0)
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()
    def run_case(self,model='test',stream=True,workflows=1,cap=3):
        run=Run(Settings(self.url,model,max_inflight=cap,stream=stream),self.rates,
                workflows=workflows,output_dir=self.tmp.name)
        run.start(); run.thread.join(timeout=15)
        self.assertFalse(run.thread.is_alive())
        return run,run.snapshot()
    def test_streaming_and_empty_usage_choices(self):
        run,s=self.run_case()
        self.assertEqual(s['completed'],1); self.assertEqual(len(s['calls']),5)
        self.assertEqual(s['input'],500); self.assertEqual(s['output'],100)
        self.assertAlmostEqual(s['cost'],0.002)
        self.assertEqual(s['unknown_usage_calls'],0)
        self.assertTrue(all(c['ttft_s'] is not None for c in s['calls']))
        with sqlite3.connect(run.db_path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM calls').fetchone()[0],5)
    def test_nonstreaming(self):
        _,s=self.run_case(stream=False)
        self.assertEqual(s['completed'],1); self.assertEqual(s['input'],500)
        self.assertTrue(all(c['ttft_s'] is None for c in s['calls']))
    def test_missing_usage_stays_unknown(self):
        _,s=self.run_case(model='missing')
        self.assertEqual(s['completed'],1); self.assertEqual(s['unknown_usage_calls'],5)
        self.assertTrue(all(c['usage'] is None for c in s['calls']))
    def test_concurrency_cap_and_real_overlap(self):
        _,s=self.run_case(workflows=3,cap=2)
        self.assertEqual(s['completed'],3); self.assertEqual(len(s['calls']),15)
        self.assertEqual(self.server.peak,2)
        for wid in ('1','2','3'):
            calls=[c for c in s['calls'] if c['workflow']==wid]
            writer=next(c for c in calls if c['agent']=='Report writer')
            analysts=[c for c in calls if c['agent'] in ('Document analyst','Data analyst','Policy checker')]
            self.assertGreaterEqual(writer['started_at'],max(c['ended_at'] for c in analysts))
    def test_http_failure_skips_downstream(self):
        _,s=self.run_case(model='error')
        self.assertEqual(s['completed'],0); self.assertEqual(len(s['calls']),3)
        self.assertTrue(all(c['status']=='failed' for c in s['calls']))
    def test_truncation_is_not_success(self):
        _,s=self.run_case(model='truncated')
        self.assertEqual(s['completed'],0); self.assertEqual(len(s['calls']),3)
        self.assertEqual(s['input'],300)
    def test_cancellation_preserves_unknown(self):
        run=Run(Settings(self.url,'slow',max_inflight=1),self.rates,workflows=3,output_dir=self.tmp.name)
        run.start()
        deadline=time.monotonic()+5
        while run.snapshot()['inflight']==0 and time.monotonic()<deadline:
            time.sleep(0.01)
        self.assertGreater(run.snapshot()['inflight'],0)
        run.stop(); run.thread.join(timeout=5)
        self.assertFalse(run.thread.is_alive())
        s=run.snapshot(); self.assertEqual(s['state'],'stopped')
        self.assertEqual(s['inflight'],0); self.assertEqual(s['queued'],0)
        self.assertTrue(any(c['status']=='cancelled' for c in s['calls']))
    def test_usage_validation(self):
        self.assertIsNone(normalise_usage(None))
        self.assertIsNone(normalise_usage({'prompt_tokens':-1,'completion_tokens':20}))
        self.assertIsNone(normalise_usage({'prompt_tokens':True,'completion_tokens':20}))
    def test_local_cache_does_not_reduce_cloud_cost(self):
        rows=[{'usage':{'input':1000000,'output':0,'cached':1000000}}]
        self.assertEqual(cloud_cost(rows,self.rates),2.0)
        r=dict(self.rates,cloud_cache_fraction=0.5)
        self.assertAlmostEqual(cloud_cost(rows,r),1.1)
        self.assertIsNone(cloud_cost(rows,{'enabled':False}))
    def test_fixture_math(self):
        rows=load_evidence()['comparison']
        self.assertEqual(rows[0]['goods_cost_gbp'],37920)
        self.assertEqual(rows[0]['delivered_cost_gbp'],38340)
        self.assertEqual([r['id'] for r in rows if r['passes_all_supplied_checks']],['S1'])
    def test_invalid_endpoint_rejected(self):
        with self.assertRaises(ValueError): Settings('file:///etc/passwd','test').validate()
        with self.assertRaises(ValueError): Settings(self.url,'replace-with-model').validate()

if __name__=='__main__': unittest.main()
