import asyncio,os,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def main():
    errors=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True);page=await b.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8200');await page.wait_for_function('() => last!==null');await page.locator('#attract-toggle').click();await page.locator('#brain-open').click();await page.wait_for_function('() => knowledgeView?.nodes.length>0');selected=await page.evaluate('last.result_id');await page.locator('#feed-brain').click();await page.wait_for_function('() => !document.getElementById("feed-proof").hidden',timeout=60000);await page.wait_for_function('() => !document.getElementById("feed-brain").disabled');await page.wait_for_timeout(800);await page.screenshot(path=str(ROOT/'eval/screenshots/v2/feed-the-brain.png'));print(json.dumps({'errors':errors,'proof':await page.locator('#feed-proof').inner_text()}));assert not errors;assert await page.evaluate('last.result_id')==selected;await page.locator('#feed-question').click();await page.wait_for_function('() => last?.tool==="search_knowledge" && sources.size>0',timeout=60000);assert await page.locator('#answer-citations').is_visible();await page.evaluate('stopSpeech()');await b.close()
asyncio.run(main())
