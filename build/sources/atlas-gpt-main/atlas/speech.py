"""Local speech with exact text normalization and reproducible audio caching."""
import asyncio,hashlib,re,time
import httpx
from atlas.config import ROOT
SPEECH='http://127.0.0.1:8204'
CACHE=ROOT/'artifacts/audio';CACHE.mkdir(parents=True,exist_ok=True)
lock=asyncio.Lock()
def normalize(text):
 # Expand formatting, never calculate a new business number.
 text=re.sub(r'\$([\d,.]+)([BMK])\b',lambda m:m[1]+' '+{'B':'billion','M':'million','K':'thousand'}[m[2]]+' dollars',text)
 text=re.sub(r'\bQ4\b','fourth quarter',text)
 text=re.sub(r'\bFY27\b','fiscal year 2027',text)
 return text.replace('·',' ').replace('−','minus ')
def sentences(text):return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])',text) if s.strip()]
def cached(text,voice,language):
 normalized=normalize(text)
 key=hashlib.sha256(('kokoro-v1.0|'+voice+'|'+language+'|'+normalized).encode()).hexdigest()
 return CACHE/(key+'.pcm'),normalized
async def synthesize(text,voice='af_heart',language='en-US'):
 path,normalized=cached(text,voice,language)
 if path.exists():return path,True,0.0
 async with lock:
  if path.exists():return path,True,0.0
  start=time.perf_counter()
  async with httpx.AsyncClient(timeout=45,trust_env=False) as c:
   r=await c.post(SPEECH+'/v1/audio/speech',json={'input':normalized,'voice':voice,'language':language,'response_format':'pcm'});r.raise_for_status()
   if len(r.content)<200 or len(r.content)%2:raise ValueError('Invalid local PCM response')
   temp=path.with_suffix('.tmp');temp.write_bytes(r.content);temp.replace(path)
  return path,False,(time.perf_counter()-start)*1000
