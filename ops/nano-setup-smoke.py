#!/usr/bin/env python3
"""Post-install checks without loading a second model stack."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.cache/ms-playwright')
sys.path.insert(0, str(ROOT))

def main():
    for environment in ('.venv', '.model-venv'):
        subprocess.run([str(ROOT / environment / 'bin/python'), '-m', 'pip', 'check'], check=True)
    subprocess.run([str(ROOT / '.venv/bin/python'), '-c',
        'import fastapi,httpx,pydantic,playwright,PIL,pptx,docx,pypdf; print("Application imports OK")'], check=True)
    subprocess.run([str(ROOT / '.model-venv/bin/python'), '-c',
        'import sys,torch,diffusers,torchao,importlib.metadata; '
        'sys.path.insert(0,"build/sources/atlas-gpt-main"); from atlas import tts_server; '
        'assert importlib.metadata.version("kokoro"); import spacy; '
        'assert spacy.util.is_package("en_core_web_sm"), "English tagger missing"; '
        'assert torch.cuda.is_available(), "CUDA is unavailable"; print("Model imports and CUDA OK")'], check=True)
    engine = ROOT / '.tools/llama.cpp/build/bin/llama-server'
    help_text = subprocess.check_output([str(engine), '--help'], text=True, stderr=subprocess.STDOUT, timeout=20)
    for flag in ('--load-mode', '--kv-unified-per-slot', '--lazy-mode', '--cache-ram'):
        if flag not in help_text:
            raise RuntimeError('Pinned engine is missing required flag ' + flag)
    print('Pinned engine interfaces OK')
    from playwright.async_api import async_playwright
    from showcase_app.gb10_miniapp import launch_browser
    async def browser_check():
        async with async_playwright() as playwright:
            browser = await launch_browser(playwright)
            try:
                page = await browser.new_page()
                await page.goto('data:text/html,<title>Nano install check</title>')
                assert await page.title() == 'Nano install check'
            finally:
                await browser.close()
    asyncio.run(browser_check())
    print('Cached sandboxed Chromium OK; no model inference was started.')

if __name__ == '__main__':
    main()
