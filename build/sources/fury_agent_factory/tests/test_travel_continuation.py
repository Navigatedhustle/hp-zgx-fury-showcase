"""Orchestrator regressions only; fixtures are never product acceptance evidence."""
import asyncio,json
import pytest
import travel_run
from travel_run import TravelRun
from travel_spec import TASKS

def test_durable_state_retains_completed_work_and_no_token_cutoff(tmp_path):
 r=TravelRun(store=tmp_path/'runs')
 r.calls=[{'usage':{'total_tokens':55000,'completion_tokens':9000},'_samples':__import__('collections').deque(),'live_supported':False,'_text':'','actor':'daniel','status':'complete','seconds':1}]
 r.tasks[0]['status']='merged';r.save()
 state=json.loads((r.root/'project-state.json').read_text())
 assert state['tasks'][0]['status']=='merged'
 assert state['product']['specification']
 assert r.snapshot()['cumulative_tokens']==55000
 assert r.state=='ready'

def test_resume_skips_merged_source_and_continues_above_old_cutoff(tmp_path,monkeypatch):
 r=TravelRun(store=tmp_path/'runs');seen=[]
 for task,(_,name,_) in zip(r.tasks,TASKS):
  task['status']='merged';(r.candidate/name).write_text('completed source')
 r.tasks[-1]['status']='pending'
 r.calls=[{'usage':{'total_tokens':40001}}]
 monkeypatch.setattr(travel_run,'available',lambda:True)
 async def ticket(client,title,name,prompt,task):
  seen.append(title);raise asyncio.CancelledError()
 r.ticket=ticket
 with pytest.raises(asyncio.CancelledError):asyncio.run(r.work())
 assert seen==[TASKS[-1][0]]
 assert (r.candidate/'db.py').read_text()=='completed source'

def test_stop_remains_immediate_before_tool_dispatch(tmp_path):
 r=TravelRun(store=tmp_path/'runs');r.stop()
 with pytest.raises(asyncio.CancelledError):asyncio.run(r.ticket(None,'Travel database','db.py','',r.tasks[1]))
 assert not r.calls


def test_repairs_read_only_the_owned_backend_module():
 assert travel_run.READ_SCOPES['Repair db.py']==set()
 assert travel_run.READ_SCOPES['Repair private.py']=={'backend.py','auth.py','reservations.py'}
 assert travel_run.READ_SCOPES['Repair app.js']=={'index.html','contract_review.md'}

def test_failed_diagnostics_are_compacted_before_model_dispatch(tmp_path):
 import httpx
 r=TravelRun(store=tmp_path/'runs');r.tests={'passed':False,'log':'x'*100000,'generated_qa':{'log':'y'*100000},'checks':[{'id':'catalog','passed':False,'error':'z'*10000}]}
 task={'id':'repair-fixture','title':'Repair db.py','actor':'daniel','model':travel_run.LEAD};r.tasks.append(task)
 def handle(request):
  payload=json.loads(request.content)
  if request.url.path.endswith('/tokenize'):
   assert len(json.dumps(payload))<30000
   raise RuntimeError('preflight fixture: no inference')
  raise AssertionError('No inference should be dispatched by fixture')
 async def call():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:await r.call(client,'Repair db.py','daniel',travel_run.LEAD,'fixture',task_id=task['id'])
 with pytest.raises(RuntimeError,match='no inference'):asyncio.run(call())

def test_restart_automatically_recovers_completed_source_without_new_run(tmp_path,monkeypatch):
 import devteam_routes
 factory=tmp_path/'deployment'/'build'/'sources'/'factory';factory.mkdir(parents=True)
 r=TravelRun(store=factory/'devruns');r.state='running';r.tasks[0]['status']='merged';(r.candidate/'architecture.md').write_text('preserved decision');r.save()
 state=factory.parents[2]/'state';state.mkdir();(state/'factory-sessions.json').write_text(json.dumps({'a'*32:r.id}))
 resumed=[];monkeypatch.setattr(TravelRun,'start',lambda self:resumed.append(self.id));monkeypatch.setattr(devteam_routes,'ROOT',factory);monkeypatch.setattr(devteam_routes,'runs',{})
 devteam_routes.recover_sessions();restored=devteam_routes.runs['a'*32]
 assert resumed==[r.id]
 assert restored.tasks[0]['status']=='merged'
 assert (restored.candidate/'architecture.md').read_text()=='preserved decision'
 assert restored.id==r.id

