#!/usr/bin/env python3
"""Render the versioned deployment guide using the pinned local Chromium."""
import argparse,asyncio,re
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
async def main(version):
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  page=await browser.new_page()
  await page.goto((ROOT/'docs/COLORADO-DEPLOYMENT.html').as_uri())
  await page.evaluate('document.fonts.ready')
  await page.wait_for_function('() => [...document.images].every(i => i.complete && i.naturalWidth > 0)')
  await page.pdf(path=str(ROOT/f'docs/Colorado-Deployment-{version}.pdf'),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=True,header_template='<span></span>',footer_template=f'<div style="font:9px Arial;width:100%;text-align:center;color:#555">HP ZGX Fury · {version} · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
  await browser.close()
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--version',default='v2.2.0');args=parser.parse_args()
 if not re.fullmatch(r'v\d+\.\d+\.\d+',args.version):parser.error('Use a numeric release version, such as v2.2.0')
 asyncio.run(main(args.version))
