"""Consented camera-to-trailer orchestration; visitor data is ephemeral and local."""
import asyncio
import base64
import io
import json
import re
import time
from pathlib import Path
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from showcase_app.visitor_store import VisitorStore
from showcase_app.creative_auth import private_key
from showcase_app.creative import reference_image
from showcase_app.workloads import JOBS, create, public, stage, llm

router=APIRouter()
visitors=VisitorStore()
GENRES={'Space Mission':'a peaceful original space exploration mission','Mountain Rescue':'a hopeful mountain rescue and safe return','Heist Planner':'a playful puzzle-room planning adventure, no crime or weapons','Superhero Origin':'an original unbranded hero discovering the power to protect a city','Race Day':'an original closed-course electric racing adventure, no brands','Deep Sea Explorer':'a peaceful deep-sea science expedition'}
COOKIE='fury_visitor'
SENSITIVE=re.compile(r'\b(?:male|female|man|woman|boy|girl|young|elderly|ethnicity|race|Asian|Caucasian|Latino|African|gender|aged|teenager)\b',re.I)
UNSAFE=re.compile(r'\b(?:gun|rifle|pistol|weapon|gore|blood|kill|nude|naked|sexual|Batman|Superman|Marvel|Disney|Star Wars|celebrity|Ferrari|Porsche|Nike)\b',re.I)
SCRIPT_SCHEMA={'type':'object','properties':{'shots':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'object','properties':{'description':{'type':'string','maxLength':300},'camera':{'type':'string','maxLength':100}},'required':['description','camera'],'additionalProperties':False}},'titles':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'string','maxLength':50}},'narrator':{'type':'string','maxLength':160}},'required':['shots','titles','narrator'],'additionalProperties':False}
APPEARANCE_SCHEMA={'type':'object','properties':{k:{'type':'string','maxLength':200} for k in ('hair','clothing','setting')},'required':['hair','clothing','setting'],'additionalProperties':False}


def session(request,touch=False):
    found=visitors.get(request.cookies.get(COOKIE),touch=touch)
    if not found:raise HTTPException(401,'Consent is required or the visitor session has expired')
    return found


async def erase(sid):
    old=visitors.delete(sid)
    if old:
        async with httpx.AsyncClient(trust_env=False,timeout=3,headers={'x-fury-creative-key':private_key()}) as client:
            for cid in old.get('creative_ids',[]):
                try:await client.post('http://127.0.0.1:8800/api/jobs/'+cid+'/cancel')
                except httpx.HTTPError:pass
        if old.get('job_id'):JOBS.pop(old['job_id'],None)
    return old


async def sweep():
    while True:
        expired=[sid for sid,s in list(visitors.sessions.items()) if time.time()-s['touched']>=900]
        for sid in expired:await erase(sid)
        await asyncio.sleep(5)


class Consent(BaseModel):agreed:Literal[True]


@router.post('/api/trailer/consent')
async def consent(body:Consent,request:Request):
    if request.cookies.get(COOKIE):await erase(request.cookies[COOKIE])
    s=visitors.consent();result=JSONResponse({'consented':True,'retention_idle_seconds':900})
    secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    result.set_cookie(COOKIE,s['id'],httponly=True,samesite='strict',secure=secure)
    result.headers['Cache-Control']='no-store'
    return result


@router.post('/api/trailer/touch')
async def touch(request:Request):session(request,touch=True);return {'active':True}


@router.post('/api/trailer/done')
async def done(request:Request):
    await erase(request.cookies.get(COOKIE));response=JSONResponse({'deleted':True,'message':'Your photo and video files have been deleted. Any in-flight render is stopping and its output will be discarded.'})
    response.delete_cookie(COOKIE);response.headers['Cache-Control']='no-store';return response


class TrailerInput(BaseModel):
    genre:Literal['Space Mission','Mountain Rescue','Heist Planner','Superhero Origin','Race Day','Deep Sea Explorer']
    source:Literal['camera']
    image:str=Field(min_length=20,max_length=12000000)


