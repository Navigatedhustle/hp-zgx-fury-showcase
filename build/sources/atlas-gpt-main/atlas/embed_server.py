"""Local revision-pinned commercially licensed embedding model; no runtime downloads."""
import asyncio,json,time
from contextlib import asynccontextmanager
from atlas.config import ROOT
from atlas.offline_guard import install
install()
from fastapi import FastAPI
from pydantic import BaseModel,Field
model=None;tokenizer=None;lock=asyncio.Lock();last_ms=None
@asynccontextmanager
async def lifespan(app):
    global model,tokenizer
    import torch
    from transformers import AutoModel,AutoTokenizer
    path=ROOT/'models/embed';torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(path,trust_remote_code=True,local_files_only=True)
    model=AutoModel.from_pretrained(path,trust_remote_code=True,local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval()
    yield
app=FastAPI(docs_url=None,redoc_url=None,lifespan=lifespan)
class Input(BaseModel):
    texts:list[str]=Field(min_length=1,max_length=64)
    query:bool=False

def encode(texts,query):
    global last_ms
    import torch
    started=time.perf_counter();results=[]
    for at in range(0,len(texts),4):
        batch=tokenizer([('query: ' if query else 'passage: ')+text[:10000] for text in texts[at:at+4]],padding=True,truncation=True,max_length=512,return_tensors='pt').to('cuda')
        with torch.inference_mode():
            hidden=model(**batch,use_cache=False).last_hidden_state
            mask=batch['attention_mask'][...,None];vectors=(hidden*mask).sum(1)/mask.sum(1);vectors=torch.nn.functional.normalize(vectors.float(),dim=-1)
        results.extend(vectors.cpu().tolist())
    last_ms=(time.perf_counter()-started)*1000
    return results
@app.get('/health')
async def health():return {'ready':model is not None,'model':json.loads((ROOT/'models/embed.json').read_text())['id'],'latency_ms':last_ms,'dimension':2048}
@app.post('/embed')
async def embed(data:Input):
    async with lock:vectors=await asyncio.to_thread(encode,data.texts,data.query)
    return {'vectors':vectors,'elapsed_ms':last_ms,'dimension':len(vectors[0])}
