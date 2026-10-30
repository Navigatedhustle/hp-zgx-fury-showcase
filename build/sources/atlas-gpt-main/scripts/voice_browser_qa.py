"""Exercise the real browser capture, streaming ASR, playback and barge-in.

Chromium receives locally generated question audio as its test microphone.
No human, real microphone, browser profile, or external connection is used.
"""
import asyncio
import json
import os
import time
import wave
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'vendor/browsers')


async def run():
    audio = ROOT / 'eval/question-1.wav'
    with wave.open(str(audio)) as source:
        duration = source.getnframes() / source.getframerate()
    report = {'test_microphone': 'locally synthesized WAV', 'duration_s': duration,
              'console_errors': [], 'stream_events': [], 'queries': [], 'metrics': []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
            '--use-file-for-fake-audio-capture=' + str(audio),
            '--autoplay-policy=no-user-gesture-required'])
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.on('pageerror', lambda error: report['console_errors'].append(str(error)))
        page.on('console', lambda message: report['console_errors'].append(message.text)
                if message.type == 'error' else None)
        def request(req):
            if req.url.endswith('/api/metrics'):
                report['metrics'].append(json.loads(req.post_data or '{}'))
        page.on('request', request)
        def socket(ws):
            def received(payload):
                if isinstance(payload, str):
                    try: report['stream_events'].append(json.loads(payload))
                    except ValueError: pass
            ws.on('framereceived', received)
        page.on('websocket', socket)
        await page.goto('http://localhost:8200')
        await page.wait_for_function("() => document.querySelector('#headline').textContent !== '—'")
        await page.locator('#attract-toggle').click()
        button = page.locator('#talk')
        box = await button.bounding_box()
        await page.mouse.move(box['x'] + 60, box['y'] + 35)
        await page.mouse.down()
        await page.wait_for_function('() => recording === true')
        await page.wait_for_timeout((duration + .15) * 1000)
        start = time.perf_counter()
        async with page.expect_response(lambda r: r.url.endswith('/api/query'), timeout=15000) as response:
            await page.mouse.up()
        answer_response = await response.value
        answer = await answer_response.json()
        report['queries'].append(answer)
        await page.wait_for_function('() => sources.size > 0', timeout=15000)
        report['observed_end_to_playback_s'] = time.perf_counter() - start
        report['client_timings'] = await page.evaluate('() => ({...last.timings,...last.voiceTimings})')
        report['audio_context_base_latency_ms'] = await page.evaluate('() => audioContext.baseLatency*1000')
        report['transcript'] = await page.locator('#transcript').inner_text()
        report['correct_tool'] = answer.get('tool') == 'forecast_quarter'
        report['grounded'] = answer.get('grounding', {}).get('passed', False)
        report['live_partials'] = sum(e.get('type', '').endswith('.delta') for e in report['stream_events'])
        await page.screenshot(path=str(ROOT / 'eval/screenshots/voice-speaking.png'))
        # A new press must stop every scheduled audio source immediately.
        await page.mouse.down()
        await page.wait_for_timeout(80)
        report['barge_in_stopped_audio'] = await page.evaluate('() => sources.size === 0')
        await page.mouse.up()
        await page.wait_for_timeout(2000)
        await browser.close()
    samples_path=ROOT/'eval/voice-browser-samples.json'
    try:samples=json.loads(samples_path.read_text())
    except (OSError,ValueError):samples=[]
    samples.append({'measured_at':time.time(),'observed_end_to_playback_s':report['observed_end_to_playback_s'],'browser_ttfa_ms':report['metrics'][0]['ttfa_ms'] if report['metrics'] else None,'partials':report['live_partials'],'grounded':report['grounded'],'correct_tool':report['correct_tool'],'barge_in':report['barge_in_stopped_audio']})
    samples_path.write_text(json.dumps(samples,indent=2))
    path = ROOT / 'eval/voice-browser-qa.json'
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ['queries', 'stream_events']}, indent=2), flush=True)
    assert report['correct_tool'] and report['grounded'] and report['live_partials'] > 0
    assert report['barge_in_stopped_audio'] and not report['console_errors']


if __name__ == '__main__':
    asyncio.run(run())
