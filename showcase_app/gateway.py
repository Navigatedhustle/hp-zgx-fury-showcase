"""Local model routing, bounded admission, and exactly-once physical call ledger."""
import anyio,logging,asyncio,json,sqlite3,time,uuid,os,re
from pathlib import Path
import httpx
from urllib.parse import urlparse
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import StreamingResponse,Response
ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'state/slides/app.db';DB.parent.mkdir(parents=True,exist_ok=True)
MODEL='unsloth/Qwen3.6-27B-NVFP4'
LEAD='fury-lead'
BACKENDS={MODEL:('http://127.0.0.1:8000',MODEL),LEAD:('http://127.0.0.1:8100',LEAD)}
app=FastAPI();active={};waiting={}
normal=asyncio.Semaphore(3);total=asyncio.Semaphore(4)
lead_slots=asyncio.Semaphore(1)
LEAD_WAIT_SECONDS=120

def connect():
 c=sqlite3.connect(DB,timeout=15);c.execute('PRAGMA journal_mode=WAL')
 c.execute('CREATE TABLE IF NOT EXISTS execution_intervals(id TEXT PRIMARY KEY,demo TEXT,model TEXT,started REAL,ended REAL,status TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,demo TEXT,role TEXT,model TEXT,status TEXT,started REAL,seconds REAL,input_tokens INTEGER,output_tokens INTEGER,cached_tokens INTEGER,error TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS routing(id TEXT PRIMARY KEY,requested TEXT,actual TEXT,reason TEXT,external_calls INTEGER,started REAL)')
 c.execute('CREATE TABLE IF NOT EXISTS gateway_settings(name TEXT PRIMARY KEY,value REAL)')
 c.execute("INSERT OR IGNORE INTO gateway_settings VALUES ('external_counter_since',?)",(time.time(),))
 c.commit()
 return c
def record(cid,demo,role,model,status,start,usage=None,error=''):
 u=usage or {};d=u.get('prompt_tokens_details') or {}
 with connect() as c:c.execute('INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',(cid,demo,role,model,status,start,time.time()-start,u.get('prompt_tokens'),u.get('completion_tokens'),d.get('cached_tokens'),error))
def execution_start(cid,demo,model):
 with connect() as c:c.execute('INSERT OR REPLACE INTO execution_intervals VALUES (?,?,?,?,NULL,?)',(cid,demo,model,time.time(),'active'))
def execution_end(cid,status):
 with connect() as c:c.execute('UPDATE execution_intervals SET ended=?,status=? WHERE id=?',(time.time(),status,cid))
async def request_body(request):
 raw=bytearray()
 async for chunk in request.stream():
  raw.extend(chunk)
  if len(raw)>1024*1024:raise HTTPException(413,'Inference payload exceeds the supported size')
 try:body=json.loads(raw)
 except (ValueError,UnicodeError):raise HTTPException(400,'Expected a JSON object')
 if not isinstance(body,dict) or not isinstance(body.get('messages'),list):raise HTTPException(422,'Expected an object with a messages array')
 if any(not isinstance(m,dict) for m in body['messages']):raise HTTPException(422,'Each message must be an object')
 if 'model' in body and not isinstance(body['model'],str):raise HTTPException(422,'Model alias must be text')
 return body
def select(prefix,requested):
 if prefix.startswith('lead/'):
  demo=prefix.split('/')[1]
  if demo not in ('vision','translate','trailer','skin'):raise HTTPException(400,'Unknown brief-call demo')
  return demo,LEAD
 demo=prefix.split('/')[0] if '/' in prefix else ('atlas' if prefix=='atlas' else 'slides')
 if demo not in ('atlas','agent','slides','devteam','vision','translate','trailer','skin'):raise HTTPException(400,'Unknown demo')
 if demo!='devteam':return demo,MODEL
 if requested not in BACKENDS:raise HTTPException(400,'Unknown local model alias')
 return 'agent',requested
async def backend_health():
 async with httpx.AsyncClient(trust_env=False,timeout=2) as c:
  async def probe(alias,spec):
   try:
    r=await c.get(spec[0]+'/health');return alias,r.status_code==200
   except httpx.HTTPError:return alias,False
  return dict(await asyncio.gather(*(probe(a,s) for a,s in BACKENDS.items())))