def validate_script(text):
    data=json.loads(text)
    if set(data)!=set(SCRIPT_SCHEMA['required']) or len(data['shots'])!=3 or len(data['titles'])!=2:raise ValueError('Invalid three-shot screenplay')
    if len(data['narrator'].split())>24 or any(len(t.split())>7 for t in data['titles']):raise ValueError('Screenplay titles or narration exceed their bound')
    if UNSAFE.search(json.dumps(data)):raise ValueError('Screenplay violates the original PG genre constraints')
    for shot in data['shots']:
        if set(shot)!={'description','camera'} or not all(isinstance(v,str) and v.strip() for v in shot.values()):raise ValueError('Invalid shot')
    return data


async def creative(job,s,kind,slot,prompt):
    async with httpx.AsyncClient(trust_env=False,timeout=30,headers={'x-fury-creative-key':private_key()}) as client:
        while True:
            if s['deleted'] or not s['path'].is_dir():raise asyncio.CancelledError()
            result=await client.post('http://127.0.0.1:8800/api/private/creative',headers={'x-fury-creative-key':private_key()},json={'session':s['id'],'kind':kind,'slot':slot,'prompt':prompt[:1500]})
            if result.status_code!=429:break
            job['stage']='Queued in shared creative lane';await asyncio.sleep(1)
        result.raise_for_status();cid=result.json()['id'];s.setdefault('creative_ids',[]).append(cid)
        try:
            while True:
                if s['deleted'] or not s['path'].is_dir():raise asyncio.CancelledError()
                r=await client.get('http://127.0.0.1:8800/api/jobs/'+cid);r.raise_for_status();value=r.json()
                job['creative_progress']={k:value[k] for k in ('status','stage','model','steps_done','steps_total','frames_generated','frames_encoded','fps','width','height','render_seconds','gpu_peak_allocated_bytes') if k in value}
                if value['status']=='complete':return value
                if value['status'] in ('failed','cancelled'):raise RuntimeError('Creative stage did not complete')
                await asyncio.sleep(.5)
        except asyncio.CancelledError:
            try:await client.post('http://127.0.0.1:8800/api/jobs/'+cid+'/cancel')
            except httpx.HTTPError:pass
            raise


