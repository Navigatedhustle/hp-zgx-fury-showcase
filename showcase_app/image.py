import asyncio,time,uuid,os,threading,logging,hmac,secrets
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse
from pydantic import BaseModel,Field
from typing import Literal
from showcase_app.creative import CreativeLane,reference_image,VIDEO_MODEL,VIDEO_PROFILE
from showcase_app.gateway import record,execution_start,execution_end,connect
from showcase_app.visitor_store import VISITORS
from showcase_app.creative_auth import private_key
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'state/images';OUT.mkdir(parents=True,exist_ok=True)
lane=CreativeLane();pipe=None;jobs={};queue=asyncio.Queue(maxsize=3)

def load():
 global pipe
 lane.load();pipe=lane.flux
async def worker():
 while True:
  cid,prompt,options=await queue.get();start=time.time();job=jobs[cid];kind=job.get('kind','image');model=job['model'];suffix='.mp4' if kind=='video' else '.png';private=job.get('_private',False);demo='trailer' if private else kind;output=job.get('_output',OUT/(cid+suffix))
  try:
   if job['_stop'].is_set():
    job['status']='cancelled';continue
   job.update(status='generating',started=start);execution_start(cid,demo,model)
   peaks=await asyncio.to_thread(lane.run,kind,prompt,output,job['_stop'],options,job);job.update(peaks)
   if job['_stop'].is_set():raise InterruptedError('Image cancelled')
   job.update(status='complete',stage='Complete',seconds=time.time()-start,**({'artifact':output.name} if private else {'url':(job.get('urls') or ['/images/'+output.name])[0]}))
   record(cid,demo,'generation',model,'complete',start)
  except InterruptedError:
   job.update(status='cancelled');output.unlink(missing_ok=True)
   record(cid,demo,'generation',model,'cancelled',start)
  except Exception:
   logging.error('Private creative job failed id=%s',cid) if private else logging.exception('Creative job failed id=%s',cid)
   job.update(status='failed',error='Creative generation failed. Retry or ask the operator to inspect job '+cid[:12])
   record(cid,demo,'generation',model,'failed',start,error='generation failed')
  finally:
   reference=options.pop('reference',None)
   if reference is not None:reference.close()
   options.clear()
   job.pop('_options',None);job['ended']=time.time();execution_end(cid,job['status']);queue.task_done()
@asynccontextmanager
async def lifespan(app):
 await asyncio.to_thread(load);task=asyncio.create_task(worker());yield;task.cancel()
from fastapi.staticfiles import StaticFiles
from showcase_app.ui import ASSETS
app=FastAPI(lifespan=lifespan)
from showcase_app.chrome import TelemetryProxy
app.add_middleware(TelemetryProxy)
app.mount("/showcase-assets",StaticFiles(directory=ASSETS),name="showcase-assets")
class Prompt(BaseModel):
 prompt:str=Field(min_length=5,max_length=1500)
 batch:Literal[1,2,4]=1
 seed:int=Field(default=42,ge=0,le=4294967295)
 aspect:Literal['1:1','16:9','9:16','4:3']='1:1'
 style:Literal['Photographic','Product','Cinematic','Illustration','Architectural']|None=None
STYLES={'Photographic':'Professional photography, natural lighting. ','Product':'Premium product photography, carefully controlled studio lighting, no real brands. ','Cinematic':'Cinematic composition, dramatic lighting and rich color grading. ','Illustration':'Detailed original editorial illustration. ','Architectural':'Elegant architectural visualization, beautiful material detail and lighting. '}
SIZES={'1:1':(768,768),'16:9':(1024,576),'9:16':(576,1024),'4:3':(896,672)}
@app.post('/api/generate')
async def submit(p:Prompt):
 cid=uuid.uuid4().hex
 if queue.full():raise HTTPException(429,'Image queue full; try after current work completes')
 # Bound in-memory metadata; artifacts remain inspectable on disk.
 for old in list(jobs):
  if len(jobs)<200:break
  if jobs[old]['status'] in ('complete','failed','cancelled'):jobs.pop(old)
 width,height=SIZES[p.aspect]
 options={'width':width,'height':height,'batch':p.batch,'seed':p.seed}
 jobs[cid]={'kind':'image','status':'queued','created':time.time(),'model':'FLUX.2-klein-4B','location':'Fury host','seed':p.seed,'batch':p.batch,'style':p.style,'aspect':p.aspect,'_stop':threading.Event(),'_options':options}
 queue.put_nowait((cid,STYLES.get(p.style,'')+p.prompt,options));return {'id':cid,**public(jobs[cid])}
class Edit(Prompt):
 image:str=Field(min_length=20,max_length=12000000)
 width:Literal[1024]=1024
 height:Literal[576]=576