@app.get('/health')
async def health():
 backends=await backend_health()
 with connect() as c:
  external=c.execute('SELECT coalesce(sum(external_calls),0) FROM routing').fetchone()[0]
  since=c.execute("SELECT value FROM gateway_settings WHERE name='external_counter_since'").fetchone()[0]
  recent=[{'requested':r[0],'model':r[1],'reason':r[2],'at':r[3]} for r in c.execute("SELECT requested,actual,reason,started FROM routing WHERE reason!='' ORDER BY started DESC LIMIT 8")]
 return {'ready':backends.get(MODEL,False),'backends':backends,'active':active,'queued':waiting,'limit':4,'normal_limit':3,'atlas_reserved':1,'lead_limit':1,'lead_wait_seconds':LEAD_WAIT_SECONDS,'external_api_calls':external,'external_counter_since':since,'local_only':all(urlparse(u).hostname in ('127.0.0.1','localhost','::1') for u,_ in BACKENDS.values()),'recent_routing':recent}
@app.get('/{prefix:path}/models')
async def models(prefix:str):
 if prefix.startswith('devteam'):
  h=await backend_health();return {'object':'list','data':[{'id':a,'object':'model','ready':h[a]} for a in BACKENDS]}
 async with httpx.AsyncClient(trust_env=False,timeout=3) as c:
  try:r=await c.get('http://127.0.0.1:8000/v1/models');return Response(r.content,r.status_code,media_type='application/json')
  except httpx.HTTPError:raise HTTPException(503,'Local model unavailable')
@app.get('/atlas/health')
async def atlas_health():
 h=await health()
 if not h['ready']:raise HTTPException(503,'Local model unavailable')
 return h
@app.post('/devteam/v1/tokenize')
async def tokenize(request:Request):
 body=await request_body(request);_,alias=select('devteam/v1',body.get('model'))
 body['model']=BACKENDS[alias][1]
 async with httpx.AsyncClient(trust_env=False,timeout=10) as client:
  try:
   response=await client.post(BACKENDS[alias][0]+'/tokenize',json=body);response.raise_for_status()
   return response.json()
  except (httpx.HTTPError,ValueError):raise HTTPException(503,'Selected runtime tokenization unavailable')
