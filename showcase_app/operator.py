import asyncio,json,sqlite3,time,subprocess
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager
from showcase_app.event import Monitor, authorized
from fastapi.responses import FileResponse,HTMLResponse
from showcase_app.gateway import connect,ROOT
from fastapi.staticfiles import StaticFiles
from showcase_app.ui import ASSETS
from showcase_app.costs import comparison
monitor=Monitor()
@asynccontextmanager
async def lifespan(app):
 task=asyncio.create_task(monitor.run(collect_live))
 try:yield
 finally:
  task.cancel()
  await asyncio.gather(task,return_exceptions=True)
app=FastAPI(lifespan=lifespan)
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
  services=dict(await asyncio.gather(*(health(n,u) for n,u in [('language','http://127.0.0.1:8001/health'),('atlas','http://127.0.0.1:8200/api/health'),('slides','http://127.0.0.1:8765/api/health'),('agent','http://127.0.0.1:8501/_stcore/health'),('image','http://127.0.0.1:8800/health'),('factory_jobs','http://127.0.0.1:8501/api/devteam/status'),('presentation_jobs','http://127.0.0.1:8765/api/booth/status'),('factory_models','http://127.0.0.1:8501/api/devteam/config')])))
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
 try:
  p=await asyncio.create_subprocess_exec('nvidia-smi','--query-gpu=memory.used,utilization.gpu,power.draw','--format=csv,noheader,nounits',stdout=asyncio.subprocess.PIPE)
  raw,_=await asyncio.wait_for(p.communicate(),3);gpu=raw.decode().strip()
 except Exception:gpu='unknown'
 return {'timestamp':time.time(),'location':'HP ZGX Fury','services':services,'totals':totals,'events':rows[:100],'cost_comparison':comparison(rows),'gpu_memory_MiB_util_pct_power_W':gpu,'source_slide_ledger':source,'external_api_calls':'No cloud inference endpoint configured. Runtime egress audit in runbook; no unverified zero claim.'}
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
