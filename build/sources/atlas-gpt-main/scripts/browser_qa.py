"""Local browser validation; records real console/network failures and captures."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('vendor/browsers').resolve())
async def run():
 import httpx
 async with httpx.AsyncClient(timeout=1,trust_env=False) as c:
  for _ in range(120):
   try:
    r=await c.get('http://127.0.0.1:8200/api/health');r.raise_for_status();break
   except httpx.HTTPError:await asyncio.sleep(.25)
 report={'console_errors':[],'failed_requests':[],'screenshots':[],'layout_bounds':[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
  context=await browser.new_context(viewport={'width':1920,'height':1080})
  page=await context.new_page()
  page.on('pageerror',lambda e:report['console_errors'].append(str(e)))
  page.on('console',lambda m:report['console_errors'].append(m.text) if m.type=='error' else None)
  page.on('requestfailed',lambda r:report['failed_requests'].append({'url':r.url,'failure':r.failure}))
  await page.goto('http://localhost:8200');await page.wait_for_function("() => document.querySelector('#headline').textContent!=='—'")
  await page.wait_for_timeout(900)
  async def capture(name):
   if name!='record-vertical':
    bounds=await page.evaluate("() => ({model_top:document.querySelector('.model-strip').getBoundingClientRect().top,answer_bottom:document.querySelector('.answer-foot').getBoundingClientRect().bottom,left_bottom:document.querySelector('.local-note').getBoundingClientRect().bottom,latency_bottom:document.querySelector('.latency-block').getBoundingClientRect().bottom})")
    report['layout_bounds'].append({'screen':name,**bounds})
    assert max(bounds['answer_bottom'],bounds['left_bottom'],bounds['latency_bottom']) < bounds['model_top'],(name,bounds)
   path='eval/screenshots/'+name+'.png';await page.screenshot(path=path);report['screenshots'].append(path)
  await capture('enterprise-idle')
  report['body_dimensions']=await page.evaluate('({width:document.body.scrollWidth,height:document.body.scrollHeight,viewportHeight:innerHeight})')
  await page.locator('#attract-toggle').click();await page.locator('#voice-toggle').click()
  await page.locator('#question-input').fill('Should we build a new sales center in Phoenix, Denver, or Albuquerque?')
  await page.locator('#question-form button').click();await page.wait_for_timeout(70);await capture('enterprise-analyzing')
  await page.wait_for_function("() => document.querySelector('#headline-label').textContent.includes('PREFERRED')");await page.wait_for_timeout(800);await capture('enterprise-site-decision')
  report['decision_caption']=await page.locator('#decision-caption').inner_text()
  await page.locator('#brief-button').click();await page.locator('#brief-preview').wait_for(state='visible');await page.wait_for_timeout(300);await capture('brief-preview')
  report['brief_png']=await page.locator('#brief-png').get_attribute('href');report['brief_pdf']=await page.locator('#brief-pdf').get_attribute('href')
  await page.locator('#brief-close').click()
  await page.locator('#record-open').click();await page.locator('[data-record="wide"]').click();await page.wait_for_timeout(500);await capture('record-landscape')
  await page.keyboard.press('Escape')
  await page.locator('[data-persona="university"]').click();await page.wait_for_function("() => document.querySelector('#headline-label').textContent.includes('FY27')");await page.wait_for_timeout(500);await capture('university-idle')
  await page.locator('#question-input').fill("What's our projected fall enrollment yield?");await page.locator('#question-form button').click();await page.wait_for_timeout(70);await capture('university-analyzing');await page.wait_for_function("() => document.querySelector('#headline-label').textContent.includes('YIELD')");await page.wait_for_timeout(500)
  await page.locator('#record-open').click();await page.locator('[data-record="vertical"]').click();await page.set_viewport_size({'width':1080,'height':1920});await page.wait_for_timeout(700);await capture('record-vertical')
  report['vertical_dimensions']=await page.evaluate('({width:document.body.scrollWidth,height:document.body.scrollHeight,viewportHeight:innerHeight})')
  await browser.close()
 Path('eval/browser-qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
 assert not report['console_errors'] and not report['failed_requests']
asyncio.run(run())
