"""Real pixel evidence distinguishes an opaque overlay from a useful gradient."""
import asyncio
import base64
import io
import pytest
from PIL import Image
from playwright.async_api import async_playwright
from devteam_browser import check_artwork_visibility


def test_supplied_artwork_visibility_and_exact_style_restoration():
 async def run():
  picture=Image.new('RGB',(320,180))
  picture.putdata([(x%256,y%256,(x+y)%256) for y in range(180) for x in range(320)])
  out=io.BytesIO();picture.save(out,'PNG');uri='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
  async with async_playwright() as p:
   browser=await p.chromium.launch(args=['--no-sandbox','--disable-gpu'])
   try:
    page=await browser.new_page()
    await page.set_content('<style>.hero{position:relative;width:320px;height:180px}.hero img{width:100%;height:100%}.hero-fallback{position:absolute;inset:0;background:#123}</style><div class="hero"><img style="object-fit: cover" src="'+uri+'"><div class="hero-fallback"></div></div>')
    await page.evaluate('(uri)=>window.furyArtwork={hero:uri}',uri)
    original=await page.locator('img').get_attribute('style')
    with pytest.raises(ValueError,match='no visible artwork'):await check_artwork_visibility(page)
    assert await page.locator('img').get_attribute('style')==original
    await page.locator('.hero-fallback').evaluate("el=>el.style.background='linear-gradient(transparent,rgba(0,0,0,.4))'")
    await check_artwork_visibility(page)
    assert await page.locator('img').get_attribute('style')==original
    await page.set_content('<div style="width:320px;height:180px;background-image:url('+uri+')"></div>')
    await page.evaluate('(uri)=>window.furyArtwork={hero:uri}',uri)
    original=await page.locator('div').get_attribute('style')
    await check_artwork_visibility(page)
    assert await page.locator('div').get_attribute('style')==original
   finally:await browser.close()
 asyncio.run(run())
