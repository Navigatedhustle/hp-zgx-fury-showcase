#!/usr/bin/env python3
"""Record actual native-kiosk segments, encode H.264 and retain private proof."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from showcase_app.gb10_miniapp import launch_browser
OUTPUT = ROOT / 'state/stage/backup'
FFMPEG = ROOT / '.cache/ms-playwright/ffmpeg-1013/ffmpeg-linux'
ENCODER = ROOT / '.tools/stage-codecs/encode'


def png_frames(stream):
    while True:
        signature = stream.read(8)
        if not signature:
            return
        if signature != b'\x89PNG\r\n\x1a\n':
            raise RuntimeError('Invalid captured PNG stream')
        data = bytearray(signature)
        while True:
            header = stream.read(8)
            if len(header) != 8:
                raise RuntimeError('Truncated capture frame')
            size = int.from_bytes(header[:4], 'big')
            if size > 64 * 1024**2:
                raise RuntimeError('Capture frame exceeds limit')
            body = stream.read(size + 4)
            if len(body) != size + 4:
                raise RuntimeError('Truncated capture chunk')
            data.extend(header + body)
            if header[4:] == b'IEND':
                break
        yield bytes(data)


def capture_start(video, marker_wall):
    earliest = json.loads((OUTPUT / 'capture-start.json').read_text())['earliest_start']
    seek = max(0, marker_wall - earliest - 15)
    process = subprocess.Popen([str(FFMPEG), '-v', 'error', '-ss', str(seek), '-i', str(video), '-t', '40',
        '-r', '30', '-c:v', 'png', '-f', 'image2', '-update', '1', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for index, frame in enumerate(png_frames(process.stdout)):
            with Image.open(io.BytesIO(frame)) as image:
                if all(c > 245 for c in image.convert('RGB').getpixel((8, 8))):
                    return marker_wall - index / 30 - seek
        error = process.stderr.read().decode()
        if process.wait():
            raise RuntimeError('Native capture decoder failed: ' + error[-500:])
        raise RuntimeError('Native recording calibration marker was not captured')
    finally:
        process.terminate()
        process.communicate(timeout=15)


def encode(video, segment, start, duration, build):
    partial = OUTPUT / (segment + '.partial.mp4')
    decoder = subprocess.Popen([str(FFMPEG), '-v', 'error', '-ss', str(max(0, start)), '-i', str(video),
        '-t', str(duration), '-r', '30', '-c:v', 'png', '-f', 'image2', '-update', '1', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        result = subprocess.run([str(ENCODER), str(partial), 'veryfast'], stdin=decoder.stdout,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        decoder.stdout.close()
        error = decoder.stderr.read()
        if decoder.wait(timeout=30) or result.returncode:
            raise RuntimeError('H.264 encoding failed: ' + (result.stderr + error).decode()[-500:])
    finally:
        if decoder.poll() is None:
            decoder.terminate()
            decoder.wait(timeout=10)
    path = OUTPUT / (segment + '.mp4')
    partial.replace(path)
    return {'build': build, 'segment': segment, 'recorded_at': time.time(), 'source': 'Actual live run on this GB10 native kiosk',
            'codec': 'H.264', 'fps': 30, 'preset': 'veryfast', 'encoder': 'minih264 speed 8',
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'duration': duration, 'label_burned': 'Recorded run'}


async def verify_clip(segment, duration):
    """Decode and seek the actual H.264 file in the installed kiosk engine."""
    async with async_playwright() as playwright:
        browser = await launch_browser(playwright)
        try:
            page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
            await page.goto('http://127.0.0.1:18808/stage/keys')
            proof = await page.evaluate('''async ({segment,duration}) => {
              const v=document.createElement('video');v.muted=true;v.controls=true;
              document.body.replaceChildren(v);Object.assign(v.style,{width:'100vw',height:'100vh',position:'fixed',inset:'0',background:'#0a0d14'});v.src='/stage/backup/'+segment+'.mp4';
              const wait=(name)=>new Promise((resolve,reject)=>{
                const timer=setTimeout(()=>reject(Error(name+' timed out')),15000);
                v.addEventListener(name,()=>{clearTimeout(timer);resolve();},{once:true});
                v.addEventListener('error',()=>reject(Error('Video decode failed')),{once:true});});
              let ready=wait('loadeddata');v.load();await ready;
              const width=v.videoWidth,height=v.videoHeight,seconds=v.duration;
              if(width!==1920||height!==1080||Math.abs(seconds-duration)>.2)throw Error('Invalid backup geometry or duration');
              let seeked=wait('seeked');v.currentTime=duration/2;await seeked;
              const frame=new Promise(resolve=>v.requestVideoFrameCallback((_,m)=>resolve(m.mediaTime)));
              await v.play();const mediaTime=await frame;v.pause();
              if(Math.abs(mediaTime-duration/2)>.2)throw Error('Backup seek failed');
              return {decode:true,width,height,duration:seconds,seek_media_time:mediaTime,decoded_frames:v.getVideoPlaybackQuality().totalVideoFrames};
            }''', {'segment': segment, 'duration': duration})
            await page.screenshot(path=str(OUTPUT / (segment + '-decode.png')))
            return proof
        finally:
            await browser.close()


async def main():
    if not ENCODER.exists():
        raise RuntimeError('The local recorder is missing. Run ops/build-gb10-codecs.py while preparing the offline build.')
    async with async_playwright() as playwright, httpx.AsyncClient(trust_env=False, timeout=10) as client:
        browser = await playwright.chromium.connect_over_cdp('http://127.0.0.1:18810')
        page = browser.contexts[0].pages[0]
        async def state():
            response = await client.get('http://127.0.0.1:18808/stage/api/state')
            response.raise_for_status()
            return response.json()
        deadline = time.monotonic() + 600
        while not (snapshot := await state())['readiness']['ready']:
            if snapshot['warm_error'] or time.monotonic() > deadline:
                raise RuntimeError(snapshot['warm_error'] or 'Recording readiness timed out')
            await asyncio.sleep(1)
        if await page.evaluate('innerWidth!==1920 || innerHeight!==1080'):
            raise RuntimeError('Backups require a native 1920x1080 kiosk')
        marker_wall = await page.evaluate('''() => {const mark=document.createElement('div');mark.id='capture-marker';Object.assign(mark.style,{position:'fixed',left:'0',top:'0',width:'32px',height:'32px',background:'white',zIndex:'9999'});document.body.append(mark);return Date.now()/1000;}''')
        await asyncio.sleep(1)
        await page.evaluate("document.querySelector('#capture-marker').remove()")
        segments = []
        for number, (segment, duration) in enumerate([('S0', 40), ('S1', 110), ('S2', 50), ('S3', 77), ('S4', 40)]):
            await page.keyboard.press(['ArrowRight', 'PageDown', ' ', 'Enter', 'ArrowRight'][number])
            started = time.monotonic()
            while True:
                snapshot = await state()
                row = snapshot['run']
                if snapshot['beat'] != segment or not row:
                    raise RuntimeError('Recording advanced to an unexpected beat')
                if row.get('backup') or row.get('recording_error') or row['status'] == 'failed':
                    raise RuntimeError('A live recording failed; no replacement footage will be accepted')
                if row['status'] == 'complete' and time.monotonic() - started >= duration:
                    break
                if time.monotonic() - started > max(duration + 10, 95):
                    raise RuntimeError('Live recording deadline exceeded')
                await asyncio.sleep(.2)
            segments.append({'segment': segment, 'started': row['started'], 'duration': duration,
                             'live_seconds': row['ended'] - row['started']})
            print('Recorded actual', segment, 'live seconds', segments[-1]['live_seconds'], flush=True)
        evidence = {'build': snapshot['build'], 'marker_wall': marker_wall, 'segments': segments}
        full_build = (await client.get('http://127.0.0.1:18808/health')).json()['build']
        evidence['build'] = full_build
        (OUTPUT / 'capture-evidence.json').write_text(json.dumps(evidence, indent=2))
    # A process-group SIGTERM also kills the recorder's Node/FFmpeg children
    # before Chromium can flush its queued frames. Close the owned context
    # first, then let the verified controller clean up the exited identity.
    sys.path.insert(0, str(ROOT / 'ops'))
    import control
    owned = control.discover('kiosk')
    if not owned or not control.identity(control.process(owned['pid']), 'kiosk'):
        raise RuntimeError('Cannot close an unverified kiosk')
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        response = await client.post('http://127.0.0.1:18809/stop')
        response.raise_for_status()
    deadline = time.monotonic() + 45
    while control.unchanged(control.fingerprint(owned)):
        if time.monotonic() > deadline:
            raise RuntimeError('Native kiosk did not finish flushing its real recording')
        await asyncio.sleep(.1)
    subprocess.run([sys.executable, 'ops/control.py', 'stop', 'kiosk'], cwd=ROOT, check=True)
    video = Path(json.loads((OUTPUT / 'raw-video.json').read_text())['path'])
    epoch = capture_start(video, marker_wall)
    for segment in segments:
        meta = await asyncio.to_thread(encode, video, segment['segment'], segment['started'] - epoch,
                                      segment['duration'], full_build)
        meta['verified'] = await verify_clip(segment['segment'], segment['duration'])
        path = OUTPUT / (segment['segment'] + '.json')
        path.write_text(json.dumps({**meta, 'live_seconds': segment['live_seconds']}, indent=2))
        print('Encoded H.264', segment['segment'], flush=True)


if __name__ == '__main__':
    asyncio.run(main())
