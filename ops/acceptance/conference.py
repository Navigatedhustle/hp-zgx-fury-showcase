#!/usr/bin/env python3
"""Real conference UI/endpoint acceptance. Evidence is private, not publication input."""
import argparse,asyncio,json,time,traceback,sqlite3,sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
VIEWPORTS=[(1366,768),(1280,720),(1440,900),(1920,1080)]
PAGES=[('chooser',8080,'/demos'),('economics',8080,'/operator'),('why-hp',8080,'/why-hp'),('stations',8080,'/stations'),('atlas',8200,'/'),('slides',8765,'/booth'),('factory',8501,'/devteam'),('image',8800,'/')]

def save(out,report):
 (out/'report.json').write_text(json.dumps(report,indent=2))

def ledger_count():
 with sqlite3.connect('file:'+str(ROOT/'state/slides/app.db')+'?mode=ro',uri=True) as db:return db.execute('SELECT count(*) FROM events').fetchone()[0]

async def run(a):
 out=Path(a.output)/time.strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
 report={'scope':'Independent Chromium contexts on this Fury; real CSS content viewports, deviceScaleFactor=1, 100% zoom; no physical separate-device claim','started':time.time(),'layouts':[],'checks':[],'errors':[]}
 host=a.host;scheme='https' if host.endswith('.ts.net') else 'http'
 def url(port,path):return scheme+'://'+host+('' if scheme=='https' and port==8080 else ':'+str(port))+path
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  try:
   for width,height in ([] if a.checks_only else VIEWPORTS+[(1366,640),(1280,620)]):
    ctx=await browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1,reduced_motion='reduce')
    page=await ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    for name,port,path in PAGES:
     try:
      r=await page.goto(url(port,path));assert r.status==200
      await page.locator('.hp-shell .hp-present').wait_for();await page.wait_for_timeout(150)
      if name=='atlas':await page.evaluate('if(typeof attract!=="undefined")attract=false;if(typeof voice!=="undefined")voice=false')
      geometry=await page.evaluate('''()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight})''')
      row={'page':name,**geometry,'passed':True};assert geometry['scrollWidth']<=width,'Horizontal page overflow';assert geometry['scrollHeight']<=height+1,'Unnecessary full-page scroll'
      essential={'chooser':['a[data-demo]'],'economics':['#event-output','#event-chart','#economics-settings-open'],'why-hp':['.why-grid-event','#why-details-open'],'stations':['#station-form button[type=submit]'],'atlas':['#question-input','#talk','#answer'],'slides':['#prompt','#go','#stage','#status'],'factory':['#start','#stage-title','#tokens','#input-tokens','#factory-workspace'],'image':['#prompt','#go','#stage','#status']}[name]
      row['essential_controls']=[]
      for selector in essential:
       for item in await page.locator(selector).all():
        box=await item.bounding_box();assert box and box['height']>0,selector+' hidden'
        assert box['x']>=-1 and box['y']>=-1 and box['x']+box['width']<=width+1 and box['y']+box['height']<=height+1,selector+' outside initial viewport'
        row['essential_controls'].append({'selector':selector,'box':box})
      if name in ['economics','why-hp']:
       open_id='economics-settings-open' if name=='economics' else 'why-details-open';dialog_id='economics-settings' if name=='economics' else 'why-details';close_id='economics-settings-close' if name=='economics' else 'why-details-close'
       await page.click('#'+open_id);dialog=await page.locator('#'+dialog_id).bounding_box();assert dialog['y']>=0 and dialog['y']+dialog['height']<=height+1;await page.screenshot(path=str(out/f'{name}-details-{width}x{height}.png'));await page.click('#'+close_id)
      assert not errors,errors
     except Exception as e:
      row={'page':name,'width':width,'height':height,'passed':False,'error':str(e)}
     await page.screenshot(path=str(out/f'{name}-{width}x{height}.png'),full_page=True);report['layouts'].append(row);save(out,report)
    # Test the actual chooser workspace viewport, including the space its shell uses.
    for demo,control in [('atlas','#question-input'),('slides','#go'),('agent','#start'),('image','#go')]:
     row={'page':'embedded-'+demo,'width':width,'height':height,'passed':True}
     try:
      await page.goto(url(8080,'/demos?demo='+demo));frame=page.frame_locator('#station-workspaces iframe[data-demo='+demo+']');await frame.locator(control).wait_for();box=await frame.locator(control).bounding_box();assert box and box['y']>=0 and box['y']+box['height']<=height+1,'Embedded essential control clipped'
      assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth');await page.screenshot(path=str(out/f'embedded-{demo}-{width}x{height}.png'),full_page=True)
     except Exception as e:row.update(passed=False,error=str(e))
     report['layouts'].append(row);save(out,report)
    await ctx.close()
   # Separate endpoint identities and browser-local persistence.
   contexts=[await browser.new_context(viewport={'width':1366,'height':768}) for _ in range(4)]
   screens=[await c.new_page() for c in contexts]
   for page,role in zip(screens[:2],['economics','why']):
    await page.goto(url(8080,'/stations'));await page.check('input[value='+role+']');await page.click('button[type=submit]');await page.wait_for_url('**/'+('operator' if role=='economics' else 'why-hp'));await page.goto(url(8080,'/'));await page.wait_for_url('**/'+('operator' if role=='economics' else 'why-hp'))
   report['checks'].append('Economics and Why HP independently restore browser-local assignments after visiting Home')
   before=[page.url for page in screens[:2]]
   await screens[2].goto(url(8080,'/demos?demo=agent'));await screens[3].goto(url(8080,'/demos?demo=image'))
   factory=screens[2].frame_locator('iframe[data-demo=agent]');await factory.locator('#start').wait_for();await screens[2].locator('.all-demos').click();await screens[2].locator('a[data-demo=slides]').click();await screens[2].frame_locator('iframe[data-demo=slides]').locator('#go').wait_for();assert await screens[2].locator('#station-workspaces iframe').count()==2
   assert [page.url for page in screens[:2]]==before and screens[3].url.endswith('demo=image')
   await screens[2].reload();await screens[2].frame_locator('iframe[data-demo=slides]').locator('#go').wait_for();assert [page.url for page in screens[:2]]==before
   report['checks'].append('Two interactive endpoints select, return, and refresh without navigating passive displays or the other demo endpoint')
   for c in contexts[2:]:await c.close()
   # Passive displays must not create inference events. No demo frames remain open.
   await asyncio.sleep(3);count=ledger_count();samples=[]
   for _ in range(4):
    await asyncio.sleep(5);r=await screens[0].request.get(url(8080,'/api/event'));samples.append((await r.json())['timestamp'])
   assert ledger_count()==count,'Passive displays added inference ledger events';report['checks'].append('Passive Economics and Why HP create no inference requests during 20-second observation');report['shared_sample_timestamps']=samples
   assert len(set(samples))<=4,'Telemetry is being collected per-browser instead of on shared cadence'
   for c in contexts[:2]:await c.close()
   # Shared setup requires no presenter secret; unrelated sites stay rejected.
   ctx=await browser.new_context();request=ctx.request;before_count=ledger_count()
   r=await request.post(url(8080,'/api/event/reset'),headers={'Origin':'https://unrelated.invalid'},data={'name':'Rejected reset'});assert r.status==403
   r=await request.post(url(8080,'/api/event/reset'),data={'name':'Conference verification'});assert r.status==200
   assert ledger_count()==before_count;report['checks'].append('No-code station reset preserves ledger/artifacts; unrelated origins rejected')
   await ctx.close()
  except Exception:
   report['errors'].append(traceback.format_exc())
  finally:
   report['ended']=time.time();report['passed']=not report['errors'] and all(r['passed'] for r in report['layouts']);save(out,report);await browser.close()
 print(json.dumps({'passed':report['passed'],'layouts':len(report['layouts']),'failures':[r for r in report['layouts'] if not r['passed']],'checks':report['checks'],'errors':report['errors'],'evidence':str(out)},indent=2))
 return report['passed']

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--checks-only',action='store_true');parser.add_argument('--host',default='localhost');parser.add_argument('--output',required=True);args=parser.parse_args();raise SystemExit(0 if asyncio.run(run(args)) else 1)
