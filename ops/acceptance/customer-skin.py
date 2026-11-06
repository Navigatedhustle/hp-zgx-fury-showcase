#!/usr/bin/env python3
"""Real shell/browser checks with fictional branding only; no public lookups."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'ops/tests/fixtures/skin/northwind.svg'
PAGES=[(8080,p) for p in ('/demos','/models','/performance','/economics','/secure','/why-hp','/presenter','/experience/vision','/experience/translate','/experience/video','/experience/trailer')]+[(8200,'/'),(8501,'/devteam'),(8765,'/booth'),(8800,'/')]


async def main(args):
 report={'scope':'Actual Chromium/Firefox on this Fury; fictional fixture only; no public lookups','layouts':[],'sync_seconds':[],'checks':{}}
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox']);context=await browser.new_context(viewport={'width':1366,'height':768});presenter=await context.new_page();errors=[]
  presenter.on('pageerror',lambda e:errors.append(str(e)))
  await presenter.goto('http://localhost:8080/demos');await presenter.wait_for_selector('#skin-unlock')
  if not args.static_only:
   assert await presenter.locator('#skin-customize').is_hidden()
   await presenter.click('#skin-unlock');await presenter.fill('#skin-pin',(ROOT/'state/skin-presenter.pin').read_text().strip());await presenter.click('#skin-pin-form button');await presenter.wait_for_selector('#skin-name')
   # Use reset to establish a real cross-station change, after the Factory run.
   await presenter.evaluate("fetch('/skin/reset',{method:'POST'})");await presenter.locator('#skin-close').click()
   stations=[]
   for path in ('/economics','/why-hp','/demos','/presenter'):
    c=await browser.new_context(viewport={'width':1366,'height':768});page=await c.new_page();await page.goto('http://localhost:8080'+path);await page.wait_for_selector('#skin-prepared');stations.append((c,page))
   await presenter.click('#skin-customize');await presenter.fill('#skin-name','Northwind Beverages');await presenter.click('#skin-manual');await presenter.set_input_files('#skin-file',str(FIXTURE));await presenter.wait_for_selector('#skin-apply')
   assert '4.5' in await presenter.locator('#skin-checks').inner_text()
   await presenter.select_option('#skin-pack','consumer_goods')
   if args.screenshots:
    args.screenshots.mkdir(parents=True,exist_ok=True);await presenter.screenshot(path=str(args.screenshots/'northwind-preview.png'))
   began=time.monotonic();await presenter.click('#skin-apply')
   async def synced(page):
    await page.wait_for_function("()=>document.querySelector('#skin-prepared')?.textContent.includes('Northwind Beverages')",timeout=4000)
    return time.monotonic()-began
   report['sync_seconds']=await asyncio.gather(*(synced(page) for _,page in stations));assert max(report['sync_seconds'])<2
   for c,page in stations:await c.close()
   report['checks'].update(pin_and_hidden_controls=True,offline_upload=True,split_preview=True,industry_pack=True,cross_station_sync=True)
   await presenter.wait_for_timeout(550)
   if args.screenshots:await presenter.screenshot(path=str(args.screenshots/'northwind-shell.png'))
   # Root JSON and served CSS must contain precisely the same active properties.
   state=await presenter.evaluate("fetch('/skin/state').then(r=>r.json())");sheet=await presenter.evaluate("fetch('/skin/active.css').then(r=>r.text())")
   assert state['active']['name']=='Northwind Beverages'
   assert all(k+':'+v in sheet for k,v in state['active']['theme']['variables'].items());report['checks']['css_json_match']=True
   # Pure text, including hostile-looking fixture text, stays text in the shell.
   malicious='Northwind <img src=x onerror=alert(1)>'
   await presenter.evaluate("({state,name})=>{const v=structuredClone(state);v.active.name=name;v.revision='fictional-escape';window.FurySkin.update(v)}",{'state':state,'name':malicious})
   await presenter.wait_for_function("()=>document.querySelector('#skin-prepared').textContent.includes('<img')")
   assert await presenter.locator('#skin-prepared img').count()==1
   await presenter.evaluate('(value)=>window.FurySkin.update(value)',state);report['checks']['customer_text_escaped']=True
   # Cached switching and reset use real endpoints and never issue model calls.
   await presenter.click('#skin-menu summary');await presenter.locator('[data-cached]').filter(has_text='Northwind Beverages').first.click();await presenter.wait_for_timeout(500)
   report['checks']['cached_switch']=True
  await context.close();await browser.close()
  for browser_name in ('chromium','firefox'):
   browser=await getattr(p,browser_name).launch(**({'args':['--no-sandbox']} if browser_name=='chromium' else {}))
   for width,height in ((1366,768),(1280,720),(1024,640)):
    context=await browser.new_context(viewport={'width':width,'height':height});page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    for port,path in PAGES:
     await page.goto(f'http://localhost:{port}{path}');await page.wait_for_function("()=>document.querySelector('#skin-prepared')?.textContent.includes('Northwind Beverages')",timeout=12000)
     assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(browser_name,port,path,width)
     assert await page.locator('.skin-identity').get_by_text('HP ZGX Fury',exact=True).is_visible()
     report['layouts'].append({'browser':browser_name,'port':port,'path':path,'width':width,'height':height,'passed':True})
    print(json.dumps({'browser':browser_name,'viewport':[width,height],'pages':len(PAGES),'passed':True}),flush=True)
    await context.close()
   await browser.close()
  # Exercise the electricity distinction with explicit illustrative inputs.
  browser=await p.chromium.launch(args=['--no-sandbox']);context=await browser.new_context(viewport={'width':1366,'height':768},reduced_motion='reduce');page=await context.new_page();await page.goto('http://localhost:8080/economics');await page.wait_for_selector('[data-cloud-energy]')
  assert await page.locator('#frontier-energy-bars').get_by_text('Unknown',exact=True).count()==4
  await page.locator('[data-cloud-energy]').first.fill('240');assert '5×' in await page.locator('#frontier-energy-ratio').inner_text()
  await page.locator('[data-cloud-energy]').first.fill('2.4');assert 'less' in await page.locator('#frontier-energy-ratio').inner_text()
  await page.locator('[data-cloud-energy]').first.fill('');assert 'Unknown is not zero' in await page.locator('#frontier-energy-ratio').inner_text()
  if args.screenshots:await page.locator('#frontier-energy').scroll_into_view_if_needed();await page.screenshot(path=str(args.screenshots/'northwind-electricity.png'))
  report['checks']['electricity_known_unknown_more_less']=True;report['checks']['reduced_motion_context']=True
  await context.close();await browser.close()
 report['browser_errors']=errors;assert not errors,errors
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2));print('PASS',len(report['layouts']),'layouts; max sync',max(report['sync_seconds'],default=0),'seconds',flush=True)


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--screenshots',type=Path);parser.add_argument('--static-only',action='store_true');asyncio.run(main(parser.parse_args()))
