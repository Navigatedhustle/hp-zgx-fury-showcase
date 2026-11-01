#!/usr/bin/env python3
"""Real local-browser workflows. Evidence is local, never a mock acceptance."""
import re,traceback
import argparse,asyncio,io,json,time,uuid,zipfile,subprocess,base64,sqlite3,itertools,os
from pathlib import Path
from playwright.async_api import async_playwright
from travel_checks import verify_travel
import httpx
ROOT=Path(__file__).resolve().parents[2]
HOST='localhost'
def save_report(out,report):
 target=out/'report.json';temp=out/'report.tmp';temp.write_text(json.dumps(report,indent=2));temp.replace(target)

async def main(a):
 if a.wait_idle:
  deadline=time.time()+900
  async with httpx.AsyncClient(trust_env=False,timeout=5) as client:
   while True:
    response=await client.get('http://127.0.0.1:8501/api/devteam/status');response.raise_for_status();status=response.json()
    if not status['active']:break
    if time.time()>deadline:raise RuntimeError('Factory remained busy for fifteen minutes; no external job was interrupted')
    print('WAITING for existing Factory work to finish; soak clock has not started',flush=True);await asyncio.sleep(10)
 out=(Path(a.output) if a.output else ROOT/'reports/acceptance')/time.strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
 report={'started':time.time(),'host':HOST,'scope':'Independent Chromium contexts on this Fury using local HTTP; no external physical device claim','cycles':[],'samples':[],'rss_page_size_bytes':os.sysconf('SC_PAGE_SIZE')};done=asyncio.Event()
 async def monitor():
  async with httpx.AsyncClient(trust_env=False,timeout=4) as client:
   while not done.is_set():
    row={'at':time.time()}
    disk=os.statvfs(ROOT);row['disk_available_bytes']=disk.f_bavail*disk.f_frsize
    row['memory']={line.split(':')[0]:line.split(':')[1].strip() for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','MemFree:','SwapFree:'))}
    try:
     registry=json.loads((ROOT/'state/supervisor.json').read_text());rss={}
     for name,spec in registry.items():
      total=0
      for member in spec.get('members',[]):
       try:total+=int((Path('/proc')/str(member['pid'])/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
       except (OSError,IndexError):pass
      rss[name]=total
     row['process_rss']=rss
    except (OSError,ValueError):pass
    for name,port,path in [('gateway',8001,'/health'),('image',8800,'/health'),('agent',8501,'/api/devteam/status')]:
     try:
      d=(await client.get(f'http://127.0.0.1:{port}{path}')).json()
      row[name]={k:d.get(k) for k in (['active','queued','backends'] if name=='gateway' else ['ready','active','queued'] if name=='image' else ['active','queued','jobs','limit'])}
     except Exception as e:row[name]={'error':str(e)}
    r=await asyncio.create_subprocess_exec('nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits',stdout=asyncio.subprocess.PIPE);row['gpu']=(await r.communicate())[0].decode().strip()
    report['samples'].append(row)
    save_report(out,report)
    await asyncio.sleep(1)
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  monitor_task=asyncio.create_task(monitor())
  try:
   cycle=0
   while cycle<a.cycles or time.time()-report['started']<a.seconds:
    cycle+=1;product=('travel','short-editorial','short')[(cycle-1)%3] if a.agent_product=='mixed' else a.agent_product;rows={};contexts=[];cycle_start=time.time();agent_started=asyncio.Event();agent_done=asyncio.Event();iterations={};prepared=asyncio.Barrier(3)
    async def workflow(name,port,path):
     iterations[name]=iterations.get(name,0)+1;iteration=iterations[name]
     row={'started':time.time(),'errors':[],'failed_requests':[],'workflow':name,'iteration':iteration};rows[name+'-'+str(iteration)]=row
     ctx=await browser.new_context(viewport={'width':1440,'height':1000});contexts.append(ctx);page=await ctx.new_page()
     def browser_error(error):
      row['errors'].append(str(error));row.setdefault('browser_error_stacks',[]).append(error.stack)
     page.on('pageerror',browser_error);page.on('requestfailed',lambda r:row['failed_requests'].append({'url':r.url,'error':r.failure}))
     try:
      if not a.individual and a.only=='all' and name!='agent':await asyncio.wait_for(agent_started.wait(),60)
      response=await page.goto(f'http://{HOST}:{port}{path}');assert response.status==200
      if name=='agent':
       await page.locator('#start').wait_for();await page.wait_for_function("() => !document.getElementById('start').disabled",timeout=30000)
       await page.select_option('#demo-mode','live');await page.select_option('#product',product);await page.locator('#advanced-controls').evaluate('(el)=>el.open=true');await page.check('#automatic')
       row['submitted']=time.time()
       async with page.expect_response(lambda r:'/api/devteam/runs' in r.url and r.request.method=='POST') as created:await page.click('#start')
       created=await created.value
       assert created.status==201,'Factory start was explicitly rejected: HTTP '+str(created.status)+' '+await created.text()
       await page.wait_for_function("() => document.getElementById('run-state').textContent==='running'",timeout=30000)
       await page.wait_for_function("() => document.querySelector('.actor.generating')!==null",timeout=60000);agent_started.set()
       await page.wait_for_function("() => ['finished','failed','stopped','blocked'].includes(document.getElementById('run-state').textContent)",timeout=1800000)
       d=await page.evaluate("fetch('/api/devteam/run').then(r=>r.json())");assert d.get('mode','live')=='live','Recorded playback cannot qualify as live inference';row['run']=d
       assert d['state']=='finished',d.get('error');assert d['tests']['passed'];assert any(c['model']=='fury-lead' and c['status']=='complete' for c in d['calls'])
       if product=='travel':
        import importlib.util,types
        spec=importlib.util.spec_from_file_location('portal',Path(__file__).with_name('travel-portal.py'));portal=importlib.util.module_from_spec(spec);spec.loader.exec_module(portal)
        owner=out/'factory-owner.json';await ctx.storage_state(path=str(owner));assert await portal.main(types.SimpleNamespace(run=d['id'],output=str(out/'portal'),origin='http://localhost:8501',storage_state=str(owner)))
       else:await verify_travel(page,row,cycle)
      elif name=='atlas':
       await page.wait_for_function('() => typeof config!=="undefined"&&!!config',timeout=30000)
       await page.evaluate('attract=false;voice=false');await page.fill('#question-input',f'What happens to Q4 profit if our Commit stage win rate drops by {3+(cycle+iteration)%18} percentage points?')
       if iteration==1 and not a.individual and a.only=='all':await asyncio.wait_for(prepared.wait(),30)
       row['submitted']=time.time();await page.locator('#question-form button').click()
       await page.wait_for_function('() => last && last.grounding && state!=="thinking"',timeout=180000)
       row['result']=await page.evaluate('last');assert row['result']['question']==f'What happens to Q4 profit if our Commit stage win rate drops by {3+(cycle+iteration)%18} percentage points?','Atlas answered a superseded question';assert row['result']['grounding']['passed'];assert row['result']['routing']['engine']=='local language model','Atlas used fallback instead of actual inference';assert row['result'].get('answer') or row['result'].get('speech') or len(str(row['result']))>500
       await page.click('#sources-toggle')
      else:
       await page.fill('#prompt',('Explain reliable local AI workflows, evidence, human review, and next steps.' if name=='slides' else 'A detailed botanical illustration of a red fox in an autumn garden, natural light, no text')+f' Run {cycle}.')
       if iteration==1 and not a.individual and a.only=='all':await asyncio.wait_for(prepared.wait(),30)
       row['submitted']=time.time();await page.click('#go')
       await page.wait_for_function("() => ['complete','failed'].includes(document.getElementById('status').dataset.state)",timeout=300000)
       row['status']=await page.locator('#status').inner_text();assert await page.locator('#status').get_attribute('data-state')=='complete',row['status']
       if name=='image':
        await page.wait_for_function('() => document.querySelector("#stage img")?.naturalWidth>0',timeout=15000)
        url=await page.locator('#stage img').get_attribute('src');data=await page.evaluate('async u=>{const r=await fetch(u);if(!r.ok)throw Error(r.status);const b=new Uint8Array(await r.arrayBuffer());let s="";for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));return btoa(s)}',url);raw=base64.b64decode(data);assert raw.startswith(b'\x89PNG');(out/f'cycle-{cycle}-{iteration}.png').write_bytes(raw);row['image_bytes']=len(raw);row['job']=await page.evaluate("()=>{const j=JSON.parse(sessionStorage.getItem('fury-image-job'));return fetch('/api/jobs/'+j.id).then(r=>r.json())}")
       else:
        await page.frame_locator('#stage iframe').locator('body').wait_for();assert len(await page.frame_locator('#stage iframe').locator('body').inner_text())>80
        link=page.get_by_text('Download editable PPTX');href=await link.get_attribute('href');data=await page.evaluate('async u=>{const r=await fetch(u);if(!r.ok)throw Error(r.status);const b=new Uint8Array(await r.arrayBuffer());let s="";for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));return btoa(s)}',href);raw=base64.b64decode(data)
        z=zipfile.ZipFile(io.BytesIO(raw));assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==3;(out/f'cycle-{cycle}-{iteration}.pptx').write_bytes(raw);row['pptx_bytes']=len(raw)
      await page.screenshot(path=str(out/f'{cycle}-{name}-{iteration}.png'),full_page=True);assert not row['errors'],row['errors'];row['budget_seconds']={'atlas':15,'slides':45,'image':15,'agent':1800 if product=='travel' else 600}[name];assert time.time()-row.get('submitted',row['started'])<=row['budget_seconds'],'Measured latency exceeded the predeclared demo budget';row['passed']=True
     except Exception as e:
      row['passed']=False;row['error']=str(e) or repr(e);row['failure_traceback']=traceback.format_exc();await page.screenshot(path=str(out/f'{cycle}-{name}-{iteration}-failure.png'),full_page=True)
     finally:
      if name=='agent':agent_done.set()
      row['ended']=time.time();row['seconds']=row['ended']-row['started'];row['latency_seconds']=row['ended']-row['submitted'] if 'submitted' in row else None;row['setup_seconds']=row.get('submitted',row['started'])-row['started'];await ctx.close();print(json.dumps({'cycle':cycle,'workflow':name,**{k:v for k,v in row.items() if k in ('passed','error','seconds','latency_seconds','status','controls')}}),flush=True)
    jobs={'atlas':(8200,'/'),'slides':(8765,'/booth'),'agent':(8501,'/devteam'),'image':(8800,'/')}
    selected=jobs if a.only=='all' else {a.only:jobs[a.only]}
    if a.individual:
     for name,(port,path) in selected.items():await workflow(name,port,path)
    else:
     async def sustained(name,port,path):
      while True:
       await workflow(name,port,path)
       if name=='agent' or not a.sustain or agent_done.is_set() or not rows[name+'-'+str(iterations[name])]['passed']:return
       await asyncio.sleep(8)
     await asyncio.gather(*(sustained(name,port,path) for name,(port,path) in selected.items()))
    intervals=[];overlap=[]
    with sqlite3.connect(ROOT/'state/slides/app.db') as db:
     try:intervals=[dict(zip(['id','demo','model','started','ended','status'],r)) for r in db.execute('SELECT * FROM execution_intervals WHERE started>=?',(cycle_start,))]
     except sqlite3.OperationalError:pass
    groups=[[r for r in intervals if r['demo']==demo and r['ended'] and r['status'] in ('complete','finished')] for demo in ('atlas','slides','agent','image')]
    if all(groups):
     for combo in itertools.product(*groups):
      begin=max(r['started'] for r in combo);end=min(r['ended'] for r in combo)
      if end>begin:overlap.append({'start':begin,'end':end,'seconds':end-begin,'ids':[r['id'] for r in combo]})
    if not a.individual and a.only=='all' and not overlap:rows['overlap']={'passed':False,'error':'No measured four-component backend execution overlap'}
    report['cycles'].append({'number':cycle,'results':rows,'execution_intervals':intervals,'four_way_overlap':overlap});save_report(out,report)
    for ctx in contexts:await ctx.close()
    if not all(r.get('passed') for r in rows.values()):break
   report['ended']=time.time();report['duration']=report['ended']-report['started']
  finally:
   done.set();await monitor_task;await browser.close();save_report(out,report);print('EVIDENCE '+str(out),flush=True)
 return all(r['passed'] for c in report['cycles'] for r in c['results'].values())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--agent-product',choices=['short','short-editorial','travel','mixed'],default='short');p.add_argument('--cycles',type=int,default=1);p.add_argument('--seconds',type=int,default=0);p.add_argument('--only',choices=['all','atlas','slides','agent','image'],default='all');p.add_argument('--individual',action='store_true');p.add_argument('--output');p.add_argument('--wait-idle',action='store_true');p.add_argument('--sustain',action='store_true');a=p.parse_args();raise SystemExit(0 if asyncio.run(main(a)) else 1)
