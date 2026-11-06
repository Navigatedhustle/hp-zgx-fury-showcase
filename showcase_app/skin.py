"""Presenter-only customer wrapper. All identity-bearing files stay in state/skin/."""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response, FileResponse
from showcase_app import skin_research as research
from showcase_app.skin_theme import palette, css, contrast

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'state/skin'
PIN=ROOT/'state/skin-presenter.pin'
router=APIRouter(prefix='/skin')
JOBS={}
TOKENS={}
COUNTER_LOCK=threading.Lock()
INDUSTRIES={
 'Q31207':'healthcare','Q16917':'healthcare','Q8434':'higher_education','Q189533':'higher_education',
 'Q1047113':'research_lab','Q11862829':'research_lab','Q187939':'manufacturing','Q190117':'automotive',
 'Q19776773':'consumer_goods','Q11204':'public_sector','Q837171':'financial_services','Q507443':'financial_services',
 'Q2151621':'energy','Q11661':'technology','Q7397':'technology','Q1665594':'technology'}


def settings():return json.loads((ROOT/'config/skin.json').read_text())


def write_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=True));temporary.chmod(0o600);temporary.replace(path)


def read_json(path,default=None):
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return default


def presenter_pin():
 PIN.parent.mkdir(parents=True,exist_ok=True)
 if not PIN.exists():
  try:fd=os.open(PIN,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  except FileExistsError:pass
  else:
   with os.fdopen(fd,'w') as f:f.write(f'{secrets.randbelow(1000000):06d}')
 return PIN.read_text().strip()


def public_count():return read_json(STATE/'web-counter.json',{}).get('requests',0)


def count_request():
 with COUNTER_LOCK:write_json(STATE/'web-counter.json',{'requests':public_count()+1})


def active():
 value=read_json(STATE/'active.json')
 if value and time.time()-value.get('touched',0)>settings()['idle_hours']*3600:
  reset();return None
 return value


def reset():
 (STATE/'active.json').unlink(missing_ok=True)


def snapshot():
 value=active()
 return {'active':value,'public_web_lookups':public_count(),'revision':hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:16]}


def recent():
 rows=[read_json(p) for p in (STATE/'cache').glob('*/skin.json')]
 return sorted((v for v in rows if v),key=lambda v:v.get('used',v.get('retrieved',0)),reverse=True)[:8]


def packs():
 return {p.stem:json.loads(p.read_text()) for p in (ROOT/'config/skin_packs').glob('*.json')}


def pack_for(industries):return next((INDUSTRIES[q] for q in industries if q in INDUSTRIES),'default')


def cache_candidate(name,candidate,asset,industry='default',sources=None):
 slug=hashlib.sha256((name+'\0'+hashlib.sha256(asset['data']).hexdigest()).encode()).hexdigest()[:24]
 directory=STATE/'cache'/slug;directory.mkdir(parents=True,exist_ok=True,mode=0o700)
 logo=directory/('logo.'+asset['ext']);logo.write_bytes(asset['data']);logo.chmod(0o600)
 png=directory/'palette.png';png.write_bytes(asset['png']);png.chmod(0o600)
 value={'id':slug,'name':name,'logo':'/skin/logo/'+slug+'/'+logo.name,'theme':asset['theme'],'colors':asset['colors'],
        'plate':asset['plate'],'source':candidate['source'],'sources':sources or [candidate.get('url','')],
        'retrieved':time.time(),'pack':industry}
 write_json(directory/'skin.json',value);return value


def apply_skin(slug,theme=None,pack=None):
 if not re.fullmatch(r'[a-f0-9]{24}',slug):raise ValueError('Unknown cached skin')
 value=read_json(STATE/'cache'/slug/'skin.json')
 if not value:raise ValueError('Unknown cached skin')
 if theme:value['theme']=theme
 if pack is not None:
  if pack not in packs():raise ValueError('Unknown sample pack')
  value['pack']=pack
 value['touched']=value['used']=time.time()
 dark=value['theme']['variables'].get('--mc-panel','#101c2e')
 value['plate']=any(contrast(c,dark)<3 for c,w in value['colors'] if w>0) if value['colors'] else value['plate']
 write_json(STATE/'cache'/slug/'skin.json',value);write_json(STATE/'active.json',value)
 return snapshot()


