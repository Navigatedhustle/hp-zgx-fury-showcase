"""Verify missing hardware and real detector responses to a synthetic camera."""
import asyncio,io,json,os
from pathlib import Path
import httpx
from PIL import Image
from playwright.async_api import async_playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(Path('vendor/browsers').resolve())
async def run():
 report={'errors':[]}
 async with httpx.AsyncClient(timeout=5,trust_env=False) as c:
  for _ in range(80):
   try:
    r=await c.get('http://127.0.0.1:8205/health');r.raise_for_status();break
   except httpx.HTTPError:await asyncio.sleep(.25)
  b=io.BytesIO();Image.new('RGB',(640,360),'white').save(b,format='JPEG')
  r=await c.post('http://127.0.0.1:8200/api/detect',content=b.getvalue(),headers={'Content-Type':'image/jpeg'});r.raise_for_status();report['blank_frame']=r.json();assert report['blank_frame']['people']==0
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True);page=await browser.new_page(viewport={'width':1920,'height':1080})
  await page.goto('http://localhost:8200');await page.locator('#enable-camera').click();await page.wait_for_timeout(700);report['without_camera']=await page.locator('#camera-message').inner_text();await page.screenshot(path='eval/screenshots/no-camera.png');await browser.close()
  browser=await p.chromium.launch(headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']);page=await browser.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:report['errors'].append(str(e)));page.on('console',lambda m:report['errors'].append(m.text) if m.type=='error' else None)
  await page.goto('http://localhost:8200');await page.locator('#enable-camera').click();await page.wait_for_function("() => document.querySelector('#people-count').textContent.includes('PEOPLE')");report['test_camera']=await page.locator('#people-count').inner_text();await page.screenshot(path='eval/screenshots/synthetic-camera.png');await browser.close()
 Path('eval/camera-qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert not report['errors']
asyncio.run(run())
