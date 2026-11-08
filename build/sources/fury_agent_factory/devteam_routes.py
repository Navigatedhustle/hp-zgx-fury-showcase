"""Separate development API; original supplier/prospecting scopes stay unchanged."""
import asyncio,json,re,threading,uuid,time,logging
from contextvars import ContextVar
import httpx
from pathlib import Path
from showcase_app.ui import header as hp_header
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import FileResponse,StreamingResponse,HTMLResponse,Response
from pydantic import BaseModel,ConfigDict
from typing import Literal
from devteam import DevRun,RetentionError
from devteam_sandbox import execute,available
router=APIRouter();ROOT=Path(__file__).resolve().parent;lock=threading.RLock()
session=ContextVar('factory_session',default=None)
runs={}
travel_slots=asyncio.Semaphore(4)
def get_current():
 r=runs.get(session.get())
 if r and not r.root.exists():
  archived=ROOT/'devruns-archive'/r.id
  if archived.is_dir():r.root=archived;r.candidate=archived/'candidate';r.data=archived/'data'
 return r
def active_runs():return [r for r in runs.values() if getattr(r,'mode','live')!='recorded' and r.thread and r.thread.is_alive()]
def recover_sessions():
 from collections import deque
 from devteam import roster
 base=ROOT/'devruns'
 # This app owns its workers. A previous running audit after startup means its
 # process was interrupted; it must never remain active forever or fill retention.
 for audit in base.glob('*/audit.json'):
  try:
   data=json.loads(audit.read_text())
   if data.get('state')=='running':
    data['state']='failed';data['error']='Application restarted during this build. Start a new development run.'
    for call in data.get('calls',[]):
     if call.get('status') in ('queued','admitted','generating'):call['status']='cancelled'
    audit.write_text(json.dumps(data,indent=2))
  except (OSError,ValueError):logging.exception('Cannot reconcile development audit %s',audit.name)
 path=ROOT.parents[2]/'state/factory-sessions.json'
 try:stored=json.loads(path.read_text())
 except (OSError,ValueError):return
 for key,rid in stored.items():
  if not re.fullmatch('[0-9a-f]{32}',key) or not re.fullmatch('[0-9a-f]{12}',rid):continue
  folder=base/rid
  if not folder.exists():folder=ROOT/'devruns-archive'/rid
  try:data=json.loads((folder/'audit.json').read_text())
  except (OSError,ValueError):continue
  r=DevRun.__new__(DevRun);r.id=rid;r.root=folder;r.candidate=folder/'candidate';r.data=folder/'data';r.thread=None;r.started=data.get('started') or min((c.get('started',time.time()) for c in data.get('calls',[])),default=time.time())
  r.lock=threading.RLock();r.stop_event=threading.Event();r.approval=threading.Event();r.actors=roster();r.changes=[];r.seq=max((e.get('seq',0) for e in data.get('events',[])),default=0)
  for field,default in [('state','failed'),('error',''),('events',[]),('calls',[]),('versions',[]),('gate',None),('automatic',False),('tasks',[]),('tests',None),('product_kind','short')]:setattr(r,field,data.get(field,default))
  for c in r.calls:c.update(_samples=deque(),_text='',_mono=time.monotonic())
  project_state=folder/'project-state.json'
  if project_state.exists():
   from travel_run import TravelRun
   state=json.loads(project_state.read_text());r.__class__=TravelRun;r.product=state['product'];r.tasks=state['tasks'];r.started=state.get('started') or r.started;r.base_url='http://127.0.0.1:8001/devteam/v1'
   if r.state in ('running','failed') and 'restarted' in r.error.lower():r.state='interrupted';r.error='Interrupted by service restart. Resume continues from durable merged files.'
  if data.get('mode')=='recorded':
   from guided_run import GuidedRun,EXAMPLE
   r.__class__=GuidedRun;r.recording=json.loads((EXAMPLE/'recording.json').read_text());r.mode='recorded';r.recorded_usage=data.get('recorded_usage')
   if r.state=='interrupted':r.state='stopped';r.error='Recorded playback interrupted; resume to replay.'
  runs[key]=r
 # A browser disconnect never stops work. After a server restart recover the
 # one previously active sustained run from durable merged tasks.
 for recovered in runs.values():
  if getattr(recovered,'travel',False) and recovered.state=='interrupted' and not active_runs():recovered.start()

