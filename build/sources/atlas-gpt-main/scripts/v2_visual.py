import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def run():
    target=ROOT/'eval/screenshots/v2';target.mkdir(parents=True,exist_ok=True)
    errors=[];geometry={}
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
        page=await b.new_page(viewport={'width':1920,'height':1080})
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8200');await page.wait_for_function('() => last !== null');await page.locator('#attract-toggle').click()
        for persona in ['enterprise','university']:
            await page.locator('[data-persona='+persona+']').click();await page.wait_for_function('(p) => last.persona===p && state===\'idle\'',arg=persona)
            await page.wait_for_timeout(600);await page.screenshot(path=str(target/f'{persona}.png'))
            geometry[persona]=await page.evaluate('() => ({height:document.body.scrollHeight,orb:document.getElementById("voice-orb").getBoundingClientRect().toJSON(),strip:document.querySelector(".model-strip").getBoundingClientRect().toJSON()})')
        await page.locator('#replay').click();await page.wait_for_function('() => sources.size>0');await page.wait_for_timeout(500);await page.screenshot(path=str(target/'orb-speaking.png'));geometry['audio_level']=await page.evaluate('() => orb.level');await page.evaluate('stopSpeech()')
        await page.locator('#stage-toggle').click();await page.screenshot(path=str(target/'stage.png'));await page.locator('#stage-toggle').click()
        await page.locator('#record-open').click();await page.locator('[data-record=wide]').click();await page.wait_for_timeout(400);await page.screenshot(path=str(target/'landscape.png'));await page.keyboard.press('Escape');await page.locator('#record-open').click();await page.locator('[data-record=vertical]').click();await page.set_viewport_size({'width':1080,'height':1920});await page.wait_for_timeout(400);await page.screenshot(path=str(target/'portrait.png'))
        await b.close()
    report={'errors':errors,'geometry':geometry};(ROOT/'eval/v2/visual.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));assert not errors
asyncio.run(run())
