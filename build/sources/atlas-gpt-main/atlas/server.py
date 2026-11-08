import asyncio
import json
import hashlib
import uuid
from collections import OrderedDict
import time
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from atlas.config import ROOT, NAME, PERSONAS, GOLDEN, UPGRADE_GOLDEN, DB
from atlas.offline_guard import install as install_offline_guard
install_offline_guard()
from atlas.analytics import execute,forecast_quarter,grant_forecast
from atlas.brain import Brain
from atlas.telemetry import Telemetry
from atlas.decisions import Decisions
from atlas.developer import Developer
import os

brain=Brain();decisions=Decisions();telemetry=Telemetry();last_results={};result_history=OrderedDict();stage_metrics={};speech_inventory=[]
developer=Developer(brain)
FEATURES={k:os.environ.get('ATLAS_'+k.upper(),'1')!='0' for k in ['orb','developer','graph','documents','feed']}
traces=OrderedDict()
def stage(trace,label):
    if not trace:return
    traces.setdefault(trace,[]).append({'label':label,'timestamp':time.time()})
    while len(traces)>64:traces.popitem(last=False)

SPEECH='http://127.0.0.1:8202'

@asynccontextmanager
async def lifespan(app):
    if not DB.exists():
        from atlas.data.generate import generate
        generate()
    from atlas.data.upgrade import ensure
    await asyncio.to_thread(ensure)
    await asyncio.to_thread(forecast_quarter);await asyncio.to_thread(grant_forecast)
    yield

app=FastAPI(title=NAME,docs_url=None,redoc_url=None,lifespan=lifespan)
from showcase_app.chrome import TelemetryProxy
app.add_middleware(TelemetryProxy)
app.mount('/showcase-assets',StaticFiles(directory=ROOT.parents[2]/'showcase_app/assets'),name='showcase-assets')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
(ROOT/'artifacts').mkdir(exist_ok=True)
app.mount('/artifacts',StaticFiles(directory=ROOT/'artifacts'),name='artifacts')

@app.middleware('http')
async def headers(request,call_next):
    from showcase_app.frame_policy import station_ancestors
    response=await call_next(request)
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' ws://localhost:8200 ws://127.0.0.1:8200 ; object-src 'none'; frame-ancestors 'none'"
    if request.url.path=='/':response.headers['Content-Security-Policy']=response.headers['Content-Security-Policy'].replace("frame-ancestors 'none'",'frame-ancestors '+station_ancestors(request.url.hostname))
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/') else 'no-cache'
    return response

@app.get('/')
async def index():return FileResponse(ROOT/'static'/'index.html')

@app.get('/api/config')
async def config():
    return {'name':NAME,'features':FEATURES,'personas':PERSONAS,'questions':[{'persona':p,'tool':t,'question':q} for p,t,q in GOLDEN+UPGRADE_GOLDEN if FEATURES['documents'] or t!='search_knowledge'],'footer':'All data synthetic. Fictional companies. Inference on HP ZGX Fury host; Local demonstration; optional remote access is configured by the operator.','attract_idle_seconds':60}

@app.get('/api/health')
async def health():return {'ready':True,'name':NAME,'data':DB.exists()}

@app.get('/api/stages/{trace}')
async def stages(trace:str):
    async def stream():
        seen=0
        for _ in range(400):
            events=traces.get(trace,[])
            for event in events[seen:]:yield 'data: '+json.dumps(event)+'\n\n'
            seen=len(events)
            if events and events[-1]['label'] in ['verified','unavailable']:break
            await asyncio.sleep(.025)
    return StreamingResponse(stream(),media_type='text/event-stream')

class Query(BaseModel):
    question:str=Field(min_length=1,max_length=1200)
    persona:str='enterprise'
    llm_narration:bool=True
    fast:bool=False
    result_id:str|None=Field(default=None,max_length=64)
    trace:str|None=Field(default=None,max_length=64)
    use_documents:bool=True
    use_graph:bool=True

