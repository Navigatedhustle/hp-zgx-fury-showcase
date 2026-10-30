"""Local feature acceptance: attract, export, fallback, routes and provenance."""
import asyncio,json,os,time
from pathlib import Path
from playwright.async_api import async_playwright
import httpx
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('vendor/browsers').resolve())
async def run():
 report={};errors=[]
 async with httpx.AsyncClient(timeout=20,trust_env=False) as c:
  base='http://127.0.0.1:8200'
  r=await c.post(base+'/api/query',json={'question':'Give me a thirty second board summary.','persona':'enterprise','fast':True,'llm_narration':False});r.raise_for_status();report['fallback_tool']=r.json()['tool'];assert report['fallback_tool']=='board_summary'
  r=await c.post(base+'/api/query',json={'question':'send me that','persona':'enterprise'});r.raise_for_status();report['voice_export']=r.json();assert report['voice_export']['action']=='export'
  for extension in ['png','pdf']:
   path=report['voice_export']['artifacts'][extension];r=await c.get(base+path);r.raise_for_status();report['export_'+extension+'_bytes']=len(r.content)
  r=await c.get(base+'/api/source/pipeline');r.raise_for_status();report['pipeline_csv_bytes']=len(r.content)
  t=(await c.get(base+'/api/telemetry')).json();report['route_presence']=t['routes'];report['pill_correct']=t['offline']==(len(t['routes'])==0);report['outbound_counter_real']=isinstance(t['non_loopback_tx_bytes'],int) and t['non_loopback_tx_bytes']>=0;report['memory']=t['app_memory_gb']
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required']);page=await b.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
  await page.goto('http://localhost:8200');await page.wait_for_function("() => document.querySelector('#headline').textContent !== '—'")
  # Exercise the same idle logic by aging the clock, without a fabricated UI counter.
  await page.evaluate('() => {lastActivity=Date.now()-61000;attract=true;}')
  await page.wait_for_function("() => attractRunning && (state==='speaking' || state==='thinking')",timeout=10000);report['attract_started']=True
  await page.locator('#voice-toggle').click();report['interrupt_stopped_speech']=await page.evaluate('() => sources.size === 0')
  await page.locator('#golden-button').click();report['staff_questions']=await page.locator('#golden-questions button').count();assert report['staff_questions']==8
  await page.locator('#golden-close').click();await page.locator('#question-input').fill('Which five deals are most at risk this quarter, and why?');await page.locator('#question-form button').click();await page.wait_for_function("() => document.querySelectorAll('#risk-list li').length===5");report['risk_rows']=await page.locator('#risk-list li').count();await page.screenshot(path='eval/screenshots/five-deal-recovery.png')
  await b.close()
 report['console_errors']=errors;Path('eval/acceptance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert not errors and report['pill_correct'] and report['outbound_counter_real']
asyncio.run(run())
