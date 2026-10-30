"""Generated microphone checks for all personas and a measured orb on/off comparison."""
import asyncio,json,os,time,wave
from pathlib import Path
import httpx
from playwright.async_api import async_playwright
from atlas.config import ROOT
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def audio(question,name):
    path=ROOT/'eval/v2'/name
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.post('http://127.0.0.1:8200/api/speech',json={'text':question});r.raise_for_status();rate=int(r.headers['X-Audio-Sample-Rate'])
    with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(r.content)
    return path,len(r.content)/(2*rate)
async def sample(p,persona,question,orb_on):
    path,duration=await audio(question,'voice-'+persona+'.wav');errors=[];metrics=[];events=[]
    b=await p.chromium.launch(headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+str(path),'--autoplay-policy=no-user-gesture-required']);page=await b.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:metrics.append(json.loads(r.post_data)) if r.url.endswith('/api/metrics') else None)
    await page.goto('http://127.0.0.1:8200');await page.wait_for_function('() => last!==null');await page.locator('#attract-toggle').click()
    if persona!='enterprise':await page.locator('[data-persona='+persona+']').click();await page.wait_for_function('(p) => persona===p && state===\'idle\'',arg=persona,timeout=60000)
    if not orb_on:await page.locator('#orb-setting').uncheck()
    button=page.locator('#orb-button' if orb_on else '#talk');box=await button.bounding_box();await page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);await page.mouse.down();await page.wait_for_function('() => recording===true');await page.wait_for_timeout((duration+.15)*1000)
    async with page.expect_response(lambda r:r.url.endswith('/api/query'),timeout=60000) as answer:await page.mouse.up()
    response=await answer.value;result=await response.json();await page.wait_for_function('() => sources.size>0',timeout=60000);levels=[]
    for _ in range(8):levels.append(await page.evaluate('() => orb.level'));await page.wait_for_timeout(70)
    data={'persona':persona,'orb_on':orb_on,'question':question,'result':result,'metrics':metrics,'max_audio_level':max(levels),'errors':errors,'captions':await page.locator('#orb-caption').inner_text()}
    if persona=='developer':data['executed_status']=await page.locator('#code-status').inner_text();assert 'EXECUTED' in data['executed_status'] and 'VERIFIED' in data['executed_status']
    assert result['grounding']['passed'] and metrics and not errors
    assert (result.get('developer',{}).get('task')=='top' if persona=='developer' else result.get('tool')==('forecast_quarter' if persona=='enterprise' else 'grant_forecast'))
    if orb_on:assert max(levels)>0,'No actual audio energy reached orb'
    await page.evaluate('stopSpeech()');data['state_change_delay_ms']=await page.evaluate('() => {const t=performance.now();setState("thinking");const d=orb.changedAt-t;setState("idle");return d;}');assert data['state_change_delay_ms']<50;await b.close();return data
async def main():
    results=[]
    async with async_playwright() as p:
        for orb_on in [False,True,False,True,False,True]:
            d=await sample(p,'enterprise',"What's our projected Q4 revenue and profit?",orb_on);results.append(d);print('enterprise',orb_on,d['metrics'][0]['ttfa_ms'],flush=True)
        for persona,q in [('university',"Based on our grant pipeline, what's projected research funding for FY27?"),('developer','Write a SQL query for the top ten accounts by open pipeline, and run it.')]:
            d=await sample(p,persona,q,True);results.append(d);print(persona,d['metrics'][0]['ttfa_ms'],flush=True)
    (ROOT/'eval/v2/voice-results.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
