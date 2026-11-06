#!/usr/bin/env python3
"""Actual browsers, injected appearance faults, fictional identity only.

Does not submit Factory jobs or cancel existing work. Run without other skin
acceptance processes: applying/resetting a skin changes shared server state.
"""
import argparse
import asyncio
import json
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[2]
HOST='http://localhost:8080'


async def live_state_faults():
 """Exercise the real collector with damaged fictional/default state only."""
 path=ROOT/'state/skin/active.json';original=path.read_bytes() if path.exists() else None
 if original and json.loads(original).get('name')!='Northwind Beverages':
  raise RuntimeError('Use default appearance or the fictional fixture before live state checks')
 async with httpx.AsyncClient(trust_env=False) as client:
  try:
   before=(await client.get(HOST+'/api/live')).json()['timestamp']
   for broken in ('[]','not json','{"name":"Northwind Beverages"}'):
    temporary=path.with_suffix('.acceptance.tmp');temporary.write_text(broken);temporary.replace(path)
    response=await client.get(HOST+'/skin/state');assert response.status_code==200
    assert response.json()['active'] is None
    assert (await client.get(HOST+'/skin/active.css')).text==':root{}'
   await asyncio.sleep(3)
   live=(await client.get(HOST+'/api/live')).json()
   assert live['timestamp']>before
   assert live['skin']['active'] is None
   assert live['telemetry']['external_api_calls']==0
   assert (await client.get(HOST+'/api/event')).json()['timestamp']>before
   return {'damaged_json_defaulted':True,'collector_and_sse_source_advance':True,'external_ai_api_calls':0}
  finally:
   if original is None:path.unlink(missing_ok=True)
   else:path.write_bytes(original)


async def launcher(page):
 await page.click('.all-demos')
 assert await page.locator('.mc-launch-card[data-demo]').count()==8
 await page.click('[data-demo="agent"]')
 await page.frame_locator('iframe[data-demo="agent"]').locator('#start').wait_for()
 await page.click('.all-demos')
 await page.click('[data-demo="vision"]')
 await page.frame_locator('iframe[data-demo="vision"]').locator('#vision-task').wait_for()
 await page.click('.all-demos')


async def main(output):
 report={'scope':'Actual local Chromium and Firefox; injected skin faults; no Factory submission, public lookup or customer identity','checks':[]}
 async with async_playwright() as p:
  for engine in ('chromium','firefox'):
   browser=await getattr(p,engine).launch(**({'args':['--no-sandbox']} if engine=='chromium' else {}))
   for fault in ('missing_script','missing_styles','initialization_error','service_503','invalid_state','unknown_counter','timeout','late_poll','late_start','safe_mode'):
    context=await browser.new_context(viewport={'width':1366,'height':768});page=await context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    if fault=='missing_script':await context.route('**/showcase-assets/skin.js',lambda route:route.abort())
    if fault=='missing_styles':await context.route('**/showcase-assets/skin.css',lambda route:route.abort())
    if fault=='initialization_error':
     async def broken_script(route):
      response=await route.fetch();body=await response.text()
      await route.fulfill(response=response,body=body.replace(" const hero=document.querySelector", " throw Error('Injected optional initialization fault');\n const hero=document.querySelector"))
     await context.route('**/showcase-assets/skin.js',broken_script)
    if fault=='service_503':await context.route('**/skin/**',lambda route:route.fulfill(status=503,json={'detail':'Customization unavailable'}))
    if fault=='invalid_state':await context.route('**/skin/state',lambda route:route.fulfill(json={'active':{'name':'Northwind Beverages','theme':{'variables':{'--mc-top':'#ffffff'}}},'revision':'broken'}))
    if fault=='unknown_counter':
     await context.route('**/skin/state',lambda route:route.fulfill(json={'active':None,'public_web_lookups':None,'revision':'unknown-counter'}))
     await context.route('**/showcase-telemetry',lambda route:route.abort())
    if fault=='timeout':
     await context.add_init_script("""const original=window.fetch;window.fetch=(url,options={})=>String(url).startsWith('/skin/')?new Promise((resolve,reject)=>{options.signal?.addEventListener('abort',()=>reject(new DOMException('Timed out','AbortError')),{once:true})}):original(url,options)""")
    pending=asyncio.Event();release=asyncio.Event()
    base={'id':'fictional','name':'Northwind Beverages','status':'researching','steps':[],'routing':{'model':'Qwen','reason':'Fictional response'},'elapsed':0}
    if fault in ('late_poll','late_start'):
     async def lookup(route):
      path=route.request.url.split('/skin/')[-1]
      if path.endswith('/cancel'):await route.fulfill(json={'cancelled':True});return
      if path=='research' and fault=='late_poll':await route.fulfill(json=base);return
      pending.set();await release.wait()
      await route.fulfill(json={**base,**({'status':'manual','message':'Fictional delayed response'} if fault=='late_poll' else {})})
     await context.route('**/skin/research**',lookup)
    requests=[]
    if fault=='safe_mode':page.on('request',lambda request:requests.append(request.url))
    await page.goto(HOST+'/demos'+('?skin=off' if fault=='safe_mode' else ''))
    await page.locator('#mc-default-appearance').wait_for()
    if fault=='unknown_counter':
     await page.locator('#skin-reset').wait_for(state='attached')
     await page.click('#skin-customize');assert await page.locator('#skin-web-count').inner_text()=='unknown'
     await page.click('#skin-close')
    if fault in ('late_poll','late_start','timeout'):
     await page.click('#skin-customize');await page.fill('#skin-name','Northwind Beverages')
     await page.locator('#skin-who button').first.click()
     if fault=='timeout':
      await page.locator('.skin-error').wait_for(timeout=10000)
      await page.click('#skin-close')
     else:
      await asyncio.wait_for(pending.wait(),5)
      if fault=='late_poll':await page.click('#skin-cancel')
      await page.click('#skin-close');release.set();await page.wait_for_timeout(350)
     assert not await page.locator('.skin-dialog').evaluate('(node)=>node.open')
    await launcher(page)
    if fault in ('missing_script','missing_styles','initialization_error'):
     assert await page.locator('.skin-top-row').count()==0
     assert not await page.evaluate("document.documentElement.classList.contains('skin-controls-ready')")
     assert await page.locator('.mc-telemetry #mc-gpu').count()==1
    if fault=='safe_mode':
     assert all('/skin/' not in u and '/skin.js' not in u and '/skin.css' not in u for u in requests)
     assert 'skin=off' in page.url
     assert await page.frame_locator('iframe[data-demo="vision"]').locator('html').evaluate("()=>new URLSearchParams(location.search).get('skin')==='off'")
     await page.click('a[href*="/economics"]');assert 'skin=off' in page.url
     await page.locator('#frontier-bars').wait_for()
    else:
     await page.click('#mc-default-appearance');assert 'skin=off' in page.url
     assert await page.locator('.mc-launch-card[data-demo]').count()==8
    assert not errors,(engine,fault,errors)
    report['checks'].append({'browser':engine,'fault':fault,'launcher_and_workspaces_passed':True})
    print(engine,fault,'PASS',flush=True);await context.close()
   await browser.close()
 report['live_backend']=await live_state_faults()
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
 asyncio.run(main(parser.parse_args().output))