def selected_result(q):
    output=result_history.get(q.result_id) if q.result_id else None
    if output is None:raise HTTPException(409,'Ask a business question before exporting a brief.')
    if output['persona']!=q.persona:raise HTTPException(409,'Choose an answer from the current persona before exporting.')
    return output

@app.post('/api/query')
async def query(q:Query,request:Request):
    task=asyncio.create_task(query_work(q))
    try:
        async with asyncio.timeout(100):
            while not task.done():
                await asyncio.wait([task],timeout=.2)
                if await request.is_disconnected():raise asyncio.CancelledError()
            return task.result()
    except TimeoutError:raise HTTPException(504,'Atlas took too long. Please try another question.')
    finally:
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)

async def query_work(q:Query):
    if q.persona not in PERSONAS:raise HTTPException(422,'Unknown persona')
    start=time.perf_counter()
    stage(q.trace,'heard')
    if q.persona=='developer':
        if not FEATURES['developer']:raise HTTPException(409,'Developer mode is switched off')
        stage(q.trace,'tool picked')
        job=await developer.generate(q.question)
        if job['task']=='connect':job['connection']=await connection_info()
        stage(q.trace,'computed');stage(q.trace,'verified')
        answer='Code generated locally. Review it, then run it against the read-only synthetic database.' if not job.get('informational') else ('The forecast adds booked and recurring revenue to pipeline weighted by historical win rates. Profit applies the contribution margin and subtracts fixed expense. Here is the actual read-only function.' if job['task']=='explain' else 'The local coding endpoint and measured generation telemetry are shown. Point your tools at this device.')
        from atlas.grounding import check
        return {'developer':job,'answer':answer,'grounding':check(answer,{}),'timings':{'total_ms':(time.perf_counter()-start)*1000},'persona':'developer'}
    from atlas.documents import knowledge_intent,search
    if FEATURES['documents'] and q.use_documents and knowledge_intent(q.question):
        stage(q.trace,'tool picked')
        try:output=await search(q.question,q.persona)
        except (ValueError,httpx.HTTPError) as e:raise HTTPException(503,'Local document index is unavailable') from e
        stage(q.trace,'computed')
        if not output['grounding']['passed']:raise HTTPException(422,'Cited answer failed numerical grounding')
        output.update(question=q.question,persona=q.persona,routing={'engine':'local vector retrieval'},timings={'total_ms':(time.perf_counter()-start)*1000})
        stage(q.trace,'verified');return output
    await brain.health()
    if q.fast:
        from atlas.router import route
        tool,kwargs=route(q.question,q.persona);meta={'engine':'deterministic fast path','route_ms':0}
    else:tool,kwargs,meta=await brain.select(q.question,q.persona)
    stage(q.trace,'tool picked')
    if tool=='export_brief':
        from atlas.briefs import export
        return {'action':'export','artifacts':await asyncio.to_thread(export,selected_result(q))}
    if tool is None:
        stage(q.trace,'unavailable')
        return JSONResponse({'unsupported':True,'answer':'I can help with the business questions in the question drawer. Choose a forecast, risk, site, hiring or university question.','grounding':{'passed':True,'checked':0,'unsupported':[]},'timings':{'total_ms':(time.perf_counter()-start)*1000}},status_code=200)
    t=time.perf_counter();output=await asyncio.to_thread(execute,tool,kwargs);analytics_ms=(time.perf_counter()-t)*1000
    if FEATURES['graph'] and q.use_graph:
        from atlas.knowledge import provenance
        output=await asyncio.to_thread(provenance,output,q.persona,kwargs)
    stage(q.trace,'computed')
    t=time.perf_counter();answer,grounding,narration_ms=await brain.narrate(output,q.llm_narration);grounding_ms=(time.perf_counter()-t)*1000-narration_ms
    output.update({'question':q.question,'persona':q.persona,'answer':answer,'grounding':grounding,'routing':meta,'timings':{'routing_ms':meta['route_ms'],'analytics_ms':analytics_ms,'narration_ms':narration_ms,'grounding_ms':max(0,grounding_ms),'total_ms':(time.perf_counter()-start)*1000}})
    await decisions.health()
    t=time.perf_counter();judgment=await decisions.judge(output)
    if judgment:output['decision']=judgment;output['timings']['decision_ms']=(time.perf_counter()-t)*1000
    output['timings']['total_ms']=(time.perf_counter()-start)*1000
    stage(q.trace,'verified')
    output['result_id']=uuid.uuid4().hex[:24]
    result_history[output['result_id']]=output
    result_history.move_to_end(output['result_id'])
    while len(result_history)>64:result_history.popitem(last=False)
    last_results[q.persona]=output;stage_metrics.update(output['timings'])
    return output

