"""Synthetic scheduler/merge fixtures, never live model throughput evidence."""
import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
import httpx
import devteam
class ParallelTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.run=devteam.DevRun(store=self.tmp.name,automatic=True)
 def test_people_are_explicit_and_operator_has_no_rate(self):
  actors=self.run.snapshot()['actors'];developers=[a for a in actors if a['type']=='developer'];self.assertEqual(len(developers),6);self.assertEqual({a['name'] for a in developers},{'Maya Chen','Jonas Weber','Sofia Alvarez','Daniel Brooks','Priya Shah','Elias Martin'})
  operator=next(a for a in actors if a['type']=='human');self.assertEqual(operator['name'],'Operator');self.assertEqual(operator['presence'],'operator');self.assertIsNone(operator['current_tps'])
 def test_missing_participant_usage_remains_unknown(self):
  from collections import deque
  self.run.calls=[{'id':'fixture','actor':'maya','usage':None,'live_count':None,'live_supported':False,'_samples':deque(),'_text':'','status':'queued'}]
  actor=next(a for a in self.run.snapshot()['actors'] if a['id']=='maya');self.assertIsNone(actor['tokens']);self.assertIsNone(actor['current_tps'])
 def test_every_task_declares_read_and_write_scopes(self):
  self.assertEqual(set(devteam.DEPENDENCIES),{t[0] for t in devteam.TICKETS})
  self.assertEqual(set(devteam.READ_SCOPES),set(devteam.DEPENDENCIES))
  for title,actor,model,prompt in devteam.TICKETS:
   self.assertTrue(devteam.FILE_SCOPES[title]<=devteam.ALLOWED);self.assertTrue(devteam.READ_SCOPES[title]<=devteam.ALLOWED)
  self.assertNotIn('styles.css',devteam.READ_SCOPES['Integration review']);self.assertNotIn('app.js',devteam.READ_SCOPES['Input hardening'])
 def test_batch_conflict_is_atomic(self):
  r=self.run;r.apply({'files':{'backend.py':'healthy'}});base=devteam.file_hashes(r.candidate)
  tasks=[{'id':str(i),'actor':'jonas','title':'Backend','owns':['backend.py'],'input_hashes':base,'call_id':str(i)} for i in range(2)]
  with self.assertRaisesRegex(ValueError,'ownership conflict'):r.merge_batch([(t,{'files':{'backend.py':'candidate'}}) for t in tasks])
  self.assertEqual((r.candidate/'backend.py').read_text(),'healthy')
 def test_stale_workspace_and_wrong_owner_are_rejected(self):
  r=self.run;r.apply({'files':{'backend.py':'healthy'}});task={'owns':['backend.py'],'input_hashes':devteam.file_hashes(r.candidate)};r.apply({'files':{'backend.py':'newer'}})
  with self.assertRaisesRegex(ValueError,'Stale'):r.merge_batch([(task,{'files':{'backend.py':'old'}})])
  with self.assertRaisesRegex(ValueError,'ownership'):r.merge_batch([(task,{'files':{'app.js':'wrong'}})])
 def test_real_scheduler_bounds_and_dependencies_with_synthetic_calls(self):
  r=self.run;active=[];overlaps=[];seen=[];real=httpx.AsyncClient
  async def call(client,title,actor,model,prompt,source,task_id):
   self.assertNotEqual(source,r.candidate);self.assertEqual(devteam.file_hashes(source),next(t for t in r.tasks if t['id']==task_id)['input_hashes'])
   active.append((actor,model));overlaps.append(list(active));seen.append(title)
   if title!='Architecture':self.assertIn('architecture.md',devteam.file_hashes(source))
   await asyncio.sleep(.01)
   r.calls.append({'id':'fixture'+task_id,'task_id':task_id});active.remove((actor,model));return {'files':{n:('pass' if n in ('test_backend.py','backend.py') else '// fixture '+title if n=='app.js' else 'fixture '+title) for n in devteam.FILE_SCOPES[title]}}
  def client(**kwargs):return real(transport=httpx.MockTransport(lambda q:httpx.Response(200,json={'data':[{'id':m,'ready':True} for m in (devteam.LEAD,devteam.SPECIALIST)]})))
  with patch.object(devteam,'available',return_value=True),patch.object(devteam,'check_frontend',new=AsyncMock()),patch.object(devteam,'check_backend_contract'),patch.object(devteam,'check_generated_qa'),patch.object(devteam,'execute',side_effect=lambda code,data,mode,*payload: {'status':200,'body':{'hotels':[{'id':i} for i in range(1,6)]}} if mode=='api' else {'passed':True,'tests':1,'log':'SYNTHETIC'}),patch.object(devteam.httpx,'AsyncClient',side_effect=client),patch.object(r,'call',side_effect=call):asyncio.run(r.work())
  self.assertEqual(r.state,'finished');self.assertEqual(max(map(len,overlaps)),2);self.assertTrue(any(len(o)==2 and {m for _,m in o}=={devteam.LEAD,devteam.SPECIALIST} for o in overlaps));self.assertEqual(seen[0],'Architecture');self.assertTrue(all(t['status']=='merged' for t in r.tasks));self.assertTrue(all(c.get('actor') for c in r.changes))
 def test_failed_parallel_task_cancels_sibling_without_partial_merge(self):
  r=self.run;real=httpx.AsyncClient;cancelled=[]
  async def call(client,title,actor,model,prompt,source,task_id):
   if title=='Architecture':r.calls.append({'id':'fixture','task_id':task_id});return {'files':{'architecture.md':'fixture'}}
   if title=='Frontend':await asyncio.sleep(.01);raise RuntimeError('Explicit fixture failure')
   try:await asyncio.sleep(10)
   except asyncio.CancelledError:cancelled.append(title);raise
  def client(**kwargs):return real(transport=httpx.MockTransport(lambda q:httpx.Response(200,json={'data':[{'id':m,'ready':True} for m in (devteam.LEAD,devteam.SPECIALIST)]})))
  with patch.object(devteam,'available',return_value=True),patch.object(devteam,'check_frontend',new=AsyncMock()),patch.object(devteam,'check_backend_contract'),patch.object(devteam,'check_generated_qa'),patch.object(devteam.httpx,'AsyncClient',side_effect=client),patch.object(r,'call',side_effect=call):r._thread()
  self.assertEqual(r.state,'failed');self.assertEqual(cancelled,['Contract review']);self.assertEqual(set(devteam.file_hashes(r.candidate)),{'architecture.md'});self.assertFalse(r.versions)
 def test_retry_preserves_rejected_candidate_without_publishing_it(self):
  r=self.run;real=httpx.AsyncClient;attempts=[]
  async def call(client,title,actor,model,prompt,source,task_id):
   if title=='Frontend wiring':
    attempts.append(source)
    if len(attempts)==2:
     self.assertIn('rejected-candidate',(source/'app.js').read_text());self.assertIn('deliberate validation failure',prompt)
     self.assertFalse((r.candidate/'app.js').exists(),'Rejected candidate must not be published')
     self.assertNotIn('app.js',next(t for t in r.tasks if t['id']==task_id)['input_hashes'])
   r.calls.append({'id':'fixture'+str(len(r.calls)),'task_id':task_id})
   return {'files':{name:('pass' if name in ('test_backend.py','backend.py') else '// '+('rejected-candidate' if title=='Frontend wiring' and len(attempts)==1 else 'repaired-candidate') if name=='app.js' else 'fixture '+title) for name in devteam.FILE_SCOPES[title]}}
  async def validate(code,data,stop):
   if (code/'app.js').exists() and 'rejected-candidate' in (code/'app.js').read_text():raise ValueError('deliberate validation failure')
  def client(**kwargs):return real(transport=httpx.MockTransport(lambda q:httpx.Response(200,json={'data':[{'id':m,'ready':True}for m in (devteam.LEAD,devteam.SPECIALIST)]})))
  with patch.object(devteam,'available',return_value=True),patch.object(devteam,'check_frontend',side_effect=validate),patch.object(devteam,'check_backend_contract'),patch.object(devteam,'check_generated_qa'),patch.object(devteam,'execute',side_effect=lambda code,data,mode,*payload:{'status':200,'body':{'hotels':[{'id':i}for i in range(1,6)]}}if mode=='api'else{'passed':True,'tests':1,'log':'SYNTHETIC'}),patch.object(devteam.httpx,'AsyncClient',side_effect=client),patch.object(r,'call',side_effect=call):asyncio.run(r.work())
  self.assertEqual(r.state,'finished');self.assertEqual(len(attempts),2);self.assertNotEqual(attempts[0],attempts[1]);self.assertTrue(any(e['kind']=='repair candidate supplied'for e in r.events))
 def test_backend_repair_escalates_to_actual_local_lead_and_preserves_candidate(self):
  r=self.run;real=httpx.AsyncClient;attempts=[]
  async def call(client,title,actor,model,prompt,source,task_id):
   if title=='Backend':
    attempts.append(model)
    if len(attempts)==1:
     r.calls.append({'id':'rejected-backend','task_id':task_id});return {'files':{'backend.py':'conn.execute("CREATE TABLE(\n id INTEGER)")'}}
    self.assertEqual(model,devteam.LEAD);self.assertIn('conn.execute',(source/'backend.py').read_text());self.assertIn('Python syntax error',prompt)
   r.calls.append({'id':'fixture'+str(len(r.calls)),'task_id':task_id})
   return {'files':{name:'pass'if name.endswith('.py')else'// fixture'if name=='app.js'else'fixture'for name in devteam.FILE_SCOPES[title]}}
  def client(**kwargs):return real(transport=httpx.MockTransport(lambda q:httpx.Response(200,json={'data':[{'id':m,'ready':True}for m in (devteam.LEAD,devteam.SPECIALIST)]})))
  with patch.object(devteam,'available',return_value=True),patch.object(devteam,'check_frontend',new=AsyncMock()),patch.object(devteam,'check_backend_contract'),patch.object(devteam,'check_generated_qa'),patch.object(devteam,'execute',side_effect=lambda code,data,mode,*payload:{'status':200,'body':{'hotels':[{'id':i}for i in range(1,6)]}}if mode=='api'else{'passed':True,'tests':1,'log':'SYNTHETIC'}),patch.object(devteam.httpx,'AsyncClient',side_effect=client),patch.object(r,'call',side_effect=call):asyncio.run(r.work())
  self.assertEqual(r.state,'finished');self.assertEqual(attempts,[devteam.SPECIALIST,devteam.LEAD]);self.assertTrue(any(e['kind']=='repair model selected'and e['to_model']==devteam.LEAD for e in r.events))
