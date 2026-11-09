"""Bounded GB10 image API using the existing CreativeLane; no video pipeline."""
import asyncio
import os
import threading
import time
import uuid
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build/sources/atlas-gpt-main'))
from atlas.offline_guard import install

install()
from showcase_app.creative import CreativeLane
from showcase_app.gateway import execution_end, execution_start, record

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'state/stage/creative'
lane = CreativeLane()
queue = asyncio.Queue(maxsize=3)
jobs = {}


async def work():
    while True:
        job, spec = await queue.get()
        began = time.time()
        try:
            job.update(status='running', started=began)
            execution_start(job['id'], 'stage_image', 'FLUX.2-klein-4B')
            path = OUTPUT / (job['id'] + '.png')
            metrics = await asyncio.to_thread(lane.run, 'image', spec.prompt, path, job['_stop'],
                {'width': spec.width, 'height': spec.height, 'batch': spec.batch, 'seed': spec.seed}, job)
            job.update(status='complete', ended=time.time(), **metrics)
            files = [path.name] if spec.batch == 1 else [path.with_stem(path.stem + '-' + str(i)).name for i in range(1, spec.batch + 1)]
            if not all((OUTPUT / name).is_file() for name in files):
                raise RuntimeError('Image worker did not produce all requested artifacts')
            job['files'] = files
            record(job['id'], 'stage_image', 'image', 'FLUX.2-klein-4B', 'complete', began,
                   run_id=spec.run_id, purpose=spec.purpose, images=len(files))
        except Exception as exc:
            logging.exception('GB10 image job failed id=%s', job['id'])
            job.update(status='failed', error=type(exc).__name__, ended=time.time())
            record(job['id'], 'stage_image', 'image', 'FLUX.2-klein-4B', 'failed', began,
                   error=type(exc).__name__, run_id=spec.run_id, purpose=spec.purpose)
        finally:
            execution_end(job['id'], job['status'])
            queue.task_done()


@asynccontextmanager
async def lifespan(app):
    if os.getenv('FURY_PROFILE') != 'gb10':
        raise RuntimeError('This API requires the GB10 profile')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(lane.load)
    task = asyncio.create_task(work())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
from showcase_app.gb10_security import StageRequestGuard
app.add_middleware(StageRequestGuard, limit=32768)


class ImageRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    prompt: str = Field(min_length=5, max_length=1500)
    width: Literal[1024, 1344] = 1024
    height: Literal[576, 768] = 576
    batch: Literal[1, 4] = 1
    seed: int = Field(default=42, ge=0, le=4294967295)
    run_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    purpose: Literal['live', 'warmup'] = 'live'


def public(job):
    return {key: value for key, value in job.items() if not key.startswith('_')}


@app.get('/health')
async def health():
    return {'ready': lane.flux is not None, 'model': 'FLUX.2-klein-4B', 'placement': lane.placement(),
            'active': sum(job['status'] == 'running' for job in jobs.values()), 'queued': queue.qsize(), 'limit': 1,
            'parameter_count': getattr(lane, 'parameter_count', None), 'load_timings': getattr(lane, 'load_timings', {})}


@app.post('/generate')
async def generate(spec: ImageRequest, request: Request):
    if request.headers.get('origin') not in (None, 'http://127.0.0.1:18808', 'http://localhost:18808'):
        raise HTTPException(403, 'Only local stage origins are accepted')
    if (spec.width, spec.height) not in ((1024, 576), (1344, 768)):
        raise HTTPException(422, 'Unsupported stage image size')
    if queue.full():
        raise HTTPException(429, 'Local image queue is full')
    cid = uuid.uuid4().hex
    job = {'id': cid, 'status': 'queued', 'created': time.time(), 'model': 'FLUX.2-klein-4B',
           'batch': spec.batch, 'images_done': 0, '_stop': threading.Event()}
    jobs[cid] = job
    queue.put_nowait((job, spec))
    return public(job)


@app.get('/jobs/{cid}')
async def job(cid: str):
    if cid not in jobs:
        raise HTTPException(404, 'Unknown local image job')
    return public(jobs[cid])


@app.post('/jobs/{cid}/cancel')
async def cancel(cid: str, request: Request):
    if request.headers.get('origin') not in (None, 'http://127.0.0.1:18808', 'http://localhost:18808'):
        raise HTTPException(403, 'Only local stage origins are accepted')
    if cid not in jobs:
        raise HTTPException(404, 'Unknown local image job')
    jobs[cid]['_stop'].set()
    return {'cancel_requested': True}