class Video(Prompt):
 image:str|None=Field(default=None,min_length=20,max_length=12000000)
 height:Literal[704,480]=704
 steps:int=Field(default=4 if VIDEO_PROFILE=='longlive' else 50,ge=1,le=50)
 guidance:float=Field(default=1.0 if VIDEO_PROFILE=='longlive' else 5.0,ge=1,le=6)

def enqueue_reference(p,kind):
 if queue.full():raise HTTPException(429,'Creative queue full; try after current work completes')
 try:reference=reference_image(p.image) if p.image is not None else None
 except (ValueError,OSError):raise HTTPException(422,'Invalid bounded reference image')
 cid=uuid.uuid4().hex;model=VIDEO_MODEL if kind=='video' else 'FLUX.2-klein-4B'
 options={'reference':reference,'height':p.height,'width':1280 if kind=='video' and p.height==704 else 832 if kind=='video' else p.width}
 if kind=='video':options.update(steps=p.steps,guidance=p.guidance)
 jobs[cid]={'kind':kind,'status':'queued','created':time.time(),'model':model,'location':'Fury + Grace CPU offload','_stop':threading.Event()}
 jobs[cid]['_options']=options
 queue.put_nowait((cid,p.prompt,options));return {'id':cid,**public(jobs[cid])}
@app.post('/api/edit')
async def edit(p:Edit):return enqueue_reference(p,'image')
@app.post('/api/video')
async def video(p:Video):return enqueue_reference(p,'video')

class PrivateCreative(BaseModel):
 session:str=Field(pattern='^[0-9a-f]{32}$')
 kind:Literal['image','video']
 slot:int=Field(ge=0,le=2)
 prompt:str=Field(min_length=5,max_length=1500)

@app.post('/api/private/creative')
async def private_creative(p:PrivateCreative,request:Request):
 if not hmac.compare_digest(request.headers.get('x-fury-creative-key',''),private_key()):raise HTTPException(403,'Local creative authority required')
 if queue.full():raise HTTPException(429,'Creative lane queue is full')
 folder=VISITORS/('session-'+p.session)
 if not folder.is_dir() or folder.is_symlink():raise HTTPException(410,'Visitor session was deleted')
 source=folder/('photo.jpg' if p.kind=='image' else f'keyframe-{p.slot}.png')
 if not source.is_file() or source.is_symlink():raise HTTPException(410,'Consented camera image or keyframe is unavailable')
 from PIL import Image
 with Image.open(source) as im:reference=im.convert('RGB')
 cid=uuid.uuid4().hex;name=f'keyframe-{p.slot}.png' if p.kind=='image' else f'clip-{p.slot}.mp4'
 options={'reference':reference,'width':1024 if p.kind=='image' else 1280,'height':576 if p.kind=='image' else 704,'steps':4,'guidance':1.0,'seed':42+p.slot}
 jobs[cid]={'kind':p.kind,'status':'queued','created':time.time(),'model':'FLUX.2-klein-4B' if p.kind=='image' else VIDEO_MODEL,'location':'Fury + Grace CPU offload','_private':True,'_output':folder/name,'_stop':threading.Event(),'_options':options}
 queue.put_nowait((cid,p.prompt,options))
 return {'id':cid,**public(jobs[cid])}
@app.get('/api/jobs/{cid}')
async def job(cid:str,request:Request):
 if cid not in jobs:raise HTTPException(404)
 if jobs[cid].get('_private') and not hmac.compare_digest(request.headers.get('x-fury-creative-key',''),private_key()):raise HTTPException(404)
 return public(jobs[cid])
def public(job):return {k:v for k,v in job.items() if not k.startswith('_')}
@app.post('/api/jobs/{cid}/cancel')
async def cancel(cid:str,request:Request):
 if cid not in jobs:raise HTTPException(404,'Unknown image job')
 if jobs[cid].get('_private') and not hmac.compare_digest(request.headers.get('x-fury-creative-key',''),private_key()):raise HTTPException(404)
 j=jobs[cid]
 if j['status'] in ('queued','generating'):
  queued=j['status']=='queued';j['_stop'].set();j['status']='cancelled' if queued else 'cancelling'
  if queued:
   reference=j.get('_options',{}).pop('reference',None)
   if reference is not None:reference.close()
 return public(j)
@app.get('/health')
async def health():return {'jobs':[{'id':cid,**{k:j[k] for k in ('kind','status','created','started','ended','stage','model','steps_done','steps_total','seconds') if k in j}} for cid,j in list(jobs.items())[-30:]],'ready':pipe is not None,'queued':sum(j['status']=='queued' for j in jobs.values()),'active':sum(j['status'] in ('generating','cancelling') for j in jobs.values()),'limit':1,'queue_limit':3,**lane.placement()}
@app.get('/images/{name}')
async def image(name:str):
 if not __import__('re').fullmatch('[0-9a-f]{32}(?:-[1-4])?\\.(?:png|mp4)',name):raise HTTPException(404)
 return FileResponse(OUT/name)
@app.get('/')
async def index():return FileResponse(ROOT/'showcase_app/image.html')
