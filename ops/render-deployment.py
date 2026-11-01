#!/usr/bin/env python3
"""Render the versioned deployment guide using the pinned local Chromium."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  page=await browser.new_page()
  await page.goto((ROOT/'docs/COLORADO-DEPLOYMENT.html').as_uri())
  await page.evaluate('document.fonts.ready')
  await page.wait_for_function('() => [...document.images].every(i => i.complete && i.naturalWidth > 0)')
  await page.pdf(path=str(ROOT/'docs/Colorado-Deployment-v2.1.0.pdf'),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=True,header_template='<span></span>',footer_template='<div style="font:9px Arial;width:100%;text-align:center;color:#555">HP ZGX Fury · v2.1.0 · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
  await browser.close()
if __name__=='__main__':asyncio.run(main())