def test_new_run_preserves_previous_project_and_database(tmp_path):
 first=TravelRun(store=tmp_path/'runs');(first.candidate/'backend.py').write_text('retained source');first.data.mkdir();(first.data/'bookings.sqlite').write_bytes(b'isolated fixture')
 second=TravelRun(store=tmp_path/'runs')
 assert first.id!=second.id and first.root!=second.root
 assert (first.candidate/'backend.py').read_text()=='retained source'
 assert (first.data/'bookings.sqlite').read_bytes()==b'isolated fixture'
 assert not second.data.exists()

def test_rest_transport_preserves_real_backend_permissions(tmp_path,monkeypatch):
 import devteam_routes
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from types import SimpleNamespace
 run=SimpleNamespace(root=tmp_path,data=tmp_path/'data',versions=[{'version':1}]);observed=[]
 monkeypatch.setattr(devteam_routes,'travel_lookup',lambda rid:run)
 def sandbox(code,data,mode,payload):observed.append(payload);return {'status':403,'body':{'error':'Forbidden fixture'}}
 monkeypatch.setattr(devteam_routes,'execute',sandbox)
 app=FastAPI();app.include_router(devteam_routes.router)
 response=TestClient(app).put('/api/travel/fixture/app/admin/listings/1',json={'price':222,'active':1},headers={'Authorization':'Bearer demo-fixture'})
 assert response.status_code==403 and response.json()['error']=='Forbidden fixture'
 assert observed[0]['headers']['authorization']=='Bearer demo-fixture'
 assert observed[0]['method']=='PUT' and observed[0]['path']=='/admin/listings/1'

@pytest.mark.parametrize('configured,reported,prompt,expected', [('16384',8192,5000,8192),(None,16384,9000,16384)])
def test_exact_serving_context_caps_each_request(tmp_path,monkeypatch,configured,reported,prompt,expected):
 import httpx
 from devteam import DevRun,LEAD
 if configured is None:monkeypatch.delenv('FURY_DEV_LEAD_CONTEXT',raising=False)
 else:monkeypatch.setenv('FURY_DEV_LEAD_CONTEXT',configured)
 r=DevRun(store=tmp_path/'runs',automatic=True)
 def handle(request):
  data=json.loads(request.content)
  if request.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':prompt,'max_model_len':reported})
  assert data['max_tokens']+prompt+128<=reported
  patch=json.dumps({'summary':'Explicit non-inference regression fixture','files':{'architecture.md':'fixture'}})
  frame={'choices':[{'delta':{'content':patch},'finish_reason':'stop'}],'usage':{'prompt_tokens':prompt,'completion_tokens':1,'total_tokens':prompt+1}}
  return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')
 async def call():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:return await r.call(client,'Architecture','agent1',LEAD,'fixture')
 asyncio.run(call());assert r.calls[0]['context_limit']==expected;assert r.calls[0]['reported_context_limit']==reported

@pytest.mark.parametrize('truth',[True,False])
def test_generated_plain_assertion_tests_really_execute_in_sandbox(tmp_path,truth):
 from devteam_sandbox import available,execute
 if not available():pytest.skip('Requires the real installed Linux namespace runner')
 code=tmp_path/'code';code.mkdir();(code/'test_backend.py').write_text('def test_plain_fixture():\n assert '+str(truth)+'\n')
 names=execute(code,tmp_path/'data','travellist')['tests'];assert len(names)==1
 result=execute(code,tmp_path/'data','traveltest',{'tests':names})
 assert result['tests']==1 and result['passed']==truth


