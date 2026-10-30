"""Real local English streaming ASR, backed by pinned Apache-2.0 Zipformer weights."""
import asyncio,json,io
from pathlib import Path
from contextlib import asynccontextmanager
import numpy as np,sherpa_onnx,soundfile as sf
from fastapi import FastAPI,WebSocket,WebSocketDisconnect,UploadFile,File,HTTPException
R=Path(__file__).resolve().parents[1]/'models/asr';recognizer=None
@asynccontextmanager
async def lifespan(app):
 global recognizer
 recognizer=sherpa_onnx.OnlineRecognizer.from_transducer(tokens=str(R/'tokens.txt'),encoder=str(R/'encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx'),decoder=str(R/'decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx'),joiner=str(R/'joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx'),num_threads=4,sample_rate=16000,feature_dim=80,decoding_method='greedy_search',enable_endpoint_detection=False)
 yield
app=FastAPI(lifespan=lifespan)
def decode(stream,samples,rate,final=False):
 stream.accept_waveform(rate,samples)
 if final:stream.accept_waveform(rate,np.zeros(int(rate*.5),dtype=np.float32));stream.input_finished()
 while recognizer.is_ready(stream):recognizer.decode_stream(stream)
 return recognizer.get_result(stream)
@app.get('/v1/models')
async def models():return {'data':[{'id':'Zipformer English streaming 2023-06-26 int8','capability':'transcription','device':'cpu','ready':recognizer is not None}]}
@app.post('/v1/audio/transcriptions')
async def transcription(file:UploadFile=File(...)):
 data=await file.read(8000001)
 if len(data)>8000000:raise HTTPException(413)
 audio,rate=sf.read(io.BytesIO(data),dtype='float32')
 if audio.ndim>1:audio=audio.mean(axis=1)
 stream=recognizer.create_stream();text=await asyncio.to_thread(decode,stream,audio,rate,True);return {'text':text}
@app.websocket('/v1/audio/transcriptions/realtime')
async def realtime(ws:WebSocket):
 await ws.accept();stream=recognizer.create_stream();rate=16000;total=0;last=''
 try:
  while True:
   msg=await ws.receive()
   if msg['type']=='websocket.disconnect':break
   if msg.get('bytes'):
    raw=msg['bytes'];total+=len(raw)
    if total>8000000:await ws.close(code=1009);break
    text=await asyncio.to_thread(decode,stream,np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768,rate)
    if text and text!=last:await ws.send_json({'type':'transcription.delta','text':text});last=text
   elif msg.get('text'):
    d=json.loads(msg['text'])
    if d.get('type')=='session.update':rate=int(d.get('session',{}).get('sample_rate',16000))
    if d.get('type')=='input_audio_buffer.commit':
     text=await asyncio.to_thread(decode,stream,np.zeros(0,dtype=np.float32),rate,True);await ws.send_json({'type':'transcription.completed','text':text});break
 except WebSocketDisconnect:pass
