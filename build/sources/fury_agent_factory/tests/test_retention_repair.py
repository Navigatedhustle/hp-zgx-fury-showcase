import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from devteam import archive_terminal_runs,RetentionError
class RetentionTests(unittest.TestCase):
 def test_terminal_runs_are_preserved_in_archive(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder)/'runs'
   for i in range(3):
    run=base/str(i);run.mkdir(parents=True);(run/'audit.json').write_text(json.dumps({'state':'finished'}));(run/'output.html').write_text('preserved')
   archive_terminal_runs(base,limit=3)
   self.assertEqual(len(list(base.glob('*/audit.json'))),2)
   archived=list((Path(folder)/'runs-archive').glob('*/output.html'))
   self.assertEqual(len(archived),1);self.assertEqual(archived[0].read_text(),'preserved')
 def test_active_unknown_and_corrupt_runs_are_never_archived(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder)/'runs'
   for i,body in enumerate(['{"state":"running"}','{"state":"unknown"}','broken']):
    run=base/str(i);run.mkdir(parents=True);(run/'audit.json').write_text(body)
   with self.assertRaises(RetentionError):archive_terminal_runs(base,limit=3)
   self.assertEqual(len(list(base.glob('*/audit.json'))),3)
 def test_capacity_error_is_structured(self):
  import devteam_routes
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  app=FastAPI();app.include_router(devteam_routes.router)
  with patch.object(devteam_routes,'get_current',return_value=None),patch.object(devteam_routes,'DevRun',side_effect=RetentionError('Review retained audits')):
   response=TestClient(app).post('/api/devteam/runs',json={})
  self.assertEqual(response.status_code,409);self.assertEqual(response.json()['detail'],'Review retained audits')
 def test_unexpected_error_is_sanitized_json(self):
  import api,devteam_routes
  from fastapi.testclient import TestClient
  with patch.object(devteam_routes,'get_current',return_value=None),patch.object(devteam_routes,'DevRun',side_effect=RuntimeError('sensitive-internal-detail')):
   response=TestClient(api.app,raise_server_exceptions=False).post('/api/devteam/runs',json={})
  self.assertEqual(response.status_code,500);self.assertIn('application/json',response.headers['content-type']);self.assertIn('reference',response.json());self.assertNotIn('sensitive-internal-detail',response.text)
 def test_tuple_qa_protocol_is_rejected_before_merge(self):
  from devteam import validate_ticket_patch
  with self.assertRaisesRegex(ValueError,'tuple'):
   validate_ticket_patch({'files':{'test_backend.py':'status, body = handle(request, db_path)'}})
  validate_ticket_patch({'files':{'test_backend.py':'reply = handle(request, db_path)\nassert reply["status"] == 200\nassert reply["body"]["hotels"]'}})
 def test_backend_contract_repair_is_bounded_and_never_published_on_failure(self):
  import devteam,httpx,asyncio
  with tempfile.TemporaryDirectory() as folder:
   r=devteam.DevRun(store=folder,automatic=True)
   task=next(t for t in r.tasks if t['title']=='Backend');task['dependencies']=[];r.tasks=[task]
   tickets=[t for t in devteam.TICKETS if t[0]=='Backend'];attempts=[]
   async def call(*args,**kwargs):
    attempts.append(kwargs['task_id']);return {'files':{'backend.py':'def handle(request,db_path): return (200,{"hotels":[]})'}}
   real=httpx.AsyncClient
   def client(**kwargs):return real(transport=httpx.MockTransport(lambda q:httpx.Response(200,json={'data':[{'id':m,'ready':True} for m in (devteam.LEAD,devteam.SPECIALIST)]})))
   with patch.object(devteam,'TICKETS',tickets),patch.object(devteam,'available',return_value=True),patch.object(devteam,'execute',return_value=[200,{'hotels':[]}]),patch.object(r,'call',side_effect=call),patch.object(devteam.httpx,'AsyncClient',side_effect=client):r._thread()
   self.assertEqual(len(attempts),2);self.assertEqual(r.state,'failed');self.assertEqual(r.versions,[]);self.assertFalse((r.candidate/'backend.py').exists())
