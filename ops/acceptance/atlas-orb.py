#!/usr/bin/env python3
"""Real local speech/analyser and retained-workspace orb acceptance; no physical audio claim."""
import argparse,asyncio,json,time,traceback
from pathlib import Path
from playwright.async_api import async_playwright

async def main(args):
 out=Path(args.output)/time.strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True)
 remote=args.host.endswith('.ts.net');origin=('https://' if remote else 'http://')+args.host+('' if remote else ':8080')
 report={'started':time.time(),'scope':'Chromium on the Fury using actual local TTS and Web Audio analyser. Private HTTPS when selected; no physical speaker/microphone quality claim.','samples':[],'viewports':[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox']);context=await browser.new_context(viewport={'width':1366,'height':768});page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  try:
   await page.goto(origin+'/demos?demo=atlas');workspace=page.frame_locator('iframe[data-demo=atlas]');await workspace.locator('#replay').wait_for();frame=next(f for f in page.frames if ':8200' in f.url)
   await frame.wait_for_function('()=>last&&state!=="thinking"',timeout=30000);await frame.evaluate('attract=false;voice=true');await workspace.locator('#replay').click()
   await frame.wait_for_function('()=>state==="speaking"&&orb.level>.01',timeout=30000,polling=50)
   for _ in range(8):
    report['samples'].append(await frame.evaluate('()=>({state,level:orb.level,frames:orb.frames,width:document.getElementById("voice-orb").clientWidth})'));await page.wait_for_timeout(100)
   assert report['samples'][-1]['frames']>report['samples'][0]['frames'] and any(s['level']>.01 for s in report['samples'])
   assert all(s['width']>=190 for s in report['samples']);assert await workspace.locator('#voice-orb').evaluate('e=>getComputedStyle(e).filter')=='none'
   await page.screenshot(path=str(out/'speaking.png'))
   await workspace.locator('#audio-pause').click();await frame.wait_for_function('()=>audioPaused&&audioContext.state==="suspended"');before=await frame.evaluate('orb.frames');await page.wait_for_timeout(500);assert await frame.evaluate('orb.frames')<=before+1
   await workspace.locator('#audio-pause').click();await frame.wait_for_function('()=>!audioPaused&&audioContext.state==="running"');await frame.wait_for_function('()=>orb.level>.01');report['pause_resume_passed']=True
   await frame.evaluate('stopSpeech()');await frame.wait_for_function('()=>state==="idle"');report['returns_to_idle']=True
   for width,height in [(1366,768),(1280,720),(1440,900),(1920,1080),(1366,640),(1280,620)]:
    await page.set_viewport_size({'width':width,'height':height});await page.wait_for_timeout(100)
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1')
    assert await frame.evaluate('document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1')
    for selector in ['#question-input','#talk','#replay']:
     box=await workspace.locator(selector).bounding_box();assert box and box['y']>=0 and box['y']+box['height']<=height+1
    report['viewports'].append({'width':width,'height':height,'passed':True})
   await page.emulate_media(reduced_motion='reduce');await page.wait_for_timeout(100);before=await frame.evaluate('orb.frames');await page.wait_for_timeout(500);assert await frame.evaluate('orb.frames')<=before+1;report['reduced_motion_static']=True
   await page.emulate_media(reduced_motion='no-preference');await page.locator('.all-demos').click();before=await frame.evaluate('orb.frames');await page.wait_for_timeout(500);assert await frame.evaluate('orb.frames')<=before+1
   await page.locator('a[data-demo=atlas]').click();await page.wait_for_timeout(500);assert await frame.evaluate('orb.frames')>before;report['hidden_workspace_stops_and_resumes']=True
   assert not errors,errors;report['passed']=True
  except Exception:report.update(passed=False,error=traceback.format_exc())
  finally:
   report.update(ended=time.time(),browser_exceptions=errors);(out/'report.json').write_text(json.dumps(report,indent=2));await browser.close()
 print(json.dumps({'passed':report.get('passed'),'error':report.get('error'),'viewports':len(report['viewports']),'evidence':str(out)},indent=2));return report.get('passed',False)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--host',default='localhost');parser.add_argument('--output',default='reports/atlas-orb');raise SystemExit(0 if asyncio.run(main(parser.parse_args())) else 1)
