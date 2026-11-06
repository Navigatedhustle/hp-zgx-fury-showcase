#!/usr/bin/env python3
"""Real no-inference V3 page/viewport checks and source-safe screenshots."""
import argparse,asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
PAGES=[('home',8080,'/'),('models',8080,'/models'),('performance',8080,'/performance'),('economics',8080,'/economics'),('secure',8080,'/secure'),('about',8080,'/about'),('vision',8080,'/experience/vision'),('translate',8080,'/experience/translate'),('video',8080,'/experience/video'),('trailer',8080,'/experience/trailer'),('image',8800,'/'),('atlas',8200,'/'),('slides',8765,'/booth'),('factory',8501,'/devteam')]
VIEWPORTS=[(1366,768),(1280,720),(1440,900),(1920,1080),(1366,640),(1280,620),(390,844)]
async def main(args):
 out=Path(args.output)/time.strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True);rows=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox','--disable-gpu'])
  try:
   for name,port,path in PAGES:
    for width,height in VIEWPORTS:
     context=await browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=await context.new_page();errors=[];bad=[]
     page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r:bad.append({'status':r.status,'url':r.url}) if r.status>=400 else None)
     await page.goto(f'http://{args.host}:{port}{path}',wait_until='domcontentloaded');await page.wait_for_timeout(800)
     geometry=await page.evaluate('''()=>({width:innerWidth,height:innerHeight,bodyHeight:document.documentElement.scrollHeight,bodyWidth:document.documentElement.scrollWidth,go:(()=>{const e=document.getElementById('go')||document.getElementById('consent-button');if(!e)return null;const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,visible:r.top>=0&&r.bottom<=innerHeight}})()})''')
     passed=not errors and not bad and geometry['bodyWidth']<=width and (width<1000 or geometry['bodyHeight']<=height+1) and (width<1000 or not geometry['go'] or geometry['go']['visible'])
     if width==1366 and height==768:await page.screenshot(path=str(out/(name+'.png')),full_page=True)
     rows.append({'page':name,'viewport':[width,height],'geometry':geometry,'browser_errors':errors,'failed_http':bad,'passed':passed});(out/'report.json').write_text(json.dumps({'pages':rows,'passed':all(r['passed'] for r in rows),'scope':'Chromium on tested host, no inference; original fictional samples and consent screen only'},indent=2));await context.close()
    print(name,flush=True)
  finally:await browser.close()
 assert all(r['passed'] for r in rows),[r for r in rows if not r['passed']]
 print(out)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--host',default='localhost');parser.add_argument('--output',default='reports/v3-ui');asyncio.run(main(parser.parse_args()))