def persist_sessions():
 path=ROOT.parents[2]/'state/factory-sessions.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps({key:r.id for key,r in runs.items()}));temp.replace(path)

def set_current(value):
 key=session.get()
 if not key:raise HTTPException(400,'Browser session unavailable; reload the application')
 if value is None:runs.pop(key,None)
 else:runs[key]=value
 # Bound idle session metadata. Complete artifacts and audits remain on disk.
 if len(runs)>100:
  for old,r in list(runs.items()):
   if old!=key and not ((r.thread and r.thread.is_alive()) or (getattr(r,'mode','live')=='recorded' and r.snapshot()['state']=='running')):runs.pop(old)
   if len(runs)<=100:break
 persist_sessions()

PROJECT=ROOT.parents[2]
MODEL_DETAILS={
 'fury-lead':{'name':'DeepSeek V4 Flash','checkpoint':'nvidia/DeepSeek-V4-Flash-NVFP4','folder':'DeepSeek-V4-Flash-NVFP4','url':'http://127.0.0.1:8100'},
 'unsloth/Qwen3.6-27B-NVFP4':{'name':'Qwen3.6 27B','checkpoint':'unsloth/Qwen3.6-27B-NVFP4','folder':'Qwen3.6-27B-NVFP4','url':'http://127.0.0.1:8000'}}
def runtime_identity(alias,record,pins,project=PROJECT):
 spec=MODEL_DETAILS[alias];expected=project/'models'/spec['folder'];pin=pins.get(spec['checkpoint'],{}).get('revision');revision=None
 try:revision=(expected/'.cache/huggingface/download/config.json.metadata').read_text().splitlines()[0].strip()
 except (OSError,IndexError):pass
 root=(record or {}).get('root');verified=None
 if record and root and pin and revision:
  verified=record.get('id')==alias and Path(root).resolve()==expected.resolve() and pin==revision
 return {'name':spec['name'],'checkpoint':spec['checkpoint'],'served_alias':alias,'reported_checkpoint':Path(root).name if root else None,'max_context':(record or {}).get('max_model_len'),'pinned_revision':pin,'identity_verified':verified}
class Start(BaseModel):
 model_config=ConfigDict(extra='forbid')
 automatic:bool=False
 product:Literal["short","travel","short-editorial"]="short"
 mode:Literal["live","recorded"]="live"
class Decision(BaseModel):
 model_config=ConfigDict(extra='forbid')
 gate_id:str;decision:str;reviewer:str
class BackendRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 method:str;path:str;body:dict={};run_id:str;version:int
def run():
 current=get_current()
 if current is None:raise HTTPException(404,'No development run in this browser session')
 return current
@router.get('/devteam')
@router.get('/devteam/build')
async def page():return FileResponse(ROOT/'static/devteam.html',headers={'Content-Security-Policy':"frame-src 'self'; object-src 'none'; base-uri 'self'"})
@router.get('/api/devteam/config')
async def config():
 models={};records={}
 try:
  pins=json.loads((PROJECT/'config/model-pins.json').read_text())
 except (OSError,ValueError):pins={}
 async with httpx.AsyncClient(trust_env=False,timeout=2) as client:
  async def inspect(alias,spec):
   try:
    response=await client.get(spec['url']+'/v1/models');response.raise_for_status()
    return alias,next((m for m in response.json().get('data',[]) if m.get('id')==alias),None)
   except (httpx.HTTPError,ValueError):return alias,None
  try:
   response=await client.get('http://127.0.0.1:8001/health');response.raise_for_status();models=response.json().get('backends',{})
  except (httpx.HTTPError,ValueError):pass
  records=dict(await asyncio.gather(*(inspect(alias,spec) for alias,spec in MODEL_DETAILS.items())))
 return {'task_limits':{'specialist_context':32768,'specialist_output':8192,'lead_output':6000,'lead_travel_qa_output':8192},'sandbox_ready':await asyncio.to_thread(available),'models_ready':all(models.get(m) for m in MODEL_DETAILS),'backends':models,'model_details':{alias:runtime_identity(alias,records.get(alias),pins) for alias in MODEL_DETAILS},'event':'AI Week Frankfurt','lead':'fury-lead','specialist':'unsloth/Qwen3.6-27B-NVFP4'}
