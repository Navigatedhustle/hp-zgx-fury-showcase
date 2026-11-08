"""Synthetic loopback fixtures test behaviour; they are never shown as Fury performance."""
import json,sqlite3,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from fastapi.testclient import TestClient
from engine import Settings
from backoffice import CoordinatedRun,ROLES
from scenario import load_evidence

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));mode=payload['model'];role=self.headers['X-Fury-Role']
        with self.server.lock:self.server.active+=1;self.server.peak=max(self.server.peak,self.server.active)
        try:
            time.sleep(.15 if mode!='slow' else 1.5)
            refs=json.loads(payload['messages'][1]['content'])['evidence']['source_refs']
            obj={'summary':'The supplied records identify a candidate for review.','source_refs':refs,'uncertainties':['Stock needs confirmation.']}
            if role=='Coordinator synthesis':obj={'recommended_supplier_id':'S1','rationale':'Quillstone meets all supplied checks at GBP 38,340.','tradeoffs':['Marrowbay Fabrication is cheaper but late.','Juniper Arc Supply is faster but over budget with missing certificate evidence.'],'uncertainties':['Stock and tax require confirmation.'],'source_refs':['DATA:S1','DATA:S2','DATA:S3','POLICY:1'],'human_decision':'The purchasing manager must confirm the final quote before approval.'}
            if mode=='bad-source':obj['source_refs']=['DOC:DOES-NOT-EXIST']
            if mode=='bad-number':obj['summary']='The price is GBP 999999.'
            if mode=='wrong-supplier' and role=='Coordinator synthesis':obj['recommended_supplier_id']='S2'
            usage=None if mode=='missing' else {'prompt_tokens':100,'completion_tokens':20}
            finish='length' if mode=='truncated' else 'stop'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for chunk in [{'choices':[{'delta':{'content':json.dumps(obj)},'finish_reason':None}]},{'choices':[{'delta':{},'finish_reason':finish}]},{'choices':[],'usage':usage}]:self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        except (BrokenPipeError,ConnectionResetError):pass
        finally:
            with self.server.lock:self.server.active-=1

class BackOfficeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.lock=threading.Lock();self.server.active=0;self.server.peak=0
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def run_case(self,model='test'):
        run=CoordinatedRun(Settings(self.url,model,max_output=1200),{},brief=load_evidence()['scenario']['request'],output_dir=self.tmp.name);run.start();run.thread.join(10);self.assertFalse(run.thread.is_alive());return run,run.snapshot()
    def test_parallel_handoff_and_ledger(self):
        run,s=self.run_case();self.assertEqual(s['state'],'finished');self.assertEqual(len(s['calls']),4);self.assertEqual(s['input'],400);self.assertEqual(s['output'],80);self.assertEqual(self.server.peak,3)
        analysts=[c for c in s['calls'] if c['agent'] in ROLES];synthesis=next(c for c in s['calls'] if c['agent']=='Coordinator synthesis')
        self.assertLess(max(c['started_at'] for c in analysts),min(c['ended_at'] for c in analysts));self.assertGreaterEqual(synthesis['started_at'],max(c['ended_at'] for c in analysts));self.assertEqual(s['results']['1']['supplier']['id'],'S1')
        self.assertEqual(len(s['findings']),3);self.assertTrue(s['validation']['policy_eligibility']);self.assertTrue(all(c['source_refs'] and c['output'] for c in s['calls']))
        with sqlite3.connect(run.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM calls').fetchone()[0],4);self.assertGreater(c.execute('SELECT count(*) FROM handoffs').fetchone()[0],5)
        self.assertTrue(run.db_path.with_suffix('.json').exists())
    def test_untrusted_numbers_and_citations_block_synthesis(self):
        for mode in ['bad-source','bad-number','truncated']:
            _,s=self.run_case(mode);self.assertEqual(s['state'],'failed');self.assertEqual(len(s['calls']),3);self.assertFalse(s['results'])
    def test_ineligible_recommendation_is_withheld(self):
        _,s=self.run_case('wrong-supplier');self.assertEqual(s['state'],'failed');self.assertFalse(s['results']);self.assertEqual(len(s['calls']),4)
    def test_unknown_usage_is_not_invented(self):
        _,s=self.run_case('missing');self.assertEqual(s['completed'],1);self.assertEqual(s['unknown_usage_calls'],4);self.assertEqual(s['input'],0);self.assertEqual(s['output'],0);self.assertTrue(all(c['usage'] is None for c in s['calls']))
    def test_stop_never_releases_final_answer(self):
        run=CoordinatedRun(Settings(self.url,'slow'),{},output_dir=self.tmp.name);run.start();time.sleep(.08);run.stop();run.thread.join(5);s=run.snapshot();self.assertEqual(s['state'],'stopped');self.assertFalse(s['results']);self.assertTrue(any(c['status']=='cancelled' for c in s['calls']));self.assertEqual(s['inflight'],0)
    def test_deterministic_fixture(self):
        e=load_evidence();self.assertEqual([r['delivered_cost_gbp'] for r in e['comparison']],[38340,35440,40850]);self.assertEqual([r['delivery_date'] for r in e['comparison']],['2026-11-01','2026-11-08','2026-10-29']);self.assertEqual([r['id'] for r in e['comparison'] if r['passes_all_supplied_checks']],['S1'])
    def test_engine_scope_and_numeric_evidence_boundary(self):
        with self.assertRaises(ValueError):CoordinatedRun(Settings(self.url,'test'),{},brief='An unrelated request',output_dir=self.tmp.name)
        run=CoordinatedRun(Settings(self.url,'test'),{},output_dir=self.tmp.name)
        text=json.dumps({'summary':'The delivered price is GBP 38,340.','source_refs':['DOC:S1'],'uncertainties':['Stock is not reserved.']})
        with self.assertRaises(ValueError):run.validate_output(text,['DOC:S1'],approved_evidence={'documents':run.evidence['documents'],'scenario':run.evidence['scenario']})
    def test_retired_supplier_api_cannot_start_work(self):
        import api
        with TestClient(api.app,base_url="http://localhost") as client:
            for body in [{'scenario_id':'urgent-order'},{'request':'Send a real purchase order'},{'workflows':12}]:self.assertEqual(client.post('/api/runs',json=body).status_code,410)
            for path in ['/api/config','/api/run','/api/events','/api/runs/123/export.json']:self.assertEqual(client.get(path).status_code,410)
            self.assertEqual(client.get('/',follow_redirects=False).headers['location'],'/devteam')
            self.assertEqual(client.get('/static/factory.js').status_code,410)
            self.assertEqual(client.get('/api/devteam/not-a-route').status_code,404)

if __name__=='__main__':unittest.main()