def job_public(job):return {k:v for k,v in job.items() if not k.startswith('_')}


def step(job,label):
 job['steps'].append({'label':label,'elapsed':round(time.monotonic()-job['_started'],3)})
 job['elapsed']=round(time.monotonic()-job['_started'],3)


def route(job,value):
 model=value.get('model','')
 if model:job['routing']={'model':model,'reason':value.get('reason','')}


async def rank(job,entities,logos):
 try:
  chosen=await research.model_choose(entities,logos,lambda r:route(job,r))
  return chosen
 except (Exception,):
  # No invented model claim on a failed local call. The presenter still chooses.
  job['routing']['note']='Local ranking unavailable; source-order candidates require presenter confirmation.'
  return {'entities':list(range(min(4,len(entities)))),'logos':list(range(min(6,len(logos))))}


async def collect_candidates(job,entity=None,initial=None):
 fetcher=job['_fetcher'];step(job,'Collecting logo candidates')
 logos=list(entity.get('logos',[]) if entity else []);hint=None
 website=initial or (entity.get('website') if entity else None)
 if website:
  step(job,'Found official site')
  try:
   site,hint=await research.site_logo_candidates(website,fetcher);logos+=site
  except research.LookupError:pass
 # Explicit site starts first. Otherwise Wikidata always has source priority.
 if initial:logos.sort(key=lambda c:c['priority'] if c['source']!='Wikidata' else 5)
 choice=await rank(job,[],logos)
 ordered=[logos[i] for i in dict.fromkeys(choice['logos'])]
 if not ordered:ordered=logos[:6]
 result=[];step(job,'Extracting colors')
 for candidate in ordered:
  if fetcher.cancelled:return
  try:
   if candidate.get('inline'):raw=candidate['inline'].encode();kind='image/svg+xml'
   else:raw,kind,_=await fetcher.get(candidate['url'])
   asset=await asyncio.to_thread(research.logo_asset,raw,kind,hint)
   if fetcher.cancelled:return
   result.append(cache_candidate(job['name'],candidate,asset,pack_for((entity or {}).get('industries',[]))))
  except research.LookupError:continue
  if len(result)==6:break
 job['candidates']=result;job['status']='candidates' if result else 'manual'
 if not result:job['message']='No suitable public logo found. Upload a PNG or SVG to continue.'
 step(job,'Candidates ready' if result else 'Manual logo upload ready')


async def run_lookup(job):
 try:
  if job.get('website'):
   await collect_candidates(job,initial=job['website']);return
  step(job,'Searching Wikidata')
  entities=await research.wikidata_search(job['name'],job['_fetcher'])
  if not entities:job.update(status='manual',message='No matching entity. Upload a PNG or SVG to continue.');return
  choice=await rank(job,entities,[])
  selected=[entities[i] for i in dict.fromkeys(choice['entities'])] or entities[:4]
  # Descriptions/domains remain presenter-confirmed, even after model ranking.
  detailed=[]
  for entity in selected[:4]:
   if job['_fetcher'].cancelled:return
   try:detailed.append(await research.wikidata_entity(entity['qid'],job['_fetcher']))
   except research.LookupError:continue
  if len(detailed)>1:
   job.update(status='entities',entities=detailed);step(job,'Confirm the official entity');return
  if detailed:await collect_candidates(job,detailed[0])
  else:job.update(status='manual',message='Public identity details unavailable. Upload a PNG or SVG to continue.')
 except asyncio.CancelledError:
  job['status']='cancelled';job['_fetcher'].cancelled=True;raise
 except research.LookupError as exc:job.update(status='manual',message=str(exc))
 except Exception:job.update(status='manual',message='Research unavailable. Upload a PNG or SVG to continue.')
 finally:job['elapsed']=round(time.monotonic()-job['_started'],3)


