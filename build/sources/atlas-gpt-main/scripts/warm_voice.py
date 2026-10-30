"""Pre-render the fixed golden narration on the same local speech engine."""
import asyncio,json,time
from pathlib import Path
import httpx
from atlas.config import GOLDEN
from atlas.speech import synthesize,sentences
async def run():
 records=[]
 async with httpx.AsyncClient(timeout=40,trust_env=False) as c:
  for _ in range(40):
   try:
    r=await c.get('http://127.0.0.1:8200/api/health');r.raise_for_status();break
   except httpx.HTTPError:await asyncio.sleep(.25)
  for persona,expected,q in GOLDEN:
   r=await c.post('http://127.0.0.1:8200/api/query',json={'question':q,'persona':persona});r.raise_for_status();d=r.json()
   if d.get('unsupported') or d.get('tool')!=expected:print('ROUTE MISMATCH',q,d.get('tool'),flush=True)
   for sentence in sentences(d['answer']):
    path,hit,ms=await synthesize(sentence)
    records.append({'question':q,'text':sentence,'cached':hit,'synthesis_ms':ms,'audio_bytes':path.stat().st_size})
    print(f'{len(records)} {ms:.0f}ms cached={hit} {sentence}',flush=True)
 Path('eval/voice-warmup.json').write_text(json.dumps(records,indent=2))
asyncio.run(run())