@app.get('/api/knowledge/{persona}')
async def knowledge_graph(persona:str):
    if persona not in PERSONAS:raise HTTPException(404)
    if not FEATURES['graph']:raise HTTPException(409,'Second Brain is switched off')
    from atlas.knowledge import graph
    output=await asyncio.to_thread(graph,persona)
    from atlas.documents import load,stats as document_stats
    index=load();docs=[d for d in index['documents'] if d['persona']==('enterprise' if persona=='developer' else persona)]
    nodes=list(output['nodes']);edges=list(output['edges']);existing={n['id'] for n in nodes}
    for d in docs:
        did='document:'+d['id'];nodes.append({'id':did,'type':'document','label':d['title'],'record':d,'value':len(d['passages']),'table':'documents'})
        for p in d['passages']:
            pid='passage:'+p['id'];nodes.append({'id':pid,'type':'passage','label':d['title'],'record':p,'value':len(p['text'].split()),'table':'passages'});edges.append({'source':did,'target':pid,'type':'contains'})
            edges.extend({'source':pid,'target':rid,'type':'grounded in'} for rid in p['row_ids'] if rid in existing)
    from collections import Counter
    output={**output,'nodes':nodes,'edges':edges,'counts':{'nodes':len(nodes),'edges':len(edges),'node_types':dict(Counter(n['type'] for n in nodes)),'edge_types':dict(Counter(e['type'] for e in edges))},'refreshed_at':index.get('refreshed_at') or output['refreshed_at']}
    live=await asyncio.to_thread(telemetry.read)
    return {**output,'decision':{'base_model':'jaredpalmer/kev-4b','calibration':'released checkpoint temperature calibration; no business-domain held-out validation','fine_tune':'Not fine-tuned: general calibration','measured_result':None},'documents':document_stats(persona),'local':{'host':'HP ZGX Fury · London','tx_upper_bound_bytes':live['non_loopback_tx_bytes'],'counter_label':live['tx_label']}}

@app.post('/api/knowledge/initialize')
async def initialize_knowledge():
    if not FEATURES['documents']:raise HTTPException(409,'Documents are switched off')
    from atlas.documents import initialize
    return await initialize()

class Feed(BaseModel):
    persona:str

@app.post('/api/knowledge/feed')
async def feed_knowledge(q:Feed):
    if not FEATURES['feed'] or not FEATURES['documents']:raise HTTPException(409,'Feed the brain is switched off')
    if q.persona not in ['enterprise','university']:raise HTTPException(422,'Select Enterprise or University')
    from atlas.documents import feed
    try:return await feed(q.persona,brain)
    except (ValueError,httpx.HTTPError) as e:raise HTTPException(422,str(e)) from e

class CodeRun(BaseModel):
    job_id:str=Field(max_length=64)
    code:str|None=Field(default=None,max_length=16000)

@app.post('/api/developer/run')
async def developer_run(q:CodeRun):
    if not FEATURES['developer']:raise HTTPException(409,'Developer mode is switched off')
    try:return await developer.execute(q.job_id,q.code)
    except KeyError as e:raise HTTPException(404,str(e)) from e

