#!/usr/bin/env python3
"""Real browser checks for HP shell, routes, theme, keyboard and responsive layout.
No inference is submitted. Evidence remains local under reports/. Optional axe audit
uses an explicitly supplied local axe.min.js; no third-party runtime/CDN dependency.
"""
import argparse,asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
PAGES=[('home',8080,'/'),('atlas',8200,'/'),('slides',8765,'/booth'),('factory',8501,'/devteam'),('image',8800,'/'),('operator',8080,'/operator'),('editor',8765,'/'),('connect',8080,'/connect')]
def lum(value):
 v=[int(value[i:i+2],16)/255 for i in (0,2,4)];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v];return sum(x*w for x,w in zip(v,[.2126,.7152,.0722]))
def contrast(a,b):
 x,y=sorted([lum(a),lum(b)]);return (y+.05)/(x+.05)
async def main(a):
 out=a.output/time.strftime('%Y%m%dT%H%M%S');out.mkdir(parents=True,exist_ok=True);results=[]
 pairs=[('primary on white','024AD8','FFFFFF'),('body on white','1A1A1A','FFFFFF'),('secondary on gray50','6B6B6B','F7F7F7'),('dark secondary','D6D6D6','262626')]
 ratios={label:round(contrast(x,y),2) for label,x,y in pairs};assert all(v>=4.5 for v in ratios.values())
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  for name,port,path in PAGES:
   for mode,width,height in [('light',1440,1000),('light',1280,800),('light',390,844),('dark',1440,1000)]:
    ctx=await browser.new_context(viewport={'width':width,'height':height},color_scheme=mode,reduced_motion='reduce',bypass_csp=bool(a.axe));page=await ctx.new_page();errors=[];bad=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:bad.append({'status':r.status,'path':r.url.split('/',3)[-1]}) if r.status>=400 else None)
    response=await page.goto(f'http://{a.host}:{port}{path}');assert response.status==200;await page.wait_for_timeout(1200)
    assert await page.locator('.hp-shell').count()==1;assert await page.locator('a[href="#main"]').count()==1
    logo=await page.locator('.hp-logo').bounding_box();assert round(logo['width'])==48 and round(logo['height'])==48
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth'),name+' page overflow'
    await page.keyboard.press('Tab');assert 'Skip to content' in await page.evaluate('document.activeElement.textContent'),name+' skip link'
    await page.keyboard.press('Enter');assert await page.evaluate("document.activeElement===document.querySelector('main')||document.activeElement===document.getElementById('root')"),name+' skip target'
    for sel in ['.hp-theme','.hp-shell nav a']:
     for item in await page.locator(sel).all():
      box=await item.bounding_box();assert box['height']>=44
    if name=='home':
     for anchor in ['catalog','why','concurrency','presenter']:assert await page.locator('#'+anchor).count()==1
     assert await page.locator('[data-copy]').count()==4
     # Explicit choice survives reload and takes priority over system preference.
     await page.locator('.hp-theme').click();assert await page.locator('html').get_attribute('data-hp-theme')=='light'
     await page.reload();assert await page.locator('html').get_attribute('data-hp-theme')=='light'
    violations=[]
    if a.axe:
     await page.add_script_tag(path=str(a.axe));audit=await page.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})")
     violations=[{'id':v['id'],'targets':[n['target'] for n in v['nodes']]} for v in audit['violations']]
    await page.screenshot(path=str(out/f'{name}-{mode}-{width}.png'),full_page=True)
    results.append({'page':name,'mode':mode,'width':width,'errors':errors,'failed_http':bad,'axe_violations':violations})
    assert not errors and not bad and not violations,(name,errors,bad,violations)
    await ctx.close()
  await browser.close()
 (out/'report.json').write_text(json.dumps({'contrast_ratios':ratios,'pages':results,'scope':'Chromium on tested host; automation is not complete WCAG certification'},indent=2));print(out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--host',default='localhost');p.add_argument('--output',type=Path,default=ROOT/'reports/hp-ui');p.add_argument('--axe',type=Path);asyncio.run(main(p.parse_args()))
