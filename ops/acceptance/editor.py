"""Inspect an existing booth deck in the full editor; no new inference is submitted."""
import asyncio,re,json,zipfile
from pathlib import Path
from pptx import Presentation
from PIL import Image
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/editor';OUT.mkdir(parents=True,exist_ok=True)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--no-sandbox']);page=await b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://localhost:8765/');await page.locator('a[href^="/p/"]').first.wait_for();await page.locator('a[href^="/p/"]').first.click();await page.wait_for_timeout(1800)
  print('Existing generated deck opened in the React editor');assert len(await page.frame_locator('iframe:visible').first.locator('body').inner_text())>80
  assert '/p/' in page.url;assert not errors,errors;await page.screenshot(path=str(OUT/'editor.png'));await b.close()
 for p in (ROOT/'reports/acceptance').rglob('*.pptx'):
  deck=Presentation(p);assert len(deck.slides)==3;print('PPTX opened:',len(deck.slides),'slides')
 for p in (ROOT/'reports/acceptance').rglob('*.png'):
  with Image.open(p) as image:image.verify()
 print('All saved PNGs decoded')
asyncio.run(main())