def test_repeated_frontend_failure_escalates_to_resident_lead(tmp_path,monkeypatch):
 import travel_checks,travel_browser,importlib
 r=TravelRun(store=tmp_path/'runs');selected=[]
 for task,(_,name,_) in zip(r.tasks,TASKS):
  task['status']='merged';(r.candidate/name).write_text('explicit controller fixture')
 monkeypatch.setattr(travel_run,'available',lambda:True);monkeypatch.setattr(importlib,'reload',lambda module:module)
 monkeypatch.setattr(travel_checks,'check_product',lambda *args:{'passed':True,'checks':[{'id':key,'passed':True} for key in ('catalog','auth','private','reservation','admin')]})
 async def qa(n):return {'passed':True,'tests':1,'log':'controller fixture only'}
 async def browser(*args,**kwargs):return {'passed':False,'error':'Explicit unchanged browser fixture','console_errors':[],'body':''}
 async def ticket(client,title,name,prompt,task):
  selected.append((title,task['model']))
  if title=='Travel frontend diagnosis':raise asyncio.CancelledError()
 r.generated_qa=qa;r.ticket=ticket;monkeypatch.setattr(travel_browser,'check_browser',browser)
 with pytest.raises(asyncio.CancelledError):asyncio.run(r.work())
 assert selected[-1]==('Travel frontend diagnosis',travel_run.LEAD)
 assert len(selected)==3
 assert not r.versions

def test_nonfinite_diagnostic_never_breaks_snapshot_json_or_audit(tmp_path,monkeypatch):
 import devteam_routes
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 r=TravelRun(store=tmp_path/'runs');r.tests={'browser':{'passed':False,'events':[{'body':{'max_price':float('nan')}}]}};r.save()
 audit=json.loads((r.root/'audit.json').read_text());assert audit['tests']['browser']['events'][0]['body']['max_price']=={'invalid_numeric':'nan'}
 monkeypatch.setattr(devteam_routes,'get_current',lambda:r);app=FastAPI();app.include_router(devteam_routes.router)
 response=TestClient(app).get('/api/devteam/run');assert response.status_code==200
 assert response.json()['tests']['browser']['events'][0]['body']['max_price']=={'invalid_numeric':'nan'}
 json.dumps(response.json(),allow_nan=False)

def test_graceful_server_interrupt_recovers_but_user_stop_does_not(tmp_path):
 r=TravelRun(store=tmp_path/'runs')
 async def cancelled():raise asyncio.CancelledError()
 r.work=cancelled;r.interrupt();r._thread()
 assert r.state=='interrupted'
 assert json.loads((r.root/'audit.json').read_text())['state']=='interrupted'
 r.stop();r._thread();assert r.state=='stopped'
 assert not r.recover_after_restart


def test_development_preview_is_not_completion_and_never_replaces_accepted(tmp_path):
 r=TravelRun(store=tmp_path/'runs');(r.candidate/'index.html').write_text('explicit promotion policy fixture')
 r.tests={'passed':False};r.publish_development_preview({'passed':True});assert not r.versions
 r.tests={'passed':True};r.publish_development_preview({'passed':False});assert not r.versions
 r.publish_development_preview({'passed':True});assert r.versions[0]['stage']=='development';assert r.state!='finished'
 assert not all(c['passed'] for c in r.product['criteria'])
 r.versions[0]['stage']='accepted';(r.candidate/'index.html').write_text('new unaccepted fixture');r.publish_development_preview({'passed':True})
 assert len(r.versions)==1
 assert (r.root/'version-1/index.html').read_text()=='explicit promotion policy fixture'


def test_archived_completed_application_keeps_its_public_run_url(tmp_path,monkeypatch):
 import devteam_routes
 factory=tmp_path/'factory';factory.mkdir();r=TravelRun(store=factory/'devruns');(r.candidate/'index.html').write_text('preserved archived fixture')
 archive=factory/'devruns-archive';archive.mkdir();r.root.rename(archive/r.id)
 monkeypatch.setattr(devteam_routes,'ROOT',factory);monkeypatch.setattr(devteam_routes,'runs',{'owner':r})
 restored=devteam_routes.travel_lookup(r.id);assert restored is r
 assert (restored.candidate/'index.html').read_text()=='preserved archived fixture'
 assert restored.root==archive/r.id and restored.data==archive/r.id/'data'