@router.get('/api/devteam/run')
async def snapshot():
 current=get_current()
 return current.snapshot() if current else {'state':'ready','actors':__import__('devteam').roster()}
@router.post('/api/devteam/runs',status_code=201)
async def start(body:Start):
 with lock:
  current=get_current()
  if body.mode=='live' and active_runs():raise HTTPException(429,'Development capacity is busy (one build). Your session is separate. Retry after the active build finishes.')
  if current and ((current.thread and current.thread.is_alive()) or (getattr(current,'mode','live')=='recorded' and current.snapshot()['state']=='running')):raise HTTPException(409,'A run is already active in this browser')
  if body.mode=='recorded' and sum(getattr(r,'mode','live')=='recorded' and r.snapshot()['state']=='running' for r in runs.values())>=4:raise HTTPException(429,'Guided demonstration capacity is busy (four playbacks). Retry shortly.')
  try:
   from travel_run import TravelRun
   if body.mode=='recorded':
    from guided_run import GuidedRun
    candidate=GuidedRun()
   else:
    candidate=TravelRun() if body.product=='travel' else DevRun(automatic=body.automatic)
    if body.product=='short-editorial':
     from enterprise_design import EDITORIAL_DESIGN
     candidate.design=EDITORIAL_DESIGN;candidate.product_kind='short-editorial'
  except RetentionError as exc:raise HTTPException(409,str(exc)) from exc
  set_current(candidate);candidate.start();return candidate.snapshot()
@router.post('/api/devteam/gate')
async def gate(body:Decision):
 try:run().approve(body.gate_id,body.decision,body.reviewer)
 except ValueError as e:raise HTTPException(409,str(e))
 return run().snapshot()
@router.post('/api/devteam/stop')
async def stop():run().stop();return {'state':'cancelling','notice':'Accepted engine work may continue until cancellation reaches the serving runtime.'}
@router.post('/api/devteam/reset')
async def reset():
 with lock:
  current=get_current()
  if current and ((current.thread and current.thread.is_alive()) or (getattr(current,'mode','live')=='recorded' and current.snapshot()['state']=='running')):raise HTTPException(409,'Stop and wait for the active run')
  set_current(None)
 return {'state':'ready'}
@router.get('/api/devteam/events')
async def events(request:Request):
 async def stream():
  while not await request.is_disconnected():
   current=get_current();data=current.snapshot(compact=True) if current else {'state':'ready','actors':[]}
   data['compact']=True
   for c in data.get('calls',[]):
    c.pop('history',None);c.pop('text_preview',None)
   yield 'id: '+str(data.get('id','idle'))+':'+str(data.get('seq',0))+'\nevent: snapshot\ndata: '+json.dumps(data)+'\n\n';await asyncio.sleep(1)
 return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
@router.get('/api/devteam/export')
async def export():
 r=run()
 if (r.thread and r.thread.is_alive()) or (getattr(r,'mode','live')=='recorded' and r.snapshot()['state']=='running'):raise HTTPException(409,'Stop or complete before export')
 if getattr(r,'mode','live')=='recorded':return Response(json.dumps(r.snapshot()),media_type='application/json',headers={'Content-Disposition':'attachment; filename="recorded-walkthrough.json"'})
 return Response((r.root/'audit.json').read_bytes(),media_type='application/json',headers={'Content-Disposition':'attachment; filename="devteam-audit.json"'})
@router.get('/api/devteam/preview')
async def preview(version:int|None=None,run_id:str|None=None):
 r=run()
 if run_id is not None and run_id!=r.id:raise HTTPException(409,'Preview belongs to a different run')
 if not r.versions:raise HTTPException(409,'No tested preview yet')
 published=next((v for v in r.versions if v['version']==version),None) if version is not None else r.versions[-1]
 if published is None:raise HTTPException(404,'Unknown published preview version')
 v=r.root/('version-'+str(published['version']))
 def read(n):return (v/n).read_text(encoding='utf-8') if (v/n).exists() else ''
 # Parent places this as sandboxed srcdoc. No host credentials, direct network, or same origin.
 from frontend_artwork import artwork_for
 return {'html':read('index.html'),'css':read('styles.css'),'js':read('app.js'),'artwork':artwork_for(v),'version':published,'run_id':r.id}