def new_lookup(name,website=None):
 if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('Use a customer name between 1 and 80 characters')
 if website:
  website=website.strip()
  if '://' not in website:website='https://'+website
  research.validate_url(website)
 if any(j['status']=='researching' for j in JOBS.values()):raise ValueError('A lookup is already running; cancel it first')
 # Keep at most eight in-memory lookup sessions. Only cached state persists.
 while len(JOBS)>=8:
  old=next(k for k,v in JOBS.items() if v['status']!='researching');JOBS.pop(old)
 jid=secrets.token_hex(12)
 job={'id':jid,'name':name.strip(),'website':website,'status':'researching','steps':[],'elapsed':0,'candidates':[],
      'routing':{'model':'Selecting local lead lane','reason':'DeepSeek if free, otherwise Qwen'},'_started':time.monotonic(),'_fetcher':research.PublicFetcher(count_request)}
 JOBS[jid]=job;job['_task']=asyncio.create_task(run_lookup(job));return job


def authorized(request):
 token=request.cookies.get('fury_skin','');expiry=TOKENS.get(token,0)
 return expiry>time.time()


def require(request):
 origin=request.headers.get('origin')
 if origin and urlsplit(origin).hostname!=request.url.hostname:raise HTTPException(403,'Use the local presenter station')
 if not authorized(request):raise HTTPException(403,'Assign this station as Presenter or enter the presenter PIN')


async def body(request):
 # Read incrementally: no unbounded multipart/JSON buffering.
 data=bytearray()
 async for chunk in request.stream():
  data.extend(chunk)
  if len(data)>2*1024*1024:raise HTTPException(413,'Maximum upload is two megabytes')
 return bytes(data)


async def json_body(request):
 try:
  value=json.loads(await body(request))
  if not isinstance(value,dict):raise ValueError()
  return value
 except (ValueError,UnicodeError):raise HTTPException(422,'Expected a JSON object') from None


async def changed():
 # Publish immediately over the SAME cached SSE fanout; no second collector.
 from showcase_app.operator import monitor
 async with monitor.lock:
  data=json.loads(monitor.stream) if monitor.stream else {'telemetry':None,'event':None}
  data['skin']=snapshot();monitor.stream=json.dumps(data,separators=(',',':'))
 async with monitor.changed:monitor.changed.notify_all()


@router.get('/state')
async def state(request:Request):
 value=snapshot();value['presenter']=authorized(request)
 if value['presenter']:value.update(recent=recent(),packs=packs())
 return JSONResponse(value,headers={'Cache-Control':'no-store'})


@router.post('/unlock')
async def unlock(request:Request):
 origin=request.headers.get('origin')
 if origin and urlsplit(origin).hostname!=request.url.hostname:raise HTTPException(403,'Use the local presenter station')
 data=await json_body(request)
 # Station assignment is an explicit local presenter action, like /stations.
 # PIN is required when the browser has another station assignment.
 if data.get('role')!='presenter' and not hmac.compare_digest(str(data.get('pin','')),presenter_pin()):raise HTTPException(403,'Presenter PIN did not match')
 now=time.time()
 for key,expiry in list(TOKENS.items()):
  if expiry<now:TOKENS.pop(key,None)
 if len(TOKENS)>64:raise HTTPException(429,'Presenter sessions full')
 token=secrets.token_urlsafe(32);TOKENS[token]=now+8*3600
 response=JSONResponse({'presenter':True});response.set_cookie('fury_skin',token,httponly=True,samesite='strict',max_age=8*3600,secure=request.url.scheme=='https');return response


@router.post('/research')
async def start(request:Request):
 require(request);data=await json_body(request)
 try:job=new_lookup(data.get('name'),data.get('website'));return job_public(job)
 except ValueError as exc:raise HTTPException(422,str(exc)) from None


@router.get('/research/{jid}')
async def lookup_status(jid:str,request:Request):
 require(request)
 if jid not in JOBS:raise HTTPException(404)
 job=JOBS[jid];value=job_public(job);value['public_web_lookups']=public_count()
 if job['status']=='researching':value['elapsed']=round(time.monotonic()-job['_started'],3)
 return JSONResponse(value,headers={'Cache-Control':'no-store'})