def test_public_quote_authorization_failure_repairs_dispatch_boundaries():
 failure={'id':'reservation','error':"POST /quote: expected status 200; actual {'status': 401, 'body': {'error': 'Unauthorized'}}"}
 assert set(travel_run.repair_targets(failure))=={'private.py','reservations.py','backend.py','auth.py'}
 assert travel_run.repair_targets({'id':'reservation','error':'invalid total'})==[]
 assert 'private.py' in travel_run.READ_SCOPES['Repair reservations.py']
 from travel_spec import CONTRACT
 assert 'POST /quote is PUBLIC' in CONTRACT
 assert 'BEFORE authentication' in CONTRACT


def test_quote_failure_selects_upstream_repair_in_real_continuation(tmp_path,monkeypatch):
 import importlib,travel_checks
 r=TravelRun(store=tmp_path/'runs');selected=[]
 for task,(_,name,_) in zip(r.tasks,TASKS):
  task['status']='merged';(r.candidate/name).write_text('controller fixture')
 monkeypatch.setattr(travel_run,'available',lambda:True)
 monkeypatch.setattr(importlib,'reload',lambda module:module)
 failure={'id':'reservation','passed':False,'error':"POST /quote: expected status 200; actual {'status': 401}"}
 monkeypatch.setattr(travel_checks,'check_product',lambda *args:{'passed':False,'checks':[failure]})
 async def qa(n):return {'passed':True,'tests':1,'log':''}
 async def ticket(client,title,name,prompt,task):
  selected.append(name)
  assert 'POST /quote' in prompt and 'BEFORE any auth guard' in prompt
  raise asyncio.CancelledError()
 r.generated_qa=qa;r.ticket=ticket
 with pytest.raises(asyncio.CancelledError):asyncio.run(r.work())
 assert selected==['private.py']


def test_qa_stagnation_ignores_traceback_line_and_timing_changes():
 def failure(line,elapsed):
  return [{'id':'qa','error':f'FAIL: test_ownership (test_backend.TestBackend.test_ownership)\nTraceback (most recent call last):\n  File "/workspace/test_backend.py", line {line}, in test_ownership\nAssertionError: 404 != 200\nRan 1 test in {elapsed}s\n'}]
 assert travel_run.acceptance_signature(failure(179,.08))==travel_run.acceptance_signature(failure(183,.11))
 different=failure(179,.08);different[0]['error']=different[0]['error'].replace('404 != 200','403 != 200')
 assert travel_run.acceptance_signature(failure(179,.08))!=travel_run.acceptance_signature(different)


def test_repeated_qa_failure_is_bounded_despite_moving_line_numbers(tmp_path,monkeypatch):
 import importlib,travel_checks
 r=TravelRun(store=tmp_path/'runs');repairs=[]
 for task,(_,name,_) in zip(r.tasks,TASKS):
  task['status']='merged';(r.candidate/name).write_text('controller fixture')
 monkeypatch.setattr(travel_run,'available',lambda:True)
 monkeypatch.setattr(importlib,'reload',lambda module:module)
 monkeypatch.setattr(travel_checks,'check_product',lambda *args:{'passed':True,'checks':[]})
 async def qa(n):return {'passed':False,'tests':1,'log':f'FAIL: test_ownership (test_backend.T.test_ownership)\nFile "/workspace/test_backend.py", line {100+n}\nAssertionError: 404 != 200\nRan 1 test in {n+1}.01s'}
 async def ticket(client,title,name,prompt,task):
  repairs.append(name)
  assert 'GET /itineraries/{id} is not in the contract' in prompt
 r.generated_qa=qa;r.ticket=ticket
 with pytest.raises(RuntimeError,match='same acceptance failure'):asyncio.run(r.work())
 assert repairs==['test_backend.py','test_backend.py']