@router.post('/api/devteam/backend')
async def backend(body:BackendRequest):
 r=run()
 if body.run_id!=r.id:raise HTTPException(409,'Backend belongs to a different run')
 if not r.versions:raise HTTPException(409,'No tested backend')
 published=next((v for v in r.versions if v['version']==body.version),None)
 if published is None:raise HTTPException(404,'Unknown published backend version')
 if body.method not in ('GET','POST') or body.path not in ('/hotels','/bookings'):raise HTTPException(422,'Outside fictional API scope')
 if len(json.dumps(body.body))>4000:raise HTTPException(413,'Request too large')
 try:
  response=await asyncio.to_thread(execute,r.root/('version-'+str(published['version'])),r.data,'api',body.model_dump(exclude={'version','run_id'}))
  return {**response,'preview_version':published['version'],'preview_hash':published['hash'],'run_id':r.id}
 except (RuntimeError,ValueError):raise HTTPException(503,'Isolated generated backend failed')

@router.get('/api/devteam/preview-frame')
async def preview_frame(v:int|None=None,run:str|None=None):
 data=await preview(v,run)
 html=re.sub(r'<script\b[^>]*>[\s\S]*?</script>','',data['html'],flags=re.I)
 html=re.sub(r'<link\b[^>]*>','',html,flags=re.I)
 bridge="(()=>{const parentOrigin=new URL(location.href).origin;let seq=0;const pending=new Map();window.furyApi=(method,path,body={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({kind:'fury-api',id,method,path,body},parentOrigin);setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('Backend timeout'))}},15000)});window.addEventListener('message',e=>{if(e.source!==parent||e.origin!==parentOrigin||e.data?.kind!=='fury-result')return;const p=pending.get(e.data.id);if(!p)return;pending.delete(e.data.id);e.data.error?p.reject(Error(e.data.error)):p.resolve(e.data.response)})})();"
 bridge=bridge.replace("kind:'fury-api',id,method,path,body", "kind:'fury-api',id,method,path,body,version:"+str(data['version']['version'])+",run_id:"+json.dumps(data['run_id']))
 from frontend_artwork import script_for
 artwork=script_for(data.get('artwork',{}))
 code=(bridge+'\n'+artwork+'\n'+data['js']).replace('</script','<\\/script')
 return HTMLResponse('<style>'+data['css']+'</style>'+html+'<script>'+code+'</script>',headers={
  'Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
  'Cache-Control':'no-store'})

@router.get('/api/devteam/status')
async def operator_status():
 return {'active':len(active_runs()),'limit':1,'queued':0,'retained_sessions':len(runs),'jobs':[{'id':r.id,'state':r.state,'elapsed_s':time.time()-r.started if r.started else 0} for r in active_runs()]}


# Sustained product routes use the existing origin and a run-specific project.
# These routes expose only the sandboxed product API, never host services.
def travel_lookup(rid):
 if not re.fullmatch('[0-9a-f]{12}',rid):raise HTTPException(404,'Unknown application')
 r=next((r for r in runs.values() if r.id==rid and getattr(r,'travel',False)),None)
 if r and not r.root.exists():
  archived=ROOT/'devruns-archive'/rid
  if archived.is_dir():r.root=archived;r.candidate=archived/'candidate';r.data=archived/'data'
 if not r:
  # New runs do not invalidate earlier published application URLs. Recover only
  # this run's bounded metadata; never start a worker from a public viewer link.
  folder=ROOT/'devruns'/rid
  if not folder.exists():folder=ROOT/'devruns-archive'/rid
  try:
   from travel_run import TravelRun
   from devteam import roster
   from collections import deque
   audit=json.loads((folder/'audit.json').read_text());saved=json.loads((folder/'project-state.json').read_text())
   r=TravelRun.__new__(TravelRun);r.id=rid;r.root=folder;r.candidate=folder/'candidate';r.data=folder/'data';r.started=saved.get('started') or time.time();r.product=saved['product'];r.tasks=saved['tasks'];r.base_url='http://127.0.0.1:8001/devteam/v1'
   r.lock=threading.RLock();r.stop_event=threading.Event();r.approval=threading.Event();r.thread=None;r.actors=roster();r.changes=[]
   for field,default in [('state','blocked'),('error',''),('events',[]),('calls',[]),('versions',[]),('tests',None),('gate',None),('automatic',True)]:setattr(r,field,audit.get(field,default))
   r.seq=max((e.get('seq',0) for e in r.events),default=0)
   for c in r.calls:c.update(_samples=deque(),_text='',_mono=time.monotonic())
  except (OSError,ValueError,KeyError):raise HTTPException(404,'Unknown application')
 return r