async def connection_info():
    async with httpx.AsyncClient(timeout=3,trust_env=False) as c:
        r=await c.get(brain.base+'/v1/models');r.raise_for_status();models=r.json()['data']
        h=await c.get('http://127.0.0.1:8001/health');live=h.json()
    return {'host':'127.0.0.1','port':8001,'base_url':brain.base+'/v1','model':models[0]['id'],'context_size':65536,'slots':4,'busy_slots':len(live['active']),'tokens_per_second':developer.last_stats.get('tokens_per_second'),'measurement':'Latest measured generation only; shared admission reserves capacity for Atlas.','curl':'See operator runbook; local OpenAI-compatible endpoint.'}

@app.get('/api/developer/connection')
async def developer_connection():
    try:return await connection_info()
    except (httpx.HTTPError,KeyError,ValueError) as e:raise HTTPException(503,'Local coding model is unavailable') from e

@app.get('/api/telemetry')
async def stats():
    # Keep discovery local to this request: simultaneous screens must not
    # append to a shared list and show the same engine twice.
    inventory=[]
    await brain.health()
    try:
        async with httpx.AsyncClient(timeout=.6,trust_env=False) as c:
            r=await c.get(SPEECH+'/v1/models');r.raise_for_status();inventory=r.json().get('data',[])
    except (httpx.HTTPError,ValueError):pass
    try:
        async with httpx.AsyncClient(timeout=.6,trust_env=False) as c:
            r=await c.get('http://127.0.0.1:8204/v1/models');r.raise_for_status();inventory+=r.json().get('data',[])
    except (httpx.HTTPError,ValueError):pass
    models=[]
    try:
        async with httpx.AsyncClient(timeout=.4,trust_env=False) as c:
            r=await c.get('http://127.0.0.1:8205/health');r.raise_for_status();v=r.json()
            if v.get('ready'):models.append({'role':'Person detection','name':v['model'],'latency_ms':v.get('latency_ms')})
    except (httpx.HTTPError,ValueError):pass
    if FEATURES['documents']:
        try:
            async with httpx.AsyncClient(timeout=.4,trust_env=False) as c:
                r=await c.get('http://127.0.0.1:8206/health');r.raise_for_status();embedding=r.json()
                if embedding.get('ready'):models.append({'role':'Knowledge embeddings','name':'Local embeddings · 1B','latency_ms':embedding.get('latency_ms')})
        except (httpx.HTTPError,ValueError):pass
    await decisions.health()
    if decisions.loaded:models.append({'role':'Decisions','name':'System One · 4B · BF16','latency_ms':decisions.last_model_ms})
    if brain.loaded:models.append({'role':'Language','name':brain.name,'latency_ms':brain.last_ms})
    for m in inventory:
        id_=m.get('id','');cap=m.get('capability',m.get('task',''))
        models.append({'role':cap or ('Speech' if 'magpie' in id_.lower() else 'Recognition'),'name':id_,'latency_ms':m.get('latency_ms') if cap=='speech' else stage_metrics.get('asr_ms')})
    if not models:models=[{'role':'Analytics','name':'Deterministic tools · ready','latency_ms':stage_metrics.get('analytics_ms')}]
    return {**await asyncio.to_thread(telemetry.read),'models':models,'llm_tokens':brain.tokens,'decision_tokens':decisions.tokens,'latencies':stage_metrics,'voice_ready':{'speech','transcription'}<={m.get('capability') for m in inventory}}

@app.post('/api/transcribe')
async def transcribe(request:Request):
    audio=await request.body()
    if len(audio)>8000000:raise HTTPException(413,'Audio too long')
    start=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15,trust_env=False) as c:
            r=await c.post(SPEECH+'/v1/audio/transcriptions',files={'file':('question.wav',audio,'audio/wav')},data={'language':'en'});r.raise_for_status();d=r.json()
    except httpx.HTTPError as e:raise HTTPException(503,'Local speech recognition is unavailable. Use the question box.') from e
    stage_metrics['asr_ms']=(time.perf_counter()-start)*1000
    return {**d,'asr_ms':stage_metrics['asr_ms']}