@app.post('/{prefix:path}/chat/completions')
async def chat(prefix:str,request:Request):
 body=await request_body(request);demo,alias=select(prefix,body.get('model'))
 requested=alias;reason=''
 if prefix.startswith('lead/'):
  pending=[*active.values(),*waiting.values()]
  if lead_slots.locked() or any(v.get('model')==LEAD for v in pending):
   factory_busy=any(v.get('demo')=='agent' and v.get('model')==LEAD for v in pending)
   alias=MODEL;reason='Routed to Qwen: DeepSeek is busy with Agent Factory' if factory_busy else 'Routed to Qwen: DeepSeek is busy'
  cap=body.get('max_tokens',768)
  if type(cap) is not int or cap<1:raise HTTPException(422,'Brief-call output limit must be a positive integer')
  body['max_tokens']=min(cap,768)
 url,served=BACKENDS[alias];body['model']=served
 external_destination=int(urlparse(url).hostname not in ('127.0.0.1','localhost','::1'))
 if external_destination:raise HTTPException(503,'External inference is disabled')
 if alias==MODEL:body.setdefault('chat_template_kwargs',{})['enable_thinking']=False
 cid=request.headers.get('x-fury-call-id') or uuid.uuid4().hex
 if not re.fullmatch(r'[A-Za-z0-9_:.-]{1,160}',cid):raise HTTPException(422,'Invalid call identity')
 role=request.headers.get('x-fury-role','language')[:80];start=time.time()
 if cid in waiting or cid in active:raise HTTPException(409,'Call already in flight')
 if len(waiting)>=24:raise HTTPException(429,'Shared queue full')
 # A completed physical request cannot be replayed with the same identity.
 with connect() as c:
  if c.execute('SELECT 1 FROM events WHERE id=?',(cid,)).fetchone():raise HTTPException(409,'Physical call identity already recorded')
  c.execute('INSERT INTO routing VALUES (?,?,?,?,?,?)',(cid,requested,alias,reason,external_destination,start))
 waiting[cid]={'demo':demo,'model':alias,'since':start,'routing':reason,'role':role};record(cid,demo,role,alias,'queued',start)
 outcome={'http_status':200}
 async def run():
  usage=None;status='failed';client=None;response=None;acquired=False;normal_acquired=False;lead_acquired=False;error=''
  try:
   # Wait on the scarce lead slot first so lead waiters cannot consume all normal slots.
   if alias==LEAD:await asyncio.wait_for(lead_slots.acquire(),LEAD_WAIT_SECONDS);lead_acquired=True
   if demo!='atlas':await asyncio.wait_for(normal.acquire(),60);normal_acquired=True
   await asyncio.wait_for(total.acquire(),60);acquired=True
   waiting.pop(cid,None);active[cid]={'demo':demo,'model':alias,'since':time.time(),'routing':reason,'role':role};record(cid,demo,role,alias,'active',start)
   client=httpx.AsyncClient(timeout=240,trust_env=False)
   execution_start(cid,demo,alias)
   response=await client.send(client.build_request('POST',url+'/v1/chat/completions',json=body),stream=True)
   response.raise_for_status()
   if body.get('stream'):
    if 'text/event-stream' not in response.headers.get('content-type',''):raise RuntimeError('Unexpected upstream stream type')
    saw_done=False
    async for line in response.aiter_lines():
     if line.startswith('data:') and line[5:].strip()=='[DONE]':saw_done=True
     if line.startswith('data:') and line[5:].strip()!='[DONE]':
      try:
       data=json.loads(line[5:]);usage=data.get('usage') or usage
       if data.get('error'):raise RuntimeError('Upstream streaming error')
      except ValueError as exc:raise RuntimeError('Malformed inference stream') from exc
     yield (line+'\n').encode()
    if not saw_done:raise RuntimeError('Inference stream interrupted before completion')
   else:
    raw=await response.aread();payload=json.loads(raw)
    if payload.get('error'):raise RuntimeError('Upstream error')
    usage=payload.get('usage')
    if demo in ('vision','translate','trailer','skin'):
     payload['fury_routing']={'requested':requested,'model':alias,'reason':reason};raw=json.dumps(payload).encode()
    yield raw
   status='complete'
  except asyncio.CancelledError:status='cancelled';raise
  except Exception as e:
   error=type(e).__name__;outcome['http_status']=e.response.status_code if isinstance(e,httpx.HTTPStatusError) else 504 if isinstance(e,(TimeoutError,httpx.TimeoutException)) else 502
   logging.exception('Inference failed call=%s model=%s',cid,alias)
   yield ('data: '+json.dumps({'error':{'message':'Local inference unavailable','type':error}})+'\n\n').encode() if body.get('stream') else json.dumps({'error':'Local inference unavailable'}).encode()
  finally:
   # Starlette cancels streams inside an AnyIO cancellation scope. Shield socket
   # cleanup so a disconnected browser cannot strand semaphore capacity.
   try:
    with anyio.CancelScope(shield=True):
     async with asyncio.timeout(5):
      if response:await response.aclose()
      if client:await client.aclose()
   finally:
    waiting.pop(cid,None);active.pop(cid,None)
    if acquired:total.release()
    if normal_acquired:normal.release()
    if lead_acquired:lead_slots.release()
    execution_end(cid,status)
    record(cid,demo,role,alias,status,start,usage,error)

 if body.get('stream'):return StreamingResponse(run(),media_type='text/event-stream',headers={'X-Fury-Call-ID':cid,'Cache-Control':'no-store','X-Accel-Buffering':'no'})
 async def collect():return b''.join([chunk async for chunk in run()])
 task=asyncio.create_task(collect())
 try:
  while not task.done():
   await asyncio.wait([task],timeout=.2)
   if await request.is_disconnected():raise asyncio.CancelledError()
  return Response(task.result(),status_code=outcome['http_status'],media_type='application/json',headers={'X-Fury-Call-ID':cid})
 finally:
  if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
connect().close()

@app.on_event('startup')
async def recover_interrupted():
 with connect() as c:
  c.execute("UPDATE execution_intervals SET ended=?,status='interrupted' WHERE ended IS NULL AND demo!='image'",(time.time(),))
  c.execute("UPDATE events SET status='failed',error='Gateway restarted during request' WHERE status IN ('queued','active') AND demo!='image'")

# Apply after route/application middleware registration so Host validation is outermost.
from showcase_app.security import HostGuard, RequestGuard
app.add_middleware(RequestGuard)
app.add_middleware(HostGuard)
