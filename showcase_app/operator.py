import asyncio,json,sqlite3,time,subprocess
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from showcase_app.event import Monitor, authorized
from fastapi.responses import FileResponse,HTMLResponse,StreamingResponse,JSONResponse
from showcase_app.gateway import connect,ROOT
from fastapi.staticfiles import StaticFiles
from showcase_app.ui import ASSETS
from showcase_app.costs import comparison
from showcase_app import workloads,trailer,samples
from showcase_app.creative_auth import private_key
monitor=Monitor()
@asynccontextmanager
async def lifespan(app):
 trailer.visitors.start();private_key()
 task=asyncio.create_task(monitor.run(collect_live))
 privacy=asyncio.create_task(trailer.sweep())
 try:yield
 finally:
  for sid in list(trailer.visitors.sessions):await trailer.erase(sid)
  tasks=[task,privacy,*[j['_task'] for j in workloads.JOBS.values() if not j['_task'].done()]]
  for pending in tasks:pending.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
app=FastAPI(lifespan=lifespan)
app.include_router(workloads.router);app.include_router(trailer.router);app.include_router(samples.router)
app.mount("/showcase-assets",StaticFiles(directory=ASSETS),name="showcase-assets")
def sync_agent():
 for path in (ROOT/'build/sources/fury_agent_factory/runs').glob('*.sqlite'):
  try:
   with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as src:
    meta=json.loads(src.execute("SELECT payload FROM metadata WHERE id='run'").fetchone()[0])
    calls=[json.loads(x[0]) for x in src.execute('SELECT payload FROM calls')]
   with connect() as dest:
    for call in calls:
     if call.get('started_at') is None:continue  # A client-queued task is not a dispatched model request.
     cid=meta['run_id']+':'+call['id'];u=call.get('usage') or {};started=call.get('queued_at') or time.time()
     # Upsert same physical call ID; never create a second row for the source ledger.
     dest.execute('INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',(cid,'agent',call['agent'],call['model'],call['status'],started,(call.get('ended_at') or time.time())-started,u.get('input'),u.get('output'),u.get('cached'),'source call failed' if call['status']=='failed' else ''))
  except (OSError,sqlite3.Error,KeyError,ValueError):continue
async def collect_live():
 await asyncio.to_thread(sync_agent)
 async with httpx.AsyncClient(timeout=2,trust_env=False) as c:
  async def health(name,url):
   try:r=await c.get(url);d=r.json() if 'json' in r.headers.get('content-type','') else {};return name,{'connected':r.status_code==200,'ready':d.get('ready', d.get('llm',{}).get('ok',r.status_code==200)),'data':d}
   except Exception:return name,{'connected':False}
  services=dict(await asyncio.gather(*(health(n,u) for n,u in [('language','http://127.0.0.1:8001/health'),('atlas','http://127.0.0.1:8200/api/health'),('slides','http://127.0.0.1:8765/api/health'),('agent','http://127.0.0.1:8501/_stcore/health'),('image','http://127.0.0.1:8800/health'),('factory_jobs','http://127.0.0.1:8501/api/devteam/status'),('presentation_jobs','http://127.0.0.1:8765/api/booth/status'),('factory_models','http://127.0.0.1:8501/api/devteam/config'),('tts','http://127.0.0.1:8204/health'),('asr','http://127.0.0.1:8202/health')])))
 with connect() as c:
  c.row_factory=sqlite3.Row
  rows=[dict(r) for r in c.execute('SELECT * FROM events ORDER BY started DESC')]
  try:source=dict(c.execute('SELECT count(*) as requests,sum(prompt_tokens) as input,sum(completion_tokens) as output FROM llmcall').fetchone())
  except Exception:source=None
 totals={}
 for row in rows:
  t=totals.setdefault(row['demo'],{'requests':0,'input':0,'output':0,'cached':0,'unknown_usage':0,'failures':0,'images':0,'seconds':0,'completed_seconds':0,'completed_output':0})
  if row['status']=='complete' and row['demo']!='image' and row['output_tokens'] is not None:
   t['completed_seconds']+=row['seconds'];t['completed_output']+=row['output_tokens'] or 0
  t['requests']+=1;t['input']+=row['input_tokens'] or 0;t['output']+=row['output_tokens'] or 0;t['cached']+=row['cached_tokens'] or 0;t['unknown_usage']+=int(row['input_tokens'] is None and row['demo']!='image');t['failures']+=int(row['status'] in ('failed','cancelled'));t['images']+=int(row['demo']=='image' and row['status']=='complete');t['seconds']+=row['seconds']
 from showcase_app.telemetry import sample
 live={'timestamp':time.time(),'location':'HP ZGX Fury','services':services,'totals':totals,'events':rows[:100],'cost_comparison':comparison(rows),'source_slide_ledger':source}
 measured=await sample(live);g=measured['gpu'];live.update(telemetry=measured,gpu_memory_MiB_util_pct_power_W=','.join(str(g[k]) for k in ('hbm_used_mib','utilization','power_w')),external_api_calls=measured['external_api_calls'])
 from showcase_app.model_hub import models
 measured['models']=models(live);measured['workflow_jobs']=workloads.summaries()
 measured['factory_jobs']=services.get('factory_jobs',{}).get('data',{}).get('jobs',[])
 return live