class Speech(BaseModel):
    text:str=Field(min_length=1,max_length=1600)
    voice:str='af_heart'
    language:str='en-US'

@app.post('/api/speech')
async def speech(s:Speech):
    from atlas.speech import synthesize
    start=time.perf_counter()
    try:path,hit,synthesis_ms=await synthesize(s.text,s.voice,s.language)
    except (httpx.HTTPError,ValueError) as e:raise HTTPException(503,'Local speech generation is unavailable. The verified text answer is ready.') from e
    stage_metrics['tts_ms']=(time.perf_counter()-start)*1000
    stage_metrics['tts_synthesis_ms']=synthesis_ms
    stage_metrics['tts_cache_hit']=hit
    return FileResponse(path,media_type='application/octet-stream',headers={'X-Audio-Sample-Rate':'24000','X-Local-Audio-Cache':'hit' if hit else 'miss'})

@app.websocket('/api/listen')
async def listen(socket:WebSocket):
    await socket.accept()
    # Proxy only to our loopback speech server; PCM never leaves the machine.
    import websockets
    try:
        async with websockets.connect('ws://127.0.0.1:8202/v1/audio/transcriptions/realtime',max_size=2000000) as upstream:
            commit_started=None
            async def send():
                nonlocal commit_started
                while True:
                    m=await socket.receive()
                    if m['type']=='websocket.disconnect':return
                    if m.get('text'):
                        try:
                            if json.loads(m['text']).get('type')=='input_audio_buffer.commit':commit_started=time.perf_counter()
                        except (ValueError,AttributeError):pass
                    await upstream.send(m.get('bytes') if m.get('bytes') is not None else m.get('text',''))
            async def receive():
                async for m in upstream:
                    if isinstance(m,str):
                        if commit_started is not None:
                            try:
                                if json.loads(m).get('type','').endswith('.completed'):stage_metrics['asr_ms']=(time.perf_counter()-commit_started)*1000
                            except (ValueError,AttributeError):pass
                        await socket.send_text(m)
            tasks=[asyncio.create_task(send()),asyncio.create_task(receive())]
            done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in pending:task.cancel()
            results=await asyncio.gather(*tasks,return_exceptions=True)
            for result in results:
                if isinstance(result,Exception):raise result
    except (OSError,WebSocketDisconnect,websockets.WebSocketException):
        try:await socket.send_json({'error':'Local voice connection unavailable'});await socket.close()
        except RuntimeError:pass

@app.post('/api/brief')
async def brief(q:Query):
    from atlas.briefs import export
    return await asyncio.to_thread(export,selected_result(q))

@app.post('/api/metrics')
async def metrics(request:Request):
    d=await request.json()
    for k in ['ttfa_ms','audio_playback_ms']:
        if k in d and isinstance(d[k],(int,float)) and 0<=d[k]<=120000:stage_metrics[k]=d[k]
    return {'ok':True}

@app.get('/api/source/{table}')
async def download_source(table:str):
    if table not in {p.stem for p in (ROOT/'data'/'csv').glob('*.csv')}:raise HTTPException(404)
    return FileResponse(ROOT/'data'/'csv'/f'{table}.csv',filename=f'atlas-{table}.csv',media_type='text/csv')

@app.post('/api/detect')
async def detect(request:Request):
    image=await request.body()
    if len(image)>1000000:raise HTTPException(413,'Frame too large')
    try:
        async with httpx.AsyncClient(timeout=2,trust_env=False) as c:
            r=await c.post('http://127.0.0.1:8205/detect',content=image,headers={'Content-Type':'image/jpeg'});r.raise_for_status()
        result=r.json();stage_metrics['vision_ms']=result['latency_ms'];return result
    except (httpx.HTTPError,ValueError) as e:raise HTTPException(503,'Person detection is loading. The live camera feed is available.') from e

# Apply after route/application middleware registration so Host validation is outermost.
from showcase_app.security import HostGuard
app.add_middleware(HostGuard)
