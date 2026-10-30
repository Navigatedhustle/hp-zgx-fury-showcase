import asyncio,os,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def main():
    errors=[]
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True);page=await b.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8200');await page.wait_for_function('() => last!==null');await page.locator('#attract-toggle').click();await page.locator('[data-persona=developer]').click();await page.wait_for_function('() => document.getElementById("code-status").textContent.includes("VERIFIED")',timeout=60000);await page.screenshot(path=str(ROOT/'eval/screenshots/v2/developer-code.png'));print(json.dumps({'errors':errors,'result':await page.locator('#code-status').inner_text()}));assert not errors;await b.close()
asyncio.run(main())