def test_generated_tests_report_real_non_inference_progress(tmp_path,monkeypatch):
 r=TravelRun(store=tmp_path/'runs')
 def execute(code,data,mode,payload=None):
  return {'tests':['test_one','test_two']} if mode=='travellist' else {'passed':True,'tests':1,'log':''}
 monkeypatch.setattr(travel_run,'execute',execute)
 result=asyncio.run(r.generated_qa(0))
 assert result['passed'] and result['tests']==2
 assert '2/2: test_two' in r.product['next_action']
 assert [e['name'] for e in r.events if e['kind']=='test case started']==['test_one','test_two']
 assert not r.calls


def test_syntax_retry_receives_rejected_owned_file_without_merging_it(tmp_path):
 r=TravelRun(store=tmp_path/'runs');seen=[];invalid='def broken():\nwrong indentation\n'
 async def call(client,title,actor,model,prompt,source,task_id):
  seen.append(source)
  if len(seen)==1:return {'files':{'db.py':invalid},'summary':'intentional invalid fixture'}
  assert (source/'db.py').read_text()==invalid
  assert not (r.candidate/'db.py').exists(), 'Rejected source must stay unpublished'
  assert 'indent' in prompt
  r.calls.append({'id':'fixture'})
  return {'files':{'db.py':'def connect(path):\n return None\n'},'summary':'syntax-only regression fixture'}
 r.call=call
 asyncio.run(r.ticket(None,'Travel database','db.py','fixture',r.tasks[1]))
 assert len(seen)==2 and r.tasks[1]['status']=='merged'
 assert (r.candidate/'db.py').read_text().startswith('def connect')


@pytest.mark.parametrize('prompt_tokens,expected',[(7000,8192),(10000,6256)])
def test_travel_qa_output_uses_available_verified_context(tmp_path,prompt_tokens,expected):
 import httpx
 r=TravelRun(store=tmp_path/'runs');seen=[]
 def handle(request):
  payload=json.loads(request.content)
  if request.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':prompt_tokens,'max_model_len':16384})
  seen.append(payload['max_tokens']);assert payload['max_tokens']+prompt_tokens+128<=16384
  result=json.dumps({'summary':'explicit transport regression, no real inference','files':{'test_backend.py':'def test_fixture():\n assert True\n'}})
  frame={'choices':[{'delta':{'content':result},'finish_reason':'stop'}],'usage':{'prompt_tokens':prompt_tokens,'completion_tokens':1,'total_tokens':prompt_tokens+1}}
  return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n')
 async def call():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:await r.call(client,'Travel independent QA','daniel',travel_run.LEAD,'fixture')
 asyncio.run(call());assert seen==[expected]


def test_travel_dependencies_describe_the_actual_sequential_generated_chain(tmp_path):
 r=TravelRun(store=tmp_path/'runs');generated=[t for t in r.tasks if not t.get('source')]
 assert generated[0]['dependencies']==[]
 for before,after in zip(generated,generated[1:]):assert after['dependencies']==[before['title']]
 assert all(t['status']=='merged' for t in r.tasks if t.get('source'))


def test_missing_backend_import_is_repaired_before_merge(tmp_path):
 from devteam_sandbox import available
 if not available():pytest.skip('Requires the installed namespace runner')
 r=TravelRun(store=tmp_path/'runs');attempts=[];invalid='import unavailable_admin_module\ndef handle(request,db_path):\n return {}\n'
 async def call(client,title,actor,model,prompt,source,task_id):
  attempts.append(prompt);r.calls.append({'id':'fixture-'+str(len(attempts))})
  if len(attempts)==1:return {'files':{'backend.py':invalid},'summary':'Intentional invalid import fixture'}
  assert 'unavailable_admin_module' in prompt
  assert (source/'backend.py').read_text()==invalid
  assert not (r.candidate/'backend.py').exists()
  return {'files':{'backend.py':'def handle(request,db_path):\n return {"status":200,"body":{"ready":True}}\n'},'summary':'Health-only controller fixture'}
 r.call=call
 asyncio.run(r.ticket(None,'Travel API integration','backend.py','fixture',r.tasks[6]))
 assert len(attempts)==2 and r.tasks[6]['status']=='merged'


