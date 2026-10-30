"""Kokoro voice fallback. Pure English G2P; no copyleft phonemizer backend."""
import asyncio,importlib.metadata,io,json,sys,time,types
from contextlib import asynccontextmanager
from pathlib import Path
import numpy as np
from fastapi import FastAPI,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
from atlas.config import ROOT
from atlas.offline_guard import install as install_offline_guard
install_offline_guard()
from atlas.number_words import num2words
model=None;g2p=None;voice=None;last_ms=None;lock=asyncio.Lock()
def load():
 global model,g2p,voice,last_ms
 import torch
 torch.set_num_threads(4)
 # English Misaki needs a number formatter; supply our MIT implementation.
 module=types.ModuleType('num2words');module.num2words=num2words;sys.modules['num2words']=module
 # Import the documented model directly. Package __init__ imports optional
 # multilingual phonemizers; our English path does not use those modules.
 distribution=importlib.metadata.distribution('kokoro');module=types.ModuleType('kokoro');module.__path__=[str(distribution.locate_file('kokoro'))];sys.modules['kokoro']=module
 from kokoro.model import KModel
 from misaki import en
 import spacy
 if not spacy.util.is_package('en_core_web_sm'):raise RuntimeError('Install-time English tagger is missing; runtime downloads are disabled.')
 p=Path(json.loads((ROOT/'models/kokoro.json').read_text())['path'])
 model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(p/'config.json'),model=str(p/'kokoro-v1_0.pth')).to('cuda').eval()
 voice=torch.load(p/'voices/af_heart.pt',weights_only=True)
 g2p=en.G2P(trf=False,british=False,fallback=None,unk='')
 generate('Welcome. Ask an executive question.')
 _,last_ms=generate('Ready for your next executive question.')
def generate(text):
 import torch
 start=time.perf_counter();ps,tokens=g2p(text)
 if not ps:raise ValueError('No pronunciable text')
 # Sentences are intentionally short; retain every phoneme and avoid truncation.
 if len(ps)+2>model.context_length:raise ValueError('Sentence too long. Split the answer into sentences.')
 with torch.inference_mode():audio=model(ps,voice[len(ps)-1],speed=1.0)
 data=(np.clip(audio.numpy(),-1,1)*32767).astype('<i2').tobytes()
 return data,(time.perf_counter()-start)*1000
@asynccontextmanager
async def lifespan(app):
 await asyncio.to_thread(load)
 yield
app=FastAPI(docs_url=None,redoc_url=None,lifespan=lifespan)
@app.get('/health')
async def health():return {'ready':model is not None,'model':'Kokoro-82M · v1.0','latency_ms':last_ms,'sample_rate':24000}
@app.get('/v1/models')
async def models():return {'data':[{'id':'Kokoro-82M · v1.0','capability':'speech','device':'cuda','voice':'American English','latency_ms':last_ms}]}
class Speech(BaseModel):
 input:str=Field(min_length=1,max_length=1600)
 voice:str='af_heart'
 language:str='en-US'
 response_format:str='pcm'
@app.post('/v1/audio/speech')
async def speech(q:Speech):
 global last_ms
 if q.language not in ['en','en-US']:raise HTTPException(422,'The local fallback voice supports English.')
 async with lock:
  try:data,last_ms=await asyncio.to_thread(generate,q.input)
  except (ValueError,RuntimeError) as e:raise HTTPException(422,str(e)) from e
 return Response(data,media_type='application/octet-stream',headers={'X-Audio-Sample-Rate':'24000','X-Synthesis-Ms':f'{last_ms:.3f}'})
