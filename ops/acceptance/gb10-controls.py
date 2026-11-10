#!/usr/bin/env python3
"""Real clicker, routing, motion and reset proof on the warmed native kiosk."""
import asyncio
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'ops')]
spec = importlib.util.spec_from_file_location('stage_proof', Path(__file__).with_name('gb10-stage.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from showcase_app.gb10_client import infer, LEAD, WORKER


async def main():
    proof = module.Proof('controls')
    results = {}
    async with httpx.AsyncClient(trust_env=False, timeout=70) as client, async_playwright() as p:
        proof.client = client
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:18810')
        page = proof.page = browser.contexts[0].pages[0]
        assert (await client.get('http://127.0.0.1:18809/health')).json()['headless'] is False
        await proof.ready()
        await proof.reset()
        for headers, body, expected in [({'Origin': 'https://example.invalid'}, {'action': 'next'}, 403),
            ({'Host': 'example.invalid'}, {'action': 'next'}, 403)]:
            response = await client.post(module.BASE + '/stage/api/control', headers=headers, json=body)
            assert response.status_code == expected
        response = await client.post(module.BASE + '/stage/api/control', content=b'x' * 65537)
        assert response.status_code == 413 and (await proof.state())['view'] == -1
        results['real_origin_host_upload_guards'] = True
        await page.goto(module.BASE + '/stage/keys')
        for key in ['ArrowRight', 'PageDown', ' ', 'Enter', 'ArrowLeft', 'PageUp', 'v', 'r', 'b', '.', 'a']:
            await page.keyboard.press(key)
            assert 'keyup' in await page.locator('#key-value').inner_text()
        assert (await proof.state())['view'] == -1
        results['raw_key_test_page'] = True
        await page.goto(module.BASE + '/stage')
        await asyncio.sleep(.8)
        for key in ['ArrowRight', 'PageDown', ' ', 'Enter']:
            await page.keyboard.press(key)
        await asyncio.sleep(.3)
        state = await proof.state()
        assert state['view'] == 0
        original = state['run']['id']
        results['600ms_debounce'] = True
        for key in ['a', 'Home', 'ArrowUp', 'ArrowDown', 'q', '3']:
            await page.keyboard.press(key)
        assert (await proof.state())['run']['id'] == original
        results['unmapped_keys_ignored'] = True
        await asyncio.sleep(.7)
        await page.keyboard.press('ArrowLeft')
        assert (await proof.state())['view'] == -1
        await asyncio.sleep(.7)
        await page.keyboard.press('ArrowRight')
        assert (await proof.state())['run']['id'] == original
        results['back_does_not_rerun'] = True
        await asyncio.sleep(.7)
        await page.keyboard.press('b')
        assert not await page.locator('#black').evaluate('(e)=>e.hidden')
        await asyncio.sleep(.7)
        await page.keyboard.press('.')
        assert await page.locator('#black').evaluate('(e)=>e.hidden')
        results['both_blank_keys'] = True
        await asyncio.sleep(.7)
        async with page.expect_request('**/stage/api/control-frame', timeout=3000) as frame:
            await page.keyboard.press('v')
        actual = (await frame.value).post_data_json
        await proof.wait_for("()=>Number(getComputedStyle(document.querySelector('#backup')).opacity)>=.99")
        assert (await proof.state())['run']['backup']
        await page.screenshot(path=str(proof.folder / 'manual-recorded-backup.png'))
        await asyncio.sleep(.7)
        await page.keyboard.press('v')
        await asyncio.sleep(.2)
        assert not (await proof.state())['run']['backup']
        results['manual_backup_frame_and_return'] = actual
        await asyncio.sleep(.7)
        await page.keyboard.down('r')
        await asyncio.sleep(1)
        await page.keyboard.up('r')
        await asyncio.sleep(.3)
        assert (await proof.state())['run']['id'] == original
        await page.keyboard.down('r')
        await asyncio.sleep(2.1)
        await page.keyboard.up('r')
        deadline = time.monotonic() + 60
        while True:
            state = await proof.state()
            if state['run']['id'] != original and state['run']['status'] == 'complete':
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Held reset did not restart S0')
            await asyncio.sleep(.1)
        results['short_r_ignored_and_2s_hold_resets'] = True
        await asyncio.sleep(.7)
        await page.keyboard.press('b')
        reset_started = time.monotonic()
        first = asyncio.create_task(client.post(module.BASE + '/stage/api/control', json={'action': 'reset'}))
        while not (await proof.state())['resetting']:
            await asyncio.sleep(.02)
        rejected = await client.post(module.BASE + '/stage/api/control', json={'action': 'reset'})
        assert rejected.status_code == 409
        assert (await proof.state())['resetting']
        await page.keyboard.press('ArrowRight')
        response = await first
        response.raise_for_status()
        await proof.wait_for("()=>document.querySelector('#black').hidden")
        await asyncio.sleep(.8)
        state = await proof.state()
        assert state['view'] == -1 and not state['pending'] and state['readiness']['ready']
        assert time.monotonic() - reset_started < 60
        results['concurrent_reset_rejected_and_ready_unblanks'] = True
        await page.keyboard.press('ArrowRight')
        await asyncio.sleep(.8)
        await page.keyboard.press('PageDown')
        fps_task = asyncio.create_task(page.evaluate('''()=>new Promise(resolve=>{let start=performance.now(),last=start,deltas=[];function tick(now){deltas.push(now-last);last=now;if(now-start<2000)requestAnimationFrame(tick);else resolve({frames:deltas.length,seconds:(now-start)/1000,deltas});}requestAnimationFrame(tick);})'''))
        for _ in range(3):
            await asyncio.sleep(.7)
            await page.keyboard.press('ArrowRight')
        assert (await proof.state())['pending']
        fps = await fps_task
        results['live_animation_cadence'] = {'frames_per_second': fps['frames'] / fps['seconds'],
            'p95_frame_interval_ms': module.percentile(fps['deltas'], .95)}
        assert results['live_animation_cadence']['frames_per_second'] >= 59
        deadline = time.monotonic() + 60
        while True:
            state = await proof.state()
            active = list(state['health']['gateway'].get('active', {}).values())
            if state['health']['image'].get('render_active') and any(x['model'] == LEAD for x in active) and any(x['model'] == WORKER for x in active):
                break
            if state['beat'] != 'S1' or time.monotonic() > deadline:
                raise RuntimeError('The Agent never showed all three model lanes busy together')
            await asyncio.sleep(.1)
        await page.screenshot(path=str(proof.folder / 'agent-three-live-lanes.png'))
        probe = asyncio.create_task(infer([{'role': 'user', 'content': 'Write a short paragraph explaining why a fictional local planning pilot needs clear owners and dates.'}],
            model=LEAD, caller='rush', run_id=state['run']['id'], purpose='live', role='priority_probe', max_tokens=128))
        await proof.wait_for("()=>document.querySelector('.route')?.textContent.includes('Routed to Qwen3.6: gpt-oss-120b is busy')", timeout=10)
        routed = await probe
        assert routed['model'] == WORKER and routed['routing'] == 'Routed to Qwen3.6: gpt-oss-120b is busy'
        results['real_priority_routing_visible_and_measured'] = {'model': routed['model'], 'routing': routed['routing'], 'output_tokens': routed['usage']['completion_tokens']}
        deadline = time.monotonic() + 100
        while True:
            state = await proof.state()
            if state['beat'] == 'S2' and state['run']['status'] == 'complete':
                break
            if state['run']['backup'] or time.monotonic() > deadline:
                raise RuntimeError('A queued advance failed to complete live')
            await asyncio.sleep(.15)
        await asyncio.sleep(1)
        assert (await proof.state())['beat'] == 'S2' and not (await proof.state())['pending']
        results['three_next_presses_queue_exactly_one_advance'] = True
        await proof.reset()
        await page.emulate_media(reduced_motion='reduce')
        reduced = await page.evaluate('''()=>{let e=document.createElement('div');e.className='fade-in';document.body.append(e);let x={preference:matchMedia('(prefers-reduced-motion: reduce)').matches,animation:getComputedStyle(e).animationName,backupTransition:getComputedStyle(document.querySelector('#backup')).transitionDuration};e.remove();return x;}''')
        assert reduced['preference'] and reduced['animation'] == 'none' and reduced['backupTransition'] == '0s'
        await page.emulate_media(reduced_motion=None)
        results['reduced_motion'] = reduced
        results['passed'] = True
        proof.save('summary.json', results)
        print(json.dumps(results, indent=2), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
