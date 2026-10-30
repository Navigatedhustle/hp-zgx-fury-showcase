"""Real Chromium fixtures for silent delegated-action failures; not product evidence."""
import asyncio,json
import pytest
from travel_browser import action_probe_script

@pytest.mark.parametrize('fixed',[False,True])
def test_nested_favorite_click_reports_unreachable_delegation(fixed):
 from playwright.async_api import async_playwright
 selector='[data-view],[data-favorite]' if fixed else '[data-view]'
 handler="""window.sent=[];document.addEventListener('click',e=>{
 const target=e.target.closest('SELECTOR');
 if(target&&target.hasAttribute('data-view'))return;
 if(target&&target.hasAttribute('data-favorite'))window.sent.push({listing_id:Number(target.dataset.favorite)});
 });""".replace('SELECTOR',selector)
 async def exercise():
  async with async_playwright() as p:
   browser=await p.chromium.launch(args=['--no-sandbox']);page=await browser.new_page()
   await page.set_content('<button data-favorite="7"><svg><path d="M0 0h10v10H0z" /></svg><span>Save</span></button>')
   await page.add_script_tag(content=action_probe_script(handler)+handler)
   await page.locator('button span').click()
   sent=await page.evaluate('window.sent');trace=await page.evaluate('window.__factoryActionTrace')
   assert sent==([{'listing_id':7}] if fixed else [])
   assert trace[-1]['attributes']=={'data-favorite':'7'}
   assert trace[-1]['delegated_matches']==[{'selector':selector,'matched':fixed}]
   await browser.close()
 asyncio.run(exercise())

def test_action_probe_does_not_capture_form_credentials():
 script=action_probe_script("e.target.closest('[data-view]')")
 assert '.value' not in script and 'textContent' not in script
 assert "'data-favorite'" in script