async def make_trailer(job,s,genre):
    began=time.monotonic();folder=s['path'];job.update(genre=genre,shot_count=3,keyframes=[],clips=[])
    stage(job,'Screenplay','fury-lead')
    script=validate_script(await llm(job,'trailer',[{'role':'system','content':'Write an original PG trailer as the required JSON. Exactly three shots starring the person from a consented camera photo. No sensitive traits, named people, celebrities, real brands, franchises, copyrighted characters, sexual content, gore or weapons. Two title cards of at most seven words. Narrator under 25 words. Describe a coherent beginning, reveal and hopeful payoff. Keep each shot description under 35 words.'},{'role':'user','content':GENRES[genre]}],lead=True,max_tokens=700,schema=SCRIPT_SCHEMA))
    job['screenplay']=script
    stage(job,'Visible continuity','unsloth/Qwen3.6-27B-NVFP4')
    photo='data:image/jpeg;base64,'+base64.b64encode((folder/'photo.jpg').read_bytes()).decode()
    appearance=json.loads(await llm(job,'trailer',[{'role':'system','content':'Describe only visible hair, clothing and setting needed for visual continuity. Never infer or mention age, ethnicity, gender identity, sex, race, health, religion or other sensitive attributes. Use unspecified if unclear. Do not call the person a man or woman. Return only the required JSON.'},{'role':'user','content':[{'type':'text','text':'Describe visible hair, clothing and setting only.'},{'type':'image_url','image_url':{'url':photo}}]}],max_tokens=240,schema=APPEARANCE_SCHEMA))
    if SENSITIVE.search(json.dumps(appearance)):
        appearance={'hair':'Use the reference photo without additional description','clothing':'Use the reference photo','setting':'Use the selected fictional genre'}
        job['continuity_note']='Appearance description omitted; reference-photo continuity is used.'
    continuity='; '.join(appearance.values())
    for index,shot in enumerate(script['shots']):
        if index==2 and time.monotonic()-began>135:
            job.update(shot_count=2,simplification='Using two shots to keep the visitor experience under four minutes.');break
        stage(job,f'Keyframe {index+1}','FLUX.2-klein-4B')
        await creative(job,s,'image',index,f'Keep the reference subject face and hair consistent. {continuity}. Original cinematic PG scene: {shot["description"]}. Plain unbranded clothing. No text, logos, weapons or recognizable franchises.')
        job['keyframes'].append(f'/api/trailer/media/keyframe-{index}.png')
    for index,shot in enumerate(script['shots'][:job['shot_count']]):
        stage(job,f'Clip {index+1}','Wan2.2-TI2V-5B + LongLive-Plug')
        await creative(job,s,'video',index,f'{shot["description"]} Camera: {shot["camera"]}. Keep the reference face and clothes consistent. Natural restrained motion. No text, logos, brands, weapons, gore or sexual content.')
        job['clips'].append(f'/api/trailer/media/clip-{index}.mp4')
        if index==1 and job['shot_count']==3 and time.monotonic()-began>180:
            job.update(shot_count=2,simplification='Using two finished shots to keep the visitor experience under four minutes.');break
    stage(job,'Trailer narration','Kokoro-82M / am_michael')
    async with httpx.AsyncClient(trust_env=False,timeout=60) as client:
        response=await client.post('http://127.0.0.1:8204/v1/audio/speech',json={'input':script['narrator'],'voice':'am_michael','language':'en-US','response_format':'pcm'});response.raise_for_status()
    if s['deleted'] or not folder.is_dir():raise asyncio.CancelledError()
    (folder/'narration.pcm').write_bytes(response.content)
    stage(job,'Final cut','Local FFmpeg + synthesized soundtrack')
    from showcase_app.trailer_render import assemble
    await asyncio.to_thread(assemble,folder,job['shot_count'],script['titles'],lambda:s['deleted'])
    if s['deleted'] or not folder.is_dir():raise asyncio.CancelledError()
    job.update(video='/api/trailer/media/trailer.mp4',end_to_end_seconds=time.monotonic()-began,download='/api/trailer/download')


@router.post('/api/trailer/start')
async def start(body:TrailerInput,request:Request):
    s=session(request,touch=True)
    if s.get('job_id'):raise HTTPException(409,'Choose Done or New visitor before another trailer')
    try:
        image=reference_image(body.image);image.thumbnail((960,960));image.save(s['path']/'photo.jpg','JPEG',quality=88);image.close()
    except (ValueError,OSError):raise HTTPException(422,'Camera frame could not be read')
    job=create('trailer','Action Trailer',lambda j:make_trailer(j,s,body.genre),private=s);s['job_id']=job['id']
    return public(job)


@router.get('/api/trailer/media/{name}')
async def media(name:str,request:Request):
    s=session(request)
    if not re.fullmatch(r'(?:keyframe-[0-2]\.png|clip-[0-2]\.mp4|trailer\.mp4)',name):raise HTTPException(404)
    path=s['path']/name
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,headers={'Cache-Control':'no-store'})


@router.get('/api/trailer/download')
async def download(request:Request):
    if request.url.hostname not in ('localhost','127.0.0.1','::1') or request.client.host not in ('localhost','127.0.0.1','::1'):
        raise HTTPException(403,'Download is available only through localhost on the station')
    s=session(request,touch=True);path=s['path']/'trailer.mp4'
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,filename='Fury-Action-Trailer.mp4',headers={'Cache-Control':'no-store'})
