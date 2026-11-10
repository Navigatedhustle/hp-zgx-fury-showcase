"""Existing local Kokoro service with GB10 stage control protections."""
import os
import asyncio
from contextlib import asynccontextmanager

if os.getenv('FURY_PROFILE') != 'gb10':
    raise RuntimeError('This service requires the GB10 profile')

from atlas.tts_server import app
from atlas import tts_server
from showcase_app.gb10_security import StageRequestGuard
from showcase_app.gb10_memory import release_unused_buffers

cleanup = {}


@asynccontextmanager
async def lifespan(app):
    device = os.getenv('FURY_GB10_VOICE_DEVICE', 'cuda')
    if device not in ('cuda', 'cpu'):
        raise RuntimeError('Unsupported Kokoro device; no substitution made')
    await asyncio.to_thread(tts_server.load, device)
    cleanup['device'] = device
    cleanup['startup'] = await asyncio.to_thread(release_unused_buffers)
    cleanup['parameters'] = sum(p.numel() for p in tts_server.model.parameters())
    yield


app.router.lifespan_context = lifespan


@app.middleware('http')
async def release_after_speech(request, call_next):
    response = await call_next(request)
    if request.method == 'POST' and request.url.path == '/v1/audio/speech':
        async with tts_server.lock:
            cleanup['last_speech'] = await asyncio.to_thread(release_unused_buffers)
    return response


@app.get('/gb10/memory')
async def memory():
    return cleanup

app.add_middleware(StageRequestGuard, limit=8192)

# The shared service defaults to CUDA; the GB10 endpoint reports actual placement.
app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', '') != '/v1/models']


@app.get('/v1/models')
async def actual_models():
    return {'data': [{'id': 'Kokoro-82M', 'device': cleanup.get('device'),
                      'parameters': cleanup.get('parameters'), 'capability': 'speech'}]}
