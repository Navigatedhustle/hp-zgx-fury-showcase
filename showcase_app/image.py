import asyncio,time,uuid,os,threading,logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,FileResponse
from pydantic import BaseModel,Field
from showcase_app.gateway import record,execution_start,execution_end
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'state/images';OUT.mkdir(parents=True,exist_ok=True)
pipe=None;jobs={};queue=asyncio.Queue(maxsize=3)
def load():
 global pipe
 import torch
 from diffusers import Flux2KleinPipeline
 pipe=Flux2KleinPipeline.from_pretrained(str(ROOT/'models/FLUX.2-klein-4B'),torch_dtype=torch.bfloat16,local_files_only=True).to('cuda')
def generate(prompt,path,stop):
 import torch
 torch.cuda.reset_peak_memory_stats()
 def checkpoint(pipe,step,timestep,kwargs):
  if stop.is_set():raise InterruptedError('Image cancelled')
  return kwargs
 pipe(prompt=prompt,callback_on_step_end=checkpoint,height=768,width=768,num_inference_steps=4,guidance_scale=1.0,generator=torch.Generator('cuda').manual_seed(42)).images[0].save(path)
 return {'gpu_peak_allocated_bytes':torch.cuda.max_memory_allocated(),'gpu_peak_reserved_bytes':torch.cuda.max_memory_reserved()}
async def worker():
 while True:
  cid,prompt=await queue.get();start=time.time();job=jobs[cid]
  try:
   if job['_stop'].is_set():
    job['status']='cancelled';continue
   job.update(status='generating',started=start);execution_start(cid,'image','FLUX.2-klein-4B')
   peaks=await asyncio.to_thread(generate,prompt,OUT/(cid+'.png'),job['_stop']);job.update(peaks)
   if job['_stop'].is_set():raise InterruptedError('Image cancelled')
   job.update(status='complete',seconds=time.time()-start,url='/images/'+cid+'.png')
   record(cid,'image','generation','FLUX.2-klein-4B','complete',start)
  except InterruptedError:
   job.update(status='cancelled');(OUT/(cid+'.png')).unlink(missing_ok=True)
   record(cid,'image','generation','FLUX.2-klein-4B','cancelled',start)
  except Exception:
   logging.exception('Image job failed id=%s',cid)
   job.update(status='failed',error='Image generation failed. Retry or ask the operator to inspect job '+cid[:12])
   record(cid,'image','generation','FLUX.2-klein-4B','failed',start,error='generation failed')
  finally:
   job['ended']=time.time();execution_end(cid,job['status']);queue.task_done()
@asynccontextmanager
async def lifespan(app):
 await asyncio.to_thread(load);task=asyncio.create_task(worker());yield;task.cancel()
from fastapi.staticfiles import StaticFiles
from showcase_app.ui import ASSETS
app=FastAPI(lifespan=lifespan)
app.mount("/showcase-assets",StaticFiles(directory=ASSETS),name="showcase-assets")
class Prompt(BaseModel):prompt:str=Field(min_length=5,max_length=1500)
@app.post('/api/generate')
async def submit(p:Prompt):
 cid=uuid.uuid4().hex
 if queue.full():raise HTTPException(429,'Image queue full; try after current work completes')
 # Bound in-memory metadata; artifacts remain inspectable on disk.
 for old in list(jobs):
  if len(jobs)<200:break
  if jobs[old]['status'] in ('complete','failed','cancelled'):jobs.pop(old)
 jobs[cid]={'status':'queued','created':time.time(),'model':'FLUX.2-klein-4B','location':'Fury host','_stop':threading.Event()}
 queue.put_nowait((cid,p.prompt));return {'id':cid,**public(jobs[cid])}
@app.get('/api/jobs/{cid}')
async def job(cid:str):
 if cid not in jobs:raise HTTPException(404)
 return public(jobs[cid])
def public(job):return {k:v for k,v in job.items() if not k.startswith('_')}
@app.post('/api/jobs/{cid}/cancel')
async def cancel(cid:str):
 if cid not in jobs:raise HTTPException(404,'Unknown image job')
 j=jobs[cid]
 if j['status'] in ('queued','generating'):
  j['_stop'].set();j['status']='cancelling'
 return public(j)
@app.get('/health')
async def health():return {'ready':pipe is not None,'queued':sum(j['status']=='queued' for j in jobs.values()),'active':sum(j['status'] in ('generating','cancelling') for j in jobs.values()),'limit':1,'queue_limit':3}
@app.get('/images/{name}')
async def image(name:str):
 if not __import__('re').fullmatch('[0-9a-f]{32}\\.png',name):raise HTTPException(404)
 return FileResponse(OUT/name)
@app.get('/')
async def index():return FileResponse(ROOT/'showcase_app/image.html')