def test_qa_import_failure_is_returned_to_the_repair_loop(tmp_path):
 from devteam_sandbox import available
 if not available():pytest.skip('Requires the installed namespace runner')
 r=TravelRun(store=tmp_path/'runs');(r.candidate/'test_backend.py').write_text('import unavailable_qa_fixture_module\n')
 result=asyncio.run(r.generated_qa(0))
 assert result['passed'] is False and result['tests']==0
 assert 'unavailable_qa_fixture_module' in result['log']


def test_exact_repairs_reject_ambiguous_or_incomplete_edits():
 from devteam import apply_exact_edits
 original='def value():\n return 1\n'
 assert apply_exact_edits(json.dumps({'summary':'fix','edits':[{'old':'return 1','new':'return 2'}]}),'reservations.py',original)['files']['reservations.py']=='def value():\n return 2\n'
 for edits in ([{'old':'missing','new':'x'}],[{'old':'','new':'x'}],[{'old':'return 1','new':'return 1'}],[{'old':'return 1','new':'return 2'},{'old':'missing','new':'x'}]):
  with pytest.raises(ValueError):apply_exact_edits(json.dumps({'summary':'fix','edits':edits}),'reservations.py',original)
 with pytest.raises(ValueError):apply_exact_edits(json.dumps({'summary':'fix','edits':[{'old':'x','new':'y'}]}),'reservations.py','x x')
 assert original=='def value():\n return 1\n'


def test_length_repair_retries_one_edit_without_replacing_complete_module(tmp_path):
 import httpx,devteam
 from travel_run import TravelRun
 r=TravelRun(store=tmp_path/'runs');name='reservations.py';original='def routes(conn,request):\n return None\n'+'# retained code\n'*800
 (r.candidate/name).write_text(original)
 task={'id':'repair-budget','title':'Repair '+name,'actor':'daniel','model':devteam.LEAD};r.tasks.append(task);requests=[]
 def handler(req):
  if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':7000 if len(json.loads(req.content).get('messages',[]))==1 else 12787,'max_model_len':16384})
  payload=json.loads(req.content);requests.append(payload)
  assert payload['max_tokens']==3469
  assert set(payload['response_format']['json_schema']['schema']['properties'])=={'summary','edits'}
  assert (r.candidate/name).read_text()==original
  if len(requests)==1:text='{"summary":"cut off';reason='length'
  else:text=json.dumps({'summary':'localized fix','edits':[{'old':'return None','new':"return {'status':200,'body':{}}"}]});reason='stop'
  return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':text},'finish_reason':reason}],'usage':{'prompt_tokens':12787,'completion_tokens':20}})+'\n\ndata: [DONE]\n\n')
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:await r.ticket(client,task['title'],name,'Fix the observed route response',task)
 asyncio.run(run())
 assert len(requests)==2 and task['status']=='merged'
 assert 'exactly ONE small exact edit' in requests[1]['messages'][1]['content']
 assert (r.candidate/name).read_text()==original.replace("return None","return {'status':200,'body':{}}")
 assert r.calls[0]['status']=='failed' and r.calls[1]['status']=='complete'
 assert all(c['output_protocol']=='exact_edits' for c in r.calls)


def test_reference_edit_dispatches_separate_owner_and_preserves_reservations(tmp_path,monkeypatch):
 import devteam,httpx
 r=TravelRun(store=tmp_path/'runs');original='def routes(conn,request):\n return None\n'+'# retained code\n'*800
 (r.candidate/'reservations.py').write_text(original)
 (r.candidate/'backend.py').write_text('def handle(request,db_path):\n return None\n')
 task={'id':'dependency-fixture','title':'Repair reservations.py','actor':'daniel','model':devteam.LEAD};r.tasks.append(task);seen=[]
 monkeypatch.setattr(travel_run,'execute',lambda *args,**kwargs:{'status':200,'body':{}})
 def handler(req):
  if req.url.path.endswith('/tokenize'):
   data=json.loads(req.content);count=(7000 if 'reservations.py' in data['messages'][0]['content'] else 1000) if len(data.get('messages',[]))==1 else 4000
   return httpx.Response(200,json={'count':count,'max_model_len':16384})
  payload=json.loads(req.content);ticket=json.loads(payload['messages'][1]['content']);seen.append(ticket.get('owned_file') or ticket['allowed_output_files'][0])
  text=json.dumps({'summary':'dispatcher defect','edits':[{'old':'def handle(request,db_path):\n return None','new':"def handle(request,db_path):\n return {'status':200,'body':{}}"}]}) if len(seen)==1 else json.dumps({'summary':'dispatcher fixed','files':{'backend.py':"def handle(request,db_path):\n return {'status':200,'body':{}}\n"}})
  return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':text},'finish_reason':'stop'}],'usage':{'prompt_tokens':4000,'completion_tokens':40}})+'\n\ndata: [DONE]\n\n')
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:await r.ticket(client,task['title'],'reservations.py','Fix the reservation dispatcher',task)
 asyncio.run(run())
 assert seen==['reservations.py','backend.py']
 assert (r.candidate/'reservations.py').read_text()==original
 assert "'status':200" in (r.candidate/'backend.py').read_text()
 assert task['status']=='merged' and 'independent checks' in task['resolution']
 assert any(e['kind']=='task resolved by dependency' and e['verification_pending'] for e in r.events)


