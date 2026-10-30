"""In-memory person detection. Frames are never stored or sent off device."""
import asyncio,io,time
from contextlib import asynccontextmanager
from pathlib import Path
from PIL import Image
from fastapi import FastAPI,Request,HTTPException
from atlas.config import ROOT
from atlas.offline_guard import install as install_offline_guard
install_offline_guard()
model=None;last_ms=None;lock=asyncio.Lock()
@asynccontextmanager
async def lifespan(app):
 global model,last_ms
 import torch
 from rfdetr import RFDETRNano
 torch.set_num_threads(4)
 model=await asyncio.to_thread(RFDETRNano,pretrain_weights=str(ROOT/'models/rf-detr-nano.pth'),device='cuda')
 await asyncio.to_thread(model.predict,Image.new('RGB',(640,360),'white'),threshold=.5)
 start=time.perf_counter()
 await asyncio.to_thread(model.predict,Image.new('RGB',(640,360),'white'),threshold=.5)
 last_ms=(time.perf_counter()-start)*1000
 yield
app=FastAPI(docs_url=None,redoc_url=None,lifespan=lifespan)
@app.get('/health')
async def health():return {'ready':model is not None,'model':'RF-DETR Nano','latency_ms':last_ms}
@app.post('/detect')
async def detect(request:Request):
 global last_ms
 data=await request.body()
 if len(data)>1000000:raise HTTPException(413,'Frame too large')
 try:
  im=Image.open(io.BytesIO(data));im.load()
  if im.width*im.height>2000000:raise ValueError()
  im=im.convert('RGB')
 except Exception:raise HTTPException(422,'Send a valid camera JPEG')
 async with lock:
  start=time.perf_counter();detections=await asyncio.to_thread(model.predict,im,threshold=.55);last_ms=(time.perf_counter()-start)*1000
 from rfdetr.assets.coco_classes import COCO_CLASSES
 boxes=[]
 for xyxy,score,cid in zip(detections.xyxy,detections.confidence,detections.class_id):
  if COCO_CLASSES[int(cid)].lower()!='person':continue
  x1,y1,x2,y2=[float(v) for v in xyxy]
  boxes.append({'x':max(0,x1/im.width),'y':max(0,y1/im.height),'width':min(1,(x2-x1)/im.width),'height':min(1,(y2-y1)/im.height),'confidence':float(score)})
 return {'people':len(boxes),'boxes':boxes,'latency_ms':last_ms,'model':'RF-DETR Nano','frames_retained':0}
