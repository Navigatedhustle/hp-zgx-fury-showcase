#!/usr/bin/env python3
"""Owned, sandboxed native Chromium kiosk with a loopback health endpoint."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from showcase_app.gb10_miniapp import chromium_wrapper
from playwright.async_api import async_playwright

status = {'ready': False}
stop_callback = None


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/stop' or self.headers.get('Host') != '127.0.0.1:18809' or self.headers.get('Origin') not in (None, 'http://127.0.0.1:18808'):
            self.send_error(403)
            return
        self.send_response(200)
        self.end_headers()
        stop_callback()

    def do_GET(self):
        self.send_response(200 if status['ready'] else 503)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, *args):
        pass


async def main():
    global stop_callback
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    stop_callback = lambda: loop.call_soon_threadsafe(stop.set)
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    server = ThreadingHTTPServer(('127.0.0.1', 18809), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    async with async_playwright() as playwright:
        options = {'no_viewport': True}
        if os.getenv('FURY_STAGE_CAPTURE') == '1':
            folder = ROOT / 'state/stage/backup/raw'
            folder.mkdir(parents=True, exist_ok=True)
            options.update(record_video_dir=str(folder), record_video_size={'width': 1920, 'height': 1080})
            (ROOT / 'state/stage/backup/capture-start.json').write_text(json.dumps({'earliest_start': __import__('time').time()}))
        context = await playwright.chromium.launch_persistent_context(str(ROOT / 'state/stage/kiosk-profile'),
            executable_path=str(chromium_wrapper(playwright.chromium.executable_path)),
            chromium_sandbox=True, headless=os.getenv('FURY_STAGE_HEADLESS') == '1',
            proxy={'server': 'http://127.0.0.1:9', 'bypass': '127.0.0.1,localhost'},
            args=['--kiosk', '--start-fullscreen', '--window-size=1920,1080', '--force-device-scale-factor=1', '--remote-debugging-address=127.0.0.1',
                  '--remote-debugging-port=18810', '--disable-background-networking', '--disable-component-update',
                  '--disable-sync', '--disable-domain-reliability', '--disable-quic', '--no-first-run',
                  '--no-default-browser-check', '--autoplay-policy=no-user-gesture-required',
                  '--disable-features=MediaRouter,OptimizationHints,AutofillServerCommunication',
                  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1, EXCLUDE [::1]'], **options)
        page = context.pages[0] if context.pages else await context.new_page()
        page.on('pageerror', lambda error: print('Stage browser error:', error, flush=True))
        await page.goto('http://127.0.0.1:18808/stage', wait_until='domcontentloaded')
        status.update(ready=True, pid=os.getpid(), headless=os.getenv('FURY_STAGE_HEADLESS') == '1')
        await stop.wait()
        status['ready'] = False
        video = page.video
        await context.close()
        if video:
            path = await video.path()
            (ROOT / 'state/stage/backup/raw-video.json').write_text(json.dumps({'path': str(path)}))
    server.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