@router.post('/research/{jid}/cancel')
async def cancel(jid:str,request:Request):
 require(request)
 if jid not in JOBS:raise HTTPException(404)
 job=JOBS[jid];job['_fetcher'].cancelled=True;job['_task'].cancel();job['status']='cancelled';return {'cancelled':True}


@router.post('/research/{jid}/entity')
async def entity_choice(jid:str,request:Request):
 require(request);data=await json_body(request);job=JOBS.get(jid)
 if not job or job['status']!='entities':raise HTTPException(409,'Choose an entity from the current lookup')
 entity=next((e for e in job['entities'] if e['qid']==data.get('qid')),None)
 if entity is None:raise HTTPException(422,'Unknown entity choice')
 job['status']='researching';job['_task']=asyncio.create_task(collect_candidates(job,entity));return job_public(job)


@router.post('/upload')
async def upload(request:Request):
 require(request);name=request.headers.get('x-skin-name','')
 # Names are UTF-8 encoded via JSON-safe URI quoting by the UI, never URL paths.
 from urllib.parse import unquote
 name=unquote(name)
 if not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise HTTPException(422,'Use a customer name between 1 and 80 characters')
 kind=request.headers.get('content-type','').split(';')[0]
 if kind not in ('image/png','image/svg+xml'):raise HTTPException(422,'Upload a PNG or SVG logo')
 try:asset=await asyncio.to_thread(research.logo_asset,await body(request),kind)
 except research.LookupError as exc:raise HTTPException(422,str(exc)) from None
 return cache_candidate(name.strip(),{'source':'manual upload'},asset)


@router.post('/preview')
async def preview(request:Request):
 require(request);data=await json_body(request);slug=data.get('id','')
 if not re.fullmatch(r'[a-f0-9]{24}',slug):raise HTTPException(404)
 value=read_json(STATE/'cache'/slug/'skin.json')
 if not value:raise HTTPException(404)
 colors={k:data.get(k) for k in ('primary','accent')}
 if any(v is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in colors.values()):raise HTTPException(422,'Use a six digit hex color')
 value['theme']=palette(value['colors'],**colors)
 return value


@router.post('/apply')
async def apply(request:Request):
 require(request);data=await json_body(request)
 # Recompute all tokens server-side; callers cannot inject CSS or semantic colors.
 slug=data.get('id','')
 if not re.fullmatch(r'[a-f0-9]{24}',slug):raise HTTPException(404)
 cached=read_json(STATE/'cache'/slug/'skin.json')
 if not cached:raise HTTPException(404)
 colors={k:data.get(k) for k in ('primary','accent')}
 if any(v is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in colors.values()):raise HTTPException(422,'Use a six digit hex color')
 theme=palette(cached['colors'],**colors) if any(colors.values()) else cached['theme']
 try:value=apply_skin(slug,theme,data.get('pack'))
 except ValueError as exc:raise HTTPException(422,str(exc)) from None
 await changed();return value


@router.post('/reset')
async def reset_route(request:Request):
 require(request);reset();await changed();return snapshot()


@router.post('/touch')
async def touch(request:Request):
 # Real browser interaction extends retention; polling and SSE never do.
 value=active()
 if value and time.time()-value.get('touched',0)>60:value['touched']=time.time();write_json(STATE/'active.json',value)
 return {'active':bool(value)}


@router.get('/active.css')
async def active_css():
 value=active();return Response(css(value['theme']) if value else ':root{}',media_type='text/css',headers={'Cache-Control':'no-store'})


@router.get('/logo/{slug}/{filename}')
async def logo(slug:str,filename:str):
 if not re.fullmatch(r'[a-f0-9]{24}',slug) or filename not in ('logo.svg','logo.png','palette.png'):raise HTTPException(404)
 path=STATE/'cache'/slug/filename
 if not path.is_file():raise HTTPException(404)
 return FileResponse(path,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'none'; sandbox"})


async def shutdown():
 for job in JOBS.values():
  if not job['_task'].done():job['_fetcher'].cancelled=True;job['_task'].cancel()
 await asyncio.gather(*(j['_task'] for j in JOBS.values()),return_exceptions=True)
