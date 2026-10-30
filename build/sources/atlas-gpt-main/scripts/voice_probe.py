"""Exercise generated audio through the real streaming recognition path."""
import asyncio,json,time,wave
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
import websockets
async def run():
 with wave.open('eval/question.wav','rb') as f:
  sr=f.getframerate();pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
 audio=resample_poly(pcm.astype(float),320,441).astype('<i2').tobytes() if sr==22050 else pcm.tobytes()
 events=[];started=time.perf_counter()
 async with websockets.connect('ws://127.0.0.1:8200/api/listen') as ws:
  async def receive():
   async for raw in ws:
    d=json.loads(raw);d['observed_ms']=(time.perf_counter()-started)*1000;events.append(d);print(d,flush=True)
    if d.get('type','').endswith('.completed'):return
  task=asyncio.create_task(receive())
  await ws.send(json.dumps({'type':'session.update','session':{'sample_rate':16000,'language':'en','endpointing_ms':10000}}))
  await asyncio.sleep(.1)
  for i in range(0,len(audio),5120):
   await ws.send(audio[i:i+5120]);await asyncio.sleep(.16)
  await ws.send(json.dumps({'type':'input_audio_buffer.commit'}))
  await asyncio.wait_for(task,15)
 Path('eval/voice-stream-events.json').write_text(json.dumps(events,indent=2))
asyncio.run(run())
