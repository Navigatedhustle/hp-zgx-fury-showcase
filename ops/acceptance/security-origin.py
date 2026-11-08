#!/usr/bin/env python3
"""Real browser CSRF proof against the live dashboard; fictional skin only."""
import argparse
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]


class ForeignPage(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<!doctype html><title>Fictional foreign-origin security fixture</title>
        <form action="http://localhost:8080/api/appearance/reset" method="post" enctype="text/plain">
        <input name="fixture" value="untrusted"><button id="attack">Submit foreign form</button></form>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def main(output):
    server = HTTPServer(('127.0.0.1', 0), ForeignPage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'passed': False, 'scope': 'Actual localhost dashboard and separate loopback HTTP origin; real browser form and raw logo upload; no model inference or real customer identity.'}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1366, 'height': 768}, reduced_motion='reduce')
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            await page.goto('http://localhost:8080/demos')
            state = await page.evaluate("fetch('/skin/state').then(r=>r.json())")
            if state.get('active') and state['active']['name'] != 'Northwind Beverages':
                raise RuntimeError('Use default appearance or the fictional fixture before this acceptance')
            await page.locator('#skin-customize').wait_for()
            await page.click('#skin-customize')
            await page.fill('#skin-name', 'Northwind Beverages')
            await page.click('#skin-manual')
            async with page.expect_response(lambda r: r.url.endswith('/skin/upload') and r.request.method == 'POST') as uploaded:
                await page.set_input_files('#skin-file', str(ROOT / 'ops/tests/fixtures/skin/northwind.svg'))
            response = await uploaded.value
            assert response.status == 200, 'The legitimate raw image upload failed'
            report['same_origin_upload_status'] = response.status
            await page.locator('#skin-apply').wait_for()
            await page.click('#skin-apply')
            await page.wait_for_function("()=>document.getElementById('skin-prepared').textContent.includes('Northwind Beverages')")
            foreign = await browser.new_context()
            attack = await foreign.new_page()
            await attack.goto('http://127.0.0.1:' + str(server.server_port) + '/')
            async with attack.expect_response(lambda r: r.url.endswith('/api/appearance/reset') and r.request.method == 'POST') as attempted:
                await attack.click('#attack')
            denied = await attempted.value
            assert denied.status == 403, 'A foreign form reached the mutation'
            state = await page.evaluate("fetch('/skin/state').then(r=>r.json())")
            assert state['active']['name'] == 'Northwind Beverages', 'The rejected form changed shared appearance'
            report.update(foreign_form_status=denied.status, shared_state_preserved=True)
            await foreign.close()
            reset = await page.evaluate("fetch('/skin/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)")
            assert reset == 200
            assert (await page.evaluate("fetch('/skin/state').then(r=>r.json())"))['active'] is None
            assert not errors, errors
            report.update(same_origin_json_reset_status=reset, no_pin_required=True, browser_errors=errors, passed=True)
        finally:
            # This script may clear only its own fictional/default appearance.
            try:
                try:
                    state = await page.evaluate("fetch('/skin/state').then(r=>r.json())")
                    if state.get('active') and state['active']['name'] == 'Northwind Beverages':
                        await page.evaluate("fetch('/skin/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})")
                except Exception as error:
                    report.update(passed=False, cleanup_error=type(error).__name__)
                await browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
