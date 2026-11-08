"""Focused failure fixtures only; real acceptance is showcase.py."""
import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import httpx
from fastapi.testclient import TestClient
from showcase_app import gateway as g
class GatewayTests(unittest.TestCase):
 def run_case(self,stream,handler):
  real=httpx.AsyncClient
  def client(**kwargs):return real(transport=httpx.MockTransport(handler),**kwargs)
  with tempfile.TemporaryDirectory() as folder,patch.object(g,'DB',Path(folder)/'ledger.db'):
   g.connect().close()
   with TestClient(g.app,base_url="http://localhost") as c,patch.object(g.httpx,'AsyncClient',side_effect=client):
    r=c.post('/slides/v1/chat/completions',json={'messages':[{'role':'user','content':'Fixture'}],'stream':stream,'max_tokens':4})
   self.assertFalse(g.active);self.assertFalse(g.waiting);self.assertEqual(g.total._value,4);self.assertEqual(g.normal._value,3)
   return r
 def test_malformed_input_is_a_structured_client_error(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(g,'DB',Path(folder)/'ledger.db'),TestClient(g.app,base_url="http://localhost") as c:
   for body,status in [('Internal error',400),('[]',422),('{"messages":[],"model":{}}',422)]:
    r=c.post('/slides/v1/chat/completions',content=body,headers={'content-type':'application/json'})
    self.assertEqual(r.status_code,status);self.assertIn('detail',r.json())
 def test_failed_http_status_is_preserved_and_sanitized(self):
  r=self.run_case(False,lambda q:httpx.Response(503,text='sensitive inference traceback'))
  self.assertEqual(r.status_code,503);self.assertNotIn('sensitive',r.text);self.assertIn('error',r.json())
 def test_interrupted_stream_fails_explicitly(self):
  r=self.run_case(True,lambda q:httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: {"choices":[]}\n\n'))
  self.assertIn('"error"',r.text);self.assertIn('RuntimeError',r.text)
 def test_malformed_stream_fails_explicitly(self):
  r=self.run_case(True,lambda q:httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: Internal failure\n\n'))
  self.assertIn('"error"',r.text)
 def test_valid_stream_completes(self):
  r=self.run_case(True,lambda q:httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n'))
  self.assertNotIn('"error"',r.text);self.assertIn('[DONE]',r.text)
 def test_busy_factory_lead_routes_brief_to_qwen_and_records_reason(self):
  real=httpx.AsyncClient;sent=[]
  def handler(request):
   sent.append(json.loads(request.content));return httpx.Response(200,json={'choices':[{'message':{'content':'Fixture brief'}}],'usage':{'prompt_tokens':5,'completion_tokens':2}})
  def client(**kwargs):return real(transport=httpx.MockTransport(handler),**kwargs)
  with tempfile.TemporaryDirectory() as folder,patch.object(g,'DB',Path(folder)/'ledger.db'):
   g.connect().close()
   with TestClient(g.app,base_url="http://localhost") as c,patch.object(g.httpx,'AsyncClient',side_effect=client):
    g.active['factory-fixture']={'demo':'agent','model':g.LEAD}
    try:r=c.post('/lead/vision/v1/chat/completions',json={'messages':[{'role':'user','content':'Fixture brief'}],'max_tokens':50})
    finally:g.active.pop('factory-fixture',None)
   self.assertEqual(r.status_code,200);self.assertEqual(sent[0]['model'],g.MODEL)
   self.assertEqual(r.json()['fury_routing']['reason'],'Routed to Qwen: DeepSeek is busy with Agent Factory')
   with g.connect() as db:
    requested,actual,reason,external=db.execute('SELECT requested,actual,reason,external_calls FROM routing').fetchone()
   self.assertEqual((requested,actual,external),(g.LEAD,g.MODEL,0));self.assertIn('Agent Factory',reason)
   self.assertEqual((g.total._value,g.normal._value,g.lead_slots._value),(4,3,1))
if __name__=='__main__':unittest.main()
