#!/usr/bin/env python3
"""Render the local light-brand presenter card and enforce a single PDF page."""
import asyncio
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.async_api import async_playwright
from showcase_app.gb10_miniapp import launch_browser

async def main():
    source = ROOT / 'docs/stage/PRESENTER_CARD.html'
    output = source.with_suffix('.pdf')
    async with async_playwright() as p:
        browser = await launch_browser(p)
        try:
            page = await browser.new_page(viewport={'width': 1123, 'height': 794})
            await page.route('**/*', lambda route: route.abort())
            await page.set_content(source.read_text(), wait_until='load')
            await page.pdf(path=str(output), format='A4', landscape=True, print_background=True,
                           prefer_css_page_size=True, tagged=True)
        finally:
            await browser.close()
    info = subprocess.check_output(['pdfinfo', str(output)], text=True)
    if 'Pages:           1' not in info:
        raise RuntimeError('The presenter card must fit one landscape page')
    subprocess.run(['pdftoppm', '-png', '-singlefile', '-r', '120', str(output), str(source.with_suffix(''))], check=True)
    print('Rendered one landscape page. Inspect docs/stage/PRESENTER_CARD.png before publication.')

if __name__ == '__main__':
    asyncio.run(main())
