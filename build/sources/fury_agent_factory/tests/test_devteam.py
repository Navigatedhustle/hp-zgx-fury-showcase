
"""Explicit synthetic fixtures. These tests are not GPU or model performance evidence."""
import asyncio,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from collections import deque
import httpx
import devteam
from devteam import DevRun,parse_patch,roster,LEAD,SPECIALIST
class DevTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
 def run_obj(self):return DevRun(store=self.tmp.name,automatic=True)
 def test_roster_is_operator_six_simulations_twentyfour_agents(self):
  rows=roster();self.assertEqual(len(rows),31);self.assertEqual(sum(r['type']=='human' for r in rows),1);self.assertEqual(sum(r['presence']=='operator' for r in rows),1)
 def test_patch_rejects_paths_and_oversized_payload(self):
  for files in [{'../api.py':'x'},{'backend.py':'x'*60001},{'other.py':'x'}]:
   with self.assertRaises(ValueError):parse_patch(json.dumps({'files':files}))
  self.assertEqual(parse_patch('```json\n{"files":{"backend.py":"ok"}}\n```')['files']['backend.py'],'ok')
 def test_human_gate_idempotency_and_no_timeout_approval(self):
  r=self.run_obj();r.gate={'id':'a','status':'waiting'};r.approve('a','approve','Verification fixture');self.assertEqual(r.gate['actor'],'Verification fixture');self.assertEqual(r.gate['identity_basis'],'self reported operator name')
  with self.assertRaises(ValueError):r.approve('a','approve','Verification fixture')
  r.gate={'id':'b','status':'waiting'}
  with self.assertRaises(ValueError):r.approve('wrong','approve','Verification fixture')
  self.assertEqual(r.gate['status'],'waiting')
  with self.assertRaises(ValueError):r.approve('b','approve','   ')
  self.assertEqual(r.gate['status'],'waiting')
 def test_rate_uses_deltas_not_cumulative_sum_and_expires(self):
  r=self.run_obj();now=time.monotonic();r.calls=[{'id':'x','actor':'agent1','usage':{'completion_tokens':30},'live_count':30,'live_supported':True,'_samples':deque([(now,10),(now,20)]),'_text':''}]
  self.assertEqual(r.snapshot()['calls'][0]['current_tps'],6)
  with patch.object(devteam.time,'monotonic',return_value=now+6):self.assertEqual(r.snapshot()['calls'][0]['current_tps'],0)
 def test_final_only_usage_is_not_claimed_as_live(self):
  r=self.run_obj();r.calls=[{'id':'x','actor':'agent1','usage':{'completion_tokens':30},'live_count':30,'live_supported':False,'_samples':deque([(time.monotonic(),30)]),'_text':''}]
  self.assertIsNone(r.snapshot()['calls'][0]['current_tps'])
 def test_last_healthy_version_is_immutable(self):
  r=self.run_obj();r.apply({'files':{'index.html':'first'}});r.tests={'passed':True};r.promote('one');r.apply({'files':{'index.html':'candidate'}})
  self.assertEqual((r.root/'version-1/index.html').read_text(),'first');self.assertEqual(len(r.versions[0]['hash']),64)
 def test_no_sandbox_fails_closed(self):
  r=self.run_obj()
  with patch.object(devteam,'available',return_value=False):
   r.start();r.thread.join(3)
  self.assertEqual(r.state,'failed');self.assertIn('bubblewrap',r.error);self.assertFalse(r.calls)
 def test_streamed_counts_and_file_ownership(self):
  r=self.run_obj()
  def handler(req):
   data=json.loads(req.content);self.assertEqual(data['model'],LEAD)
   if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':4})
   text=json.dumps({'summary':'fixture','files':{'architecture.md':'architecture'}})
   frames=[{'choices':[{'delta':{'content':text},'finish_reason':None}],'usage':{'completion_tokens':10,'prompt_tokens':4}},{'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'completion_tokens':15,'prompt_tokens':4}},{'choices':[],'usage':{'completion_tokens':15,'prompt_tokens':4}}]
   return httpx.Response(200,text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n')
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Architecture','agent1',LEAD,'fixture')
  result=asyncio.run(perform());self.assertIn('architecture.md',result['files']);self.assertEqual(r.calls[0]['usage']['completion_tokens'],15);self.assertEqual(sum(n for _,n in r.calls[0]['_samples']),15);self.assertTrue(r.calls[0]['live_supported'])
 def test_exact_prompt_tokenization_mismatch_fails_closed(self):
  r=self.run_obj()
  def handler(req):
   if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':5})
   text=json.dumps({'files':{'architecture.md':'fixture'}})
   frame={'choices':[{'delta':{'content':text},'finish_reason':'stop'}],'usage':{'completion_tokens':10,'prompt_tokens':4}}
   return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Architecture','agent1',LEAD,'fixture')
  with self.assertRaisesRegex(RuntimeError,'Exact tokenization'):asyncio.run(perform())
  self.assertEqual(r.calls[0]['status'],'failed')
 def test_historical_large_frontend_prompt_keeps_complete_output_budget(self):
  r=self.run_obj();submitted=[]
  def handler(req):
   if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':12520})
   submitted.append(json.loads(req.content))
   text=json.dumps({'files':{'app.js':'// synthetic complete output'}})
   frame={'choices':[{'delta':{'content':text},'finish_reason':'stop'}],'usage':{'completion_tokens':10,'prompt_tokens':12520}}
   return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Frontend refinement','agent3',SPECIALIST,'fixture')
  asyncio.run(perform());self.assertGreaterEqual(submitted[0]['max_tokens'],6000)
  self.assertLessEqual(12520+submitted[0]['max_tokens'],r.calls[0]['context_limit'])
 def test_actual_parser_final_only_usage_remains_unknown(self):
  r=self.run_obj()
  def handler(req):
   if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':4})
   text=json.dumps({'files':{'architecture.md':'fixture'}})
   frames=[{'choices':[{'delta':{'content':text},'finish_reason':'stop'}],'usage':{'completion_tokens':10,'prompt_tokens':4}}]
   return httpx.Response(200,text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n')
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Architecture','daniel',LEAD,'fixture')
  asyncio.run(perform());self.assertIsNone(r.snapshot()['calls'][0]['current_tps']);self.assertFalse(r.calls[0]['history']);self.assertEqual(r.calls[0]['usage']['completion_tokens'],10)
 def test_preflight_rejection_clears_active_role_without_dispatch(self):
  r=self.run_obj();seen=[]
  def handler(req):
   seen.append(req.url.path)
   return httpx.Response(200,json={'count':20000})
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Architecture','agent1',LEAD,'fixture')
  with self.assertRaisesRegex(RuntimeError,'context budget'):asyncio.run(perform())
  self.assertEqual(r.calls[0]['status'],'failed');self.assertIsNone(r.calls[0]['usage'])
  self.assertEqual(next(a for a in r.actors if a['id']=='agent1')['state'],'failed')
  self.assertEqual(len(seen),1);self.assertTrue(seen[0].endswith('/tokenize'))
 def test_stop_during_preflight_does_not_start_inference(self):
  r=self.run_obj();seen=[]
  def handler(req):
   seen.append(req.url.path);r.stop_event.set()
   return httpx.Response(200,json={'count':4})
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Architecture','agent1',LEAD,'fixture')
  with self.assertRaises(asyncio.CancelledError):asyncio.run(perform())
  self.assertEqual(r.calls[0]['status'],'cancelled');self.assertIsNone(r.calls[0]['usage']);self.assertEqual(len(seen),1)
 def test_generated_code_has_no_host_fallback(self):
  import devteam_sandbox
  with patch.object(devteam_sandbox.sys,'platform','win32'):
   with self.assertRaises(RuntimeError):devteam_sandbox.execute(Path(self.tmp.name),Path(self.tmp.name)/'data','test')
 def test_complete_orchestration_with_explicit_synthetic_adapters(self):
  r=self.run_obj()
  async def fake_call(client,title,actor,model,task,**kwargs):
   r.calls.append({'id':'fixture'+str(len(r.calls)),'task_id':kwargs.get('task_id')})
   return {'files':{name:'fixture' for name in devteam.FILE_SCOPES[title]}}
  def endpoint(req):return httpx.Response(200,json={'data':[{'id':LEAD,'ready':True},{'id':SPECIALIST,'ready':True}]})
  real_client=httpx.AsyncClient
  def client(**kwargs):return real_client(transport=httpx.MockTransport(endpoint))
  with patch.object(devteam,'available',return_value=True),patch.object(devteam,'check_frontend',new=AsyncMock()),patch.object(devteam,'check_backend_contract'),patch.object(devteam,'check_generated_qa'),patch.object(r,'call',side_effect=fake_call),patch.object(devteam,'execute',side_effect=lambda code,data,mode,*payload: {'status':200,'body':{'hotels':[{'id':i} for i in range(1,6)]}} if mode=='api' else {'passed':True,'tests':1,'log':'SYNTHETIC ADAPTER'}),patch.object(devteam.httpx,'AsyncClient',side_effect=client):
   r.start();r.thread.join(5)
  self.assertFalse(r.thread.is_alive());self.assertEqual(r.state,'finished');self.assertGreaterEqual(len(r.versions),3);self.assertEqual(r.versions[-1]['title'],'Release')
 def test_repair_http_payload_includes_its_rejected_owned_file(self):
  r=self.run_obj();source=r.root/'rejected';source.mkdir();(source/'app.js').write_text('// rejected code to repair');submitted=[]
  def handler(req):
   if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':4})
   submitted.append(json.loads(req.content));text=json.dumps({'files':{'app.js':'// repaired code'}})
   frame={'choices':[{'delta':{'content':text},'finish_reason':'stop'}],'usage':{'completion_tokens':10,'prompt_tokens':4}}
   return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')
  async def perform():
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:return await r.call(client,'Frontend wiring','maya',SPECIALIST,'Repair candidate',source=source)
  asyncio.run(perform());refs=json.loads(submitted[0]['messages'][1]['content'])['read_only_reference_files'];self.assertEqual(refs['app.js'],'// rejected code to repair')

if __name__=='__main__':unittest.main()
