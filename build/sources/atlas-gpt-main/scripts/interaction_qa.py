"""Exercise blocked autoplay, explicit audio activation and unsupported input."""
import asyncio,json,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def run():
 report={'console_errors':[],'nonlocal_page_requests':[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=document-user-activation-required'])
  page=await browser.new_page(viewport={'width':1920,'height':1080})
  page.on('pageerror',lambda e:report['console_errors'].append(str(e)))
  page.on('request',lambda r:report['nonlocal_page_requests'].append(r.url) if urlparse(r.url).hostname not in ['localhost','127.0.0.1',None] else None)
  session=await page.context.new_cdp_session(page)
  await page.goto('http://localhost:8200')
  # Playwright evaluations mark a user gesture; poll through CDP without one.
  for _ in range(100):
   ready=await session.send('Runtime.evaluate',{'expression':"last?.tool==='forecast_quarter'",'returnByValue':True,'userGesture':False})
   if ready['result'].get('value'):break
   await asyncio.sleep(.1)
  activation=await session.send('Runtime.evaluate',{'expression':'navigator.userActivation.hasBeenActive','returnByValue':True,'userGesture':False})
  report['prior_user_activation']=activation['result']['value']
  await session.send('Runtime.evaluate',{'expression':'ask("What\'s our projected Q4 revenue and profit?")','awaitPromise':True,'userGesture':False})
  report['blocked_autoplay_graceful']=await page.evaluate("() => state==='idle' && audioContext.state==='suspended' && sources.size===0")
  report['autoplay_prompt']=await page.locator('#toast').inner_text()
  await page.locator('#replay').click();await page.wait_for_function('() => sources.size>0')
  report['gesture_enables_audio']=True
  await page.locator('#voice-toggle').click();await page.wait_for_timeout(500)
  report['voice_off_cancels_all_sentences']=await page.evaluate('() => sources.size===0')
  await page.locator('#question-input').fill('What is the weather tomorrow?');await page.locator('#question-form button').click()
  await page.wait_for_function("() => document.querySelector('#headline').textContent==='—' && state==='idle'")
  report['unsupported_clears_stale_answer']=await page.evaluate("() => last===null && !chart && document.querySelector('#brief-button').disabled && document.querySelector('#replay').disabled && document.querySelector('#record-details').textContent==='' ")
  await page.locator('#question-input').fill("What's our projected Q4 revenue and profit?");await page.locator('#question-form button').click();await page.wait_for_function("() => last?.tool==='forecast_quarter'")
  report['supported_question_recovers']=await page.evaluate("() => !document.querySelector('#brief-button').disabled && !document.querySelector('#replay').disabled")
  await browser.close()
 (ROOT/'eval/interaction-qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
 assert all(report[k] for k in ['blocked_autoplay_graceful','gesture_enables_audio','voice_off_cancels_all_sentences','unsupported_clears_stale_answer','supported_question_recovers'])
 assert not report['console_errors'] and not report['nonlocal_page_requests']
if __name__=='__main__':asyncio.run(run())