def test_backend_dispatch_signature_catches_the_actual_reservation_root_defect():
 from travel_run import backend_dispatch_diagnostics
 for source in ('from private import routes as private_routes\nprivate_routes(conn,request,current_user)\n','import private\nprivate.routes(conn,request,current_user)\n'):
  with pytest.raises(ValueError,match='never a third current_user'):backend_dispatch_diagnostics(source)
 backend_dispatch_diagnostics('from private import routes as private_routes\nprivate_routes(conn,request)\n')


def test_generated_qa_failure_reports_actual_capacity_without_credentials(tmp_path):
 from devteam_sandbox import available,execute
 if not available():pytest.skip('Requires installed namespace sandbox')
 code=tmp_path/'code';code.mkdir()
 (code/'backend.py').write_text("def handle(request,db_path):\n if request['method']=='GET':return {'status':200,'body':{'listing':{'id':1,'capacity':2,'active':1}}}\n return {'status':400,'body':{'error':'Party size exceeds capacity'}}\n")
 (code/'test_backend.py').write_text("from backend import handle\ndef test_reservation():\n reply=handle({'method':'POST','path':'/reservations','body':{'listing_id':1,'party':3,'password':'fixture-private-password'},'headers':{'authorization':'fixture-private-bearer'}},'/data/test.sqlite')\n assert reply['status']==201\n")
 result=execute(code,tmp_path/'data','traveltest')
 assert not result['passed'] and 'Party size exceeds capacity' in result['log']
 assert '"capacity": 2' in result['log'] and '"party": 3' in result['log']
 assert 'fixture-private-password' not in result['log'] and 'fixture-private-bearer' not in result['log']


def test_unexpected_complete_file_truncation_switches_protocol(tmp_path):
 import devteam,httpx
 r=TravelRun(store=tmp_path/'runs');original='def routes(conn,request):\n return None\n'
 (r.candidate/'reservations.py').write_text(original)
 task={'id':'unexpected-length','title':'Repair reservations.py','actor':'daniel','model':devteam.LEAD};r.tasks.append(task);protocols=[]
 def handler(req):
  data=json.loads(req.content)
  if req.url.path.endswith('/tokenize'):return httpx.Response(200,json={'count':100 if len(data['messages'])==1 else 4000,'max_model_len':16384})
  schema=data['response_format']['json_schema']['schema']['properties'];protocols.append('files' if 'files' in schema else 'edits')
  text='{"files":' if len(protocols)==1 else json.dumps({'summary':'one small repair','edits':[{'old':'return None','new':"return {'status':200,'body':{}}"}]})
  return httpx.Response(200,text='data: '+json.dumps({'choices':[{'delta':{'content':text},'finish_reason':'length' if len(protocols)==1 else 'stop'}],'usage':{'prompt_tokens':4000,'completion_tokens':20}})+'\n\ndata: [DONE]\n\n')
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:await r.ticket(client,task['title'],'reservations.py','Fix route',task)
 asyncio.run(run());assert protocols==['files','edits'];assert task['status']=='merged'
