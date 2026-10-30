"""Run against the explicitly started prebuilt reference server on localhost:8510."""
import asyncio,json,sys,uuid
from pathlib import Path
from datetime import date,timedelta
from playwright.async_api import async_playwright
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'build/sources/fury_agent_factory'))
from travel_checks import check_product
result=check_product(root/'examples/reference-travel/app',root/'state/reference-checks');assert result['passed'],result.get('log');print('Reference backend: all checks passed',flush=True)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--no-sandbox']);page=await b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://localhost:8510');await page.locator('#listing-list [data-detail]').first.wait_for()
  assert 'PREBUILT REFERENCE' in await page.locator('body').inner_text()
  await page.locator('#auth-nav').click();await page.locator('[data-target=register-form]').click()
  await page.locator('#register-form [name=email]').fill('reference'+uuid.uuid4().hex[:8]+'@example.test');await page.locator('#register-form [name=password]').fill('ReferenceDemo2028!');await page.locator('#register-form button[type=submit]').click()
  await page.locator('#listing-list [data-detail]').first.wait_for();await page.locator('#listing-list [data-detail]').first.click();await page.locator('#quote-form').wait_for()
  await page.locator('[name=check_in]').fill(str(date.today()+timedelta(days=45)));await page.locator('[name=check_out]').fill(str(date.today()+timedelta(days=48)));await page.locator('#quote-button').click();await page.locator('#reserve-button').wait_for();await page.locator('#reserve-button').click();await page.locator('#reservations-list .trip-card').first.wait_for()
  await page.reload();await page.wait_for_function("() => document.getElementById('user-display').textContent.includes('@example.test')");await page.locator('.nav-link[data-view=reservations]').click();await page.locator('#reservations-list .trip-card').first.wait_for()
  assert not errors,errors
  out=root/'reports/reference';out.mkdir(parents=True,exist_ok=True);await page.screenshot(path=str(out/'reference.png'));await b.close();print('REFERENCE BROWSER PASS',flush=True)
asyncio.run(main())
