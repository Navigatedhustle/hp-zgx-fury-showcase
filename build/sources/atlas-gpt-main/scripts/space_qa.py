"""Keyboard push-to-talk works when the main button holds focus."""
import asyncio,json,os,wave
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def run():
 audio=ROOT/'eval/question-1.wav'
 with wave.open(str(audio)) as f:duration=f.getnframes()/f.getframerate()
 report={'console_errors':[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+str(audio),'--autoplay-policy=document-user-activation-required'])
  page=await browser.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:report['console_errors'].append(str(e)))
  await page.goto('http://localhost:8200');await page.wait_for_function("() => last?.tool==='forecast_quarter'")
  await page.locator('#talk').focus();await page.keyboard.down('Space');await page.wait_for_function('() => recording===true')
  report['space_records_with_button_focus']=True
  await page.wait_for_timeout((duration+.15)*1000)
  async with page.expect_response(lambda r:r.url.endswith('/api/query')) as response:await page.keyboard.up('Space')
  answer=await(await response.value).json();await page.wait_for_function('() => sources.size>0')
  report['correct_tool']=answer['tool']=='forecast_quarter';report['grounded']=answer['grounding']['passed']
  await page.keyboard.down('Space');await page.wait_for_timeout(80);report['space_barge_in']=await page.evaluate('() => sources.size===0');await page.keyboard.up('Space')
  await browser.close()
 (ROOT/'eval/space-qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
 assert all(report[k] for k in ['space_records_with_button_focus','correct_tool','grounded','space_barge_in']) and not report['console_errors']
if __name__=='__main__':asyncio.run(run())