@router.post('/api/devteam/resume')
async def resume():
 with lock:
  r=run()
  if not getattr(r,'travel',False):raise HTTPException(409,'Resume is supported for sustained travel runs')
  if active_runs() or r.snapshot()['state']=='running':raise HTTPException(409,'Development or playback is already active')
  r.start();return r.snapshot()
def published_version(r,version=None):
 if not r.versions:raise HTTPException(409,'No verified application version yet')
 selected=next((v for v in r.versions if v['version']==version),None) if version is not None else r.versions[-1]
 if selected is None:raise HTTPException(404,'Unknown checked application version')
 return selected['version']
@router.get('/travel/{rid}')
async def travel_page(rid:str,version:int|None=None,embed:bool=False):
 r=travel_lookup(rid);selected=published_version(r,version)
 return HTMLResponse('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aster Journeys · Local demonstration</title><link rel="stylesheet" href="/showcase-assets/hp-shell.css"><script defer src="/showcase-assets/hp-shell.js"></script><script defer src="/showcase-assets/device-navigation.js"></script><style>body{margin:0}iframe{border:0;width:100%;height:calc(100vh - 112px);min-height:600px}#notice{padding:20px;font-family:system-ui}</style></head><body>'''+('' if embed else hp_header())+'''<main id="main"><div id="notice">Loading the last verified application…</div><iframe id="app" sandbox="allow-scripts allow-forms allow-modals" title="Aster Journeys"></iframe><script>
 const version='''+str(selected)+''';const rid='''+json.dumps(rid)+''';let token=sessionStorage.getItem('travel-token-'+rid)||'';
 const frame=document.getElementById('app');frame.src='/api/travel/'+rid+'/frame?version='+version;
 window.addEventListener('message',async e=>{if(e.source!==frame.contentWindow||e.origin!=='null'||e.data?.kind!=='travel-api')return;const d=e.data;try{const response=await fetch('/api/travel/'+rid+'/backend?version='+version,{method:'POST',headers:{'Content-Type':'application/json',...(token?{'Authorization':'Bearer '+token}:{})},body:JSON.stringify({method:d.method,path:d.path,body:d.body||{}})});const result=await response.json();if(!response.ok)throw Error(result.detail||'Backend unavailable');if(result.body?.token){token=result.body.token;sessionStorage.setItem('travel-token-'+rid,token)}if(d.path==='/logout'){token='';sessionStorage.removeItem('travel-token-'+rid)}e.source.postMessage({kind:'travel-result',id:d.id,response:result},'*')}catch(err){e.source.postMessage({kind:'travel-result',id:d.id,error:err.message},'*')}});
 frame.onload=()=>document.getElementById('notice').hidden=true;
 </script></main></body></html>''',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'"})
@router.get('/api/travel/{rid}/frame')
async def travel_frame(rid:str,version:int|None=None):
 r=travel_lookup(rid)
 if not r.versions:return HTMLResponse('<p>No verified version yet. Development continues in Agent Factory.</p>',status_code=409)
 v=r.root/('version-'+str(published_version(r,version)))
 html=(v/'index.html').read_text();html=re.sub(r'<script\b[^>]*>[\s\S]*?</script>','',html,flags=re.I);html=re.sub(r'<link\b[^>]*>','',html,flags=re.I)
 bridge="const parentOrigin=new URL(location.href).origin;let seq=0;const pending=new Map();window.furyApi=(method,path,body={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({kind:'travel-api',id,method,path,body},parentOrigin);setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('Backend timeout'))}},15000)});addEventListener('message',e=>{if(e.source!==parent||e.origin!==parentOrigin||e.data?.kind!=='travel-result')return;const p=pending.get(e.data.id);if(!p)return;pending.delete(e.data.id);e.data.error?p.reject(Error(e.data.error)):p.resolve(e.data.response)});"
 return HTMLResponse('<style>'+(v/'styles.css').read_text()+'</style>'+html+'<script>'+ ('(()=>{'+bridge+'})();\n'+(v/'app.js').read_text()).replace('</script','<\\/script')+'</script>',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'"})
class TravelRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 method:str;path:str;body:dict={}
@router.post('/api/travel/{rid}/backend')
async def travel_backend(rid:str,body:TravelRequest,request:Request,version:int|None=None):
 r=travel_lookup(rid)
 if not r.versions:raise HTTPException(409,'No verified backend yet')
 if body.method not in ('GET','POST','PUT','DELETE') or not re.fullmatch(r'/(health|register|login|logout|me|listings(?:/\d+)?|favorites(?:/\d+)?|itineraries(?:/\d+)?|quote|reservations(?:/\d+)?|admin/(?:listings(?:/\d+)?|reservations))',body.path):raise HTTPException(422,'Outside demonstration API')
 if len(json.dumps(body.body))>8000:raise HTTPException(413,'Request too large')
 payload=body.model_dump();payload['headers']={'authorization':request.headers.get('authorization','')[:300]}
 try:
  async with asyncio.timeout(15):
   async with travel_slots:return await asyncio.to_thread(execute,r.root/('version-'+str(published_version(r,version))),r.data,'api',payload)
 except TimeoutError:raise HTTPException(503,'Demo API capacity timed out; retry shortly')
 except (RuntimeError,ValueError):raise HTTPException(503,'Generated application failed; last preview retained')
@router.get('/api/travel/{rid}/docs')
async def travel_docs(rid:str):
 r=travel_lookup(rid)
 from travel_spec import CONTRACT
 return {'application':'Aster Journeys','demonstration':True,'health':'verified' if r.versions else 'building','api':CONTRACT,'request_endpoint':'/api/travel/'+rid+'/backend','example':{'method':'GET','path':'/listings','body':{}},'acceptance':r.product['criteria']}

@router.get('/api/devteam/watch/{rid}')
async def watch_travel(rid:str):
 r=run()
 if r.id!=rid:raise HTTPException(404,'Run is private to its owner')
 snapshot=r.snapshot()
 # Viewers can inspect execution, never acquire another visitor's controls.
 if isinstance(snapshot.get('tests'),dict):snapshot['tests'].pop('persistence_probe',None)
 snapshot['read_only']=True
 return snapshot

@router.api_route('/api/travel/{rid}/app/{path:path}',methods=['GET','POST','PUT','DELETE'])
async def travel_rest(rid:str,path:str,request:Request):
 """Normal HTTP status API over the exact same generated, isolated backend."""
 from fastapi.responses import JSONResponse
 if request.method=='GET':
  payload=dict(request.query_params)
  for key in ('page','page_size','party','max_price'):
   if key in payload:
    try:payload[key]=float(payload[key]) if key=='max_price' else int(payload[key])
    except ValueError:raise HTTPException(400,'Invalid numeric filter '+key)
 else:
  try:payload=await request.json() if await request.body() else {}
  except ValueError:raise HTTPException(400,'Expected JSON request body')
 if not isinstance(payload,dict):raise HTTPException(400,'Expected a JSON object')
 result=await travel_backend(rid,TravelRequest(method=request.method,path='/'+path,body=payload),request)
 if not isinstance(result,dict) or type(result.get('status')) is not int or not 200<=result['status']<=599 or not isinstance(result.get('body'),dict):raise HTTPException(503,'Generated API returned an invalid response')
 return JSONResponse(result['body'],status_code=result['status'],headers={'Cache-Control':'no-store'})
