import asyncio,json,os
from atlas.config import ROOT
from playwright.async_api import async_playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'vendor/browsers')
async def main():
    errors=[];checks={}
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required']);page=await b.new_page(viewport={'width':1920,'height':1080});page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8200');await page.wait_for_function('() => last!==null');await page.locator('#attract-toggle').click();await page.locator('#voice-toggle').click()
        for persona,q,name in [('enterprise','Which five deals are most at risk this quarter, and why?','risk'),('enterprise','Should we build a new sales center in Phoenix, Denver, or Albuquerque?','site-decision'),('enterprise',"Summarize the board's concerns about margin.",'document-citations'),('developer','Explain how the Q4 forecast is calculated and show me the code.','source-explanation'),('developer','Write unit tests for the site scoring function and run them.','unit-tests'),('developer','How fast is the model running right now, and how do I connect my own tools to it?','endpoint')]:
            if persona!=await page.evaluate('persona'):await page.locator('[data-persona='+persona+']').click();await page.wait_for_function('(p) => persona===p && state===\'idle\'',arg=persona,timeout=60000)
            await page.evaluate('(q) => ask(q)',q);await page.wait_for_timeout(600);await page.screenshot(path=str(ROOT/'eval/screenshots/v2'/f'{name}.png'));checks[name]=await page.evaluate('() => ({state,bodyHeight:document.body.scrollHeight,status:document.getElementById("code-status").textContent})')
        await page.locator('[data-persona=enterprise]').click();await page.wait_for_function('() => persona===\'enterprise\' && state===\'idle\'');await page.locator('#orb-setting').uncheck();checks['v1_restore']=await page.evaluate('() => !document.body.classList.contains("orb-enabled") && document.querySelector(".center-column .chart-block")!==null');await page.locator('#orb-setting').check();await page.locator('#golden-button').click();checks['golden_tabs']=await page.locator('.golden-tabs button').count();await page.locator('[data-golden-persona=university]').click();await page.wait_for_function('() => persona===\'university\' && state===\'idle\'');checks['university_questions']=await page.locator('#golden-questions button').count();await b.close()
    result={'errors':errors,'checks':checks};(ROOT/'eval/v2/ui-states.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert not errors and checks['v1_restore'] and checks['golden_tabs']==3
asyncio.run(main())
