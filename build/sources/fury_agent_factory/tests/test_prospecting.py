"""Synthetic fixtures exercise dependency gates and a bounded preview inbox, not live performance."""
import json,sqlite3,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from engine import Settings
from prospecting import ProspectRun,DraftInbox,evidence

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));role=self.headers['X-Fury-Role'];mode=payload['model'];data=json.loads(payload['messages'][1]['content'])['evidence']
        with self.server.lock:self.server.active+=1;self.server.peak=max(self.server.peak,self.server.active)
        try:
            time.sleep(.1 if mode!='slow' else 1)
            if role=='Research Agent':
                obj={'prospects':[{'company_id':r['company_id'],'fit':'The supplied project fits the fictional product.','uncertainty':'Attendance and needs are unverified.','source_refs':['COMPANY:'+r['company_id'],'ICP:1']} for r in data['evidence']['ranking']]}
                if mode=='bad-rank':obj['prospects'].reverse()
                if mode=='bad-source':obj['prospects'][0]['source_refs']=['COMPANY:C7','ICP:1']
            else:
                c=data['company'];obj={'company_id':c['id'],'subject':'Your fictional inference project','body':'A fictional introduction. If this is not relevant, no reply is needed.','source_refs':['COMPANY:'+c['id'],'PRODUCT:1']}
                if mode=='bad-draft':obj['body']='Missing review requirement'
            usage=None if mode=='unknown' else {'prompt_tokens':100,'completion_tokens':30}
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for chunk in [{'choices':[{'delta':{'content':json.dumps(obj)},'finish_reason':None}]},{'choices':[{'delta':{},'finish_reason':'stop'}]},{'choices':[],'usage':usage}]:self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        except (BrokenPipeError,ConnectionResetError):pass
        finally:
            with self.server.lock:self.server.active-=1

class ProspectingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.lock=threading.Lock();self.server.active=0;self.server.peak=0;threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def run_case(self,mode='test'):
        run=ProspectRun(Settings(self.url,mode,max_output=1200),{},output_dir=self.tmp.name);run.start();run.thread.join(10);self.assertFalse(run.thread.is_alive());return run,run.snapshot()
    def test_dependency_parallel_calls_and_source_ledger(self):
        run,s=self.run_case();self.assertEqual(s['state'],'finished');self.assertEqual(len(s['calls']),6);self.assertEqual(s['input'],600);self.assertEqual(s['output'],180);self.assertEqual(self.server.peak,3)
        research=next(c for c in s['calls'] if c['agent']=='Research Agent');sales=[c for c in s['calls'] if c['agent']=='Sales Agent'];self.assertTrue(all(c['started_at']>=research['ended_at'] for c in sales));self.assertLess(max(c['started_at'] for c in sales[:3]),min(c['ended_at'] for c in sales[:3]))
        self.assertEqual(len(s['results']['1']['drafts']),5);self.assertTrue(all(c['source_refs'] and c['output'] for c in s['calls']));self.assertTrue(run.db_path.with_suffix('.json').exists())
        with sqlite3.connect(run.db_path) as con:meta=json.loads(con.execute('SELECT payload FROM metadata').fetchone()[0]);self.assertIn('GTC Berlin',meta['data_notice'])
    def test_invalid_research_blocks_sales(self):
        for mode in ['bad-rank','bad-source']:
            _,s=self.run_case(mode);self.assertEqual(s['state'],'failed');self.assertFalse(s['results']);self.assertEqual(len(s['calls']),1)
    def test_invalid_email_withheld_and_unknown_usage(self):
        _,s=self.run_case('bad-draft');self.assertEqual(s['state'],'failed');self.assertFalse(s['results'])
        _,s=self.run_case('unknown');self.assertEqual(s['state'],'finished');self.assertEqual(s['unknown_usage_calls'],6);self.assertEqual(s['input'],0);self.assertEqual(s['output'],0)
    def test_stop_and_fixed_scope(self):
        with self.assertRaises(ValueError):ProspectRun(Settings(self.url,'test'),{},brief='Find real contacts',output_dir=self.tmp.name)
        run=ProspectRun(Settings(self.url,'slow'),{},output_dir=self.tmp.name);run.start();time.sleep(.08);run.stop();run.thread.join(5);self.assertEqual(run.snapshot()['state'],'stopped');self.assertFalse(run.results)
    def test_ranking_is_deterministic_and_exclusions_explicit(self):
        e=evidence();self.assertEqual([(r['company_id'],r['score']) for r in e['ranking']],[('C1',5),('C2',5),('C3',4),('C4',3),('C5',3)]);self.assertTrue(all(c['email'].endswith('.example') for c in e['companies']))
    def test_inbox_twenty_fifo_idempotent_persistence_review_and_no_resurrection(self):
        path=Path(self.tmp.name)/'inbox.sqlite';box=DraftInbox(path)
        def drafts(n):return [{'id':str(i),'to':f'{i}@prospects.example','subject':'Fictional','body':'Preview'} for i in range(n)]
        for n in range(5):box.add('run'+str(n),drafts(5))
        s=box.snapshot();self.assertEqual(len(s['items']),20);self.assertFalse(any(i['run_id']=='run0' for i in s['items']));box.add('run0',drafts(5));self.assertEqual(box.snapshot(),s)
        seq=s['items'][0]['seq'];self.assertTrue(box.review(seq)['items'][0]['reviewed_at']);self.assertEqual(len(DraftInbox(path).snapshot()['items']),20)
        with self.assertRaises(ValueError):box.review(-1)
        with self.assertRaises(ValueError):box.add('bad',[{'id':'bad','to':'actual@real.test'}])
        self.assertEqual(len(box.snapshot()['items']),20)
    def test_retired_prospecting_pages_and_api(self):
        import api
        with TestClient(api.app,base_url="http://localhost") as client:
            for path in ['/prospecting','/research','/sales','/static/prospecting.html']:
                response=client.get(path,follow_redirects=False);self.assertEqual(response.status_code,307);self.assertEqual(response.headers['location'],'/devteam')
            for path in ['/api/prospecting/config','/api/prospecting/inbox']:self.assertEqual(client.get(path).status_code,410)
            self.assertEqual(client.post('/api/prospecting/send').status_code,410)
            self.assertEqual(client.get('/static/prospecting.js').status_code,410)
            self.assertEqual(client.get('/devteam').status_code,200)

if __name__=='__main__':unittest.main()
