"""Two real Atlas browser conversations and simultaneous unique PNG/PDF exports."""
import asyncio,json,time,base64
from pathlib import Path
from playwright.async_api import async_playwright
H='localhost';OUT=Path(__file__).resolve().parents[2]/'reports/atlas-isolation';OUT.mkdir(parents=True,exist_ok=True)
async def main():
 rows=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--no-sandbox'])
  async def client(i):
   c=await b.new_context();page=await c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(f'http://{H}:8200/');await page.wait_for_function('()=>typeof config!=="undefined"&&!!config');await page.evaluate('voice=false;attract=false');await page.fill('#question-input',"What's our projected Q4 revenue and profit?");await page.locator('#question-form button').click();await page.wait_for_function('()=>last?.grounding?.passed&&state!=="thinking"',timeout=60000)
   result=await page.evaluate('last');await page.click('#brief-button');await page.wait_for_function('()=>document.getElementById("brief-preview").naturalWidth>0',timeout=30000)
   png=await page.locator('#brief-png').get_attribute('href');pdf=await page.locator('#brief-pdf').get_attribute('href')
   for kind,url,magic in [('png',png,b'\x89PNG'),('pdf',pdf,b'%PDF')]:
    data=await page.evaluate('async u=>{const r=await fetch(u);if(!r.ok)throw Error(r.status);const b=new Uint8Array(await r.arrayBuffer());let s="";for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));return btoa(s)}',url);raw=base64.b64decode(data);assert raw.startswith(magic);(OUT/(str(i)+'.'+kind)).write_bytes(raw)
   assert not errors,errors;await page.screenshot(path=str(OUT/(str(i)+'-browser.png')));await c.close();return {'session':i,'result_id':result['result_id'],'grounding':result['grounding'],'png':png,'pdf':pdf,'errors':errors}
  rows=await asyncio.gather(client(1),client(2));assert rows[0]['result_id']!=rows[1]['result_id'];assert rows[0]['png']!=rows[1]['png'];assert rows[0]['pdf']!=rows[1]['pdf'];await b.close()
 result={'at':time.time(),'passed':True,'scope':'Two independent host browser contexts over local HTTP, real grounded questions and generated artifacts','sessions':rows};(OUT/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
asyncio.run(main())