@app.get('/')
async def home():return FileResponse(ROOT/'showcase_app/launcher.html')
@app.get('/operator')
async def operator():return FileResponse(ROOT/'showcase_app/operator.html')
@app.get('/methodology')
async def methodology():return FileResponse(ROOT/'showcase_app/methodology.html')

@app.get('/connect')
async def connect_device_page():return FileResponse(ROOT/'showcase_app/connect.html')

@app.get('/api/device-access')
async def device_access_status():
 from showcase_app.device_access import device_status
 return await device_status()

@app.get('/connect/qr.svg')
async def device_access_qr():
 from showcase_app.device_access import device_status
 from fastapi.responses import Response
 from fastapi import HTTPException
 import qrcode,qrcode.image.svg
 status=await device_status()
 if not status.get('connect_url'):raise HTTPException(503,'Tailscale DNS is unavailable')
 qr=qrcode.make(status['connect_url'],image_factory=qrcode.image.svg.SvgPathImage)
 return Response(qr.to_string(),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})


@app.get('/api/live')
async def live():
 if monitor.latest_live is None:
  async with monitor.lock:
   if monitor.latest_live is None:monitor.latest_live=await collect_live()
 return monitor.latest_live

@app.get('/showcase-telemetry')
@app.get('/api/telemetry/stream')
async def telemetry_stream(request:Request):
 async def events():
  last=None
  while not await request.is_disconnected():
   current=monitor.stream
   if current is not None and current!=last:
    last=current;yield 'data: '+current+'\n\n'
   try:
    async with monitor.changed:
     await asyncio.wait_for(monitor.changed.wait_for(lambda:monitor.stream!=last),15)
   except asyncio.TimeoutError:yield ': keepalive\n\n'
 return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

@app.get('/api/demo/jobs/{cid}')
async def demo_job(cid:str,request:Request):
 job=workloads.JOBS.get(cid)
 if not job:raise HTTPException(404)
 if job['kind']=='trailer':
  session=trailer.session(request)
  if job.get('_session')!=session['id']:raise HTTPException(404)
 return JSONResponse(workloads.public(job),headers={'Cache-Control':'no-store'})

@app.get('/api/models')
async def model_hub():
 from showcase_app.model_hub import models
 return {'models':models(monitor.latest_live or {}),'as_of':(monitor.latest_live or {}).get('timestamp')}

PROOF_FILES={'ops/runtime.py','config/gb300.json','config/model-pins.json','config/creative-models.json','showcase_app/gateway.py','build/sources/fury_agent_factory/devteam_sandbox.py','showcase_app/visitor_store.py','AGENTS.md','docs/ASSET-MANIFEST.md'}
@app.get('/api/source/{name:path}')
async def source_proof(name:str):
 if name not in PROOF_FILES:raise HTTPException(404)
 return FileResponse(ROOT/name,media_type='text/plain')

@app.get('/models')
@app.get('/performance')
@app.get('/economics')
@app.get('/secure')
@app.get('/about')
async def mission_page():return FileResponse(ROOT/'showcase_app/mission.html')

@app.get('/experience/{demo}')
async def experience_page(demo:str):
 if demo not in ('vision','translate','video','trailer'):raise HTTPException(404)
 return FileResponse(ROOT/'showcase_app/experience.html')

@app.post('/api/video')
async def video_submit(request:Request):
 body=await request.json()
 async with httpx.AsyncClient(trust_env=False,timeout=10) as client:
  r=await client.post('http://127.0.0.1:8800/api/video',json=body)
 return JSONResponse(r.json(),status_code=r.status_code)

@app.get('/api/creative/jobs/{cid}')
async def creative_job(cid:str):
 if not __import__('re').fullmatch('[0-9a-f]{32}',cid):raise HTTPException(404)
 async with httpx.AsyncClient(trust_env=False,timeout=5) as client:r=await client.get('http://127.0.0.1:8800/api/jobs/'+cid)
 return JSONResponse(r.json(),status_code=r.status_code)

@app.get('/api/creative/media/{name}')
async def creative_media(name:str):
 if not __import__('re').fullmatch(r'[0-9a-f]{32}(?:-[1-4])?\.(?:png|mp4)',name):raise HTTPException(404)
 path=ROOT/'state/images'/name
 if not path.is_file():raise HTTPException(404)
 return FileResponse(path)

@app.get('/api/event')
async def event_telemetry():
 if monitor.latest is None:raise HTTPException(503,'Event telemetry is starting')
 return monitor.latest

@app.post('/api/event/reset')
async def reset_event(request:Request):
 if not authorized(request.headers.get('x-fury-presenter')):raise HTTPException(403,'Presenter code required; retrieve it through your authorized SSH terminal')
 body=await request.json()
 try:session=await asyncio.to_thread(monitor.store.reset,body.get('name','Conference session'))
 except (ValueError,AttributeError):raise HTTPException(422,'Use an event name between 1 and 80 characters')
 return {'session':session,'jobs_preserved':True}

@app.get('/demos')
async def demos():return FileResponse(ROOT/'showcase_app/launcher.html')

@app.get('/stations')
async def stations():return FileResponse(ROOT/'showcase_app/stations.html')

@app.get('/why-hp')
async def why_hp():return FileResponse(ROOT/'showcase_app/why-hp.html')

@app.get('/presenter')
async def presenter():return FileResponse(ROOT/'showcase_app/presenter.html')
