"""V3-style interactive hub sharing the stage process and resident Nano models."""
import asyncio
import base64
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
from typing import Literal
import uuid
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from showcase_app.gb10_agent import ROOT
from showcase_app.free_mode_tools import TOOLS, LANGUAGES
from showcase_app.free_mode_deck import Deck, export_deck

CATALOG = [
    {'id': 'atlas', 'name': 'Atlas', 'tag': 'Account intelligence', 'model': 'gpt-oss-120b',
     'description': 'Ask, reason and follow up with grounded fictional account notes.', 'mark': 'A',
     'prompt': 'What are the top three risks for Northwind and what should I discuss with the CIO?'},
    {'id': 'slides', 'name': 'Presentations', 'tag': 'Brief to boardroom', 'model': 'Qwen3.6-35B-A3B',
     'description': 'Turn a brief into a presentation. Edit the copy and export PowerPoint.', 'mark': 'P',
     'prompt': 'Create a three-slide executive proposal for a fictional local AI pilot: evaluate document summarization, translation and image review; run a four-week trial; measure review time and output quality. No assumed savings or performance claims.'},
    {'id': 'factory', 'name': 'Agent Factory', 'tag': 'Build something useful', 'model': 'gpt-oss + Qwen',
     'description': 'Plan and build an interactive browser app with live preview and source.', 'mark': 'F',
     'prompt': 'Build a polished ROI calculator with hourly rate, hours saved per month, and monthly cost. Show net monthly value = rate * hours - cost and ROI = net / cost * 100. Handle zero cost. Label inputs fictional.'},
    {'id': 'images', 'name': 'Image Studio', 'tag': 'Imagine in materials', 'model': 'FLUX.2 klein 4B',
     'description': 'Create original artwork with your own prompt, style, size and seed.', 'mark': 'I',
     'prompt': 'A sculptural cobalt aluminum ribbon resting on an obsidian plinth in a dark architectural studio, refined reflections and confident negative space.'},
    {'id': 'vision', 'name': 'Vision Lab', 'tag': 'From image to insight', 'model': 'Qwen3.6 vision',
     'description': 'Inspect a whiteboard, chart or public sample and extract its details.', 'mark': 'V',
     'prompt': 'Read this image carefully. Extract the visible text and numbers, then summarize the key takeaways.'},
    {'id': 'translate', 'name': 'Translate Desk', 'tag': 'Work across languages', 'model': 'Qwen3.6-35B-A3B',
     'description': 'Translate text or documents into 34 languages with page-aware exports.', 'mark': 'T',
     'prompt': 'Northwind will evaluate 12 workstations during a 4-week pilot beginning 2026-11-08. The team will review document summaries, translated drafts and image extraction results. All inputs are fictional.'},
    {'id': 'voice', 'name': 'Voice Studio', 'tag': 'Give your words a voice', 'model': 'Kokoro 82M',
     'description': 'Turn short English narration into a local voice recording.', 'mark': 'S',
     'prompt': 'Welcome to HP ZGX Nano. Explore local intelligence, create something new, and see the work happen right here.'},
]
STATIC = ROOT / 'showcase_app/free_mode'
ACTIVE = ('queued', 'running', 'cancelling')
ID = r'[a-f0-9]{32}'


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=9000)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    demo: Literal['atlas', 'slides', 'factory', 'images', 'vision', 'translate', 'voice']
    prompt: str = Field(min_length=3, max_length=9000)
    history: list[Message] = Field(default_factory=list, max_length=8)
    slide_count: int = Field(default=3, ge=3, le=8)
    language: str = 'Spanish'
    sample: Literal['whiteboard.png', 'chart.png', ''] = 'whiteboard.png'
    image_base64: str = Field(default='', max_length=700000)
    batch: Literal[1, 2, 4] = 1
    width: Literal[1024, 1344] = 1024
    height: Literal[576, 768] = 576
    seed: int = Field(default=42, ge=0, le=4294967295)
    style: Literal['Studio', 'Photographic', 'Architectural', 'Illustration', 'Cinematic'] = 'Studio'
    voice: Literal['af_heart', 'am_michael'] = 'am_michael'

    @model_validator(mode='after')
    def bounds(self):
        if self.language not in LANGUAGES:
            raise ValueError('Choose a supported language')
        if (self.width, self.height) not in ((1024, 576), (1344, 768)):
            raise ValueError('Choose a supported image size')
        if len(self.prompt) + sum(len(row.content) for row in self.history) > 22000:
            raise ValueError('The conversation is too long. Start a new conversation.')
        if self.demo == 'voice' and len(self.prompt) > 900:
            raise ValueError('Keep English narration below 900 characters')
        if self.demo == 'images' and len(self.prompt) > 1500:
            raise ValueError('Keep image prompts below 1500 characters')
        if self.demo == 'vision' and not self.sample and not self.image_base64:
            raise ValueError('Choose a sample or provide a public demonstration image')
        return self


class Upload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1, max_length=700000)


def extract_document(upload):
    try:
        raw = base64.b64decode(upload.content_base64, validate=True)
        suffix = Path(upload.filename).suffix.lower()
        if suffix == '.txt':
            text = raw.decode('utf-8-sig')
        elif suffix == '.docx':
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(row.file_size for row in archive.infolist()) > 3_000_000:
                    raise ValueError('This document is too large after decompression')
            from docx import Document
            document = Document(io.BytesIO(raw))
            text = '\n'.join(p.text for p in document.paragraphs)
            for table in document.tables:
                text += '\n' + '\n'.join(' | '.join(c.text for c in row.cells) for row in table.rows)
        elif suffix == '.pdf':
            from pypdf import PdfReader
            document = PdfReader(io.BytesIO(raw))
            if document.is_encrypted or len(document.pages) > 4:
                raise ValueError('Use an unencrypted PDF of at most four pages')
            # Bound content streams before text parsing; scanned PDFs need OCR.
            pages = []
            for page in document.pages:
                contents = page.get_contents()
                if contents and len(contents.get_data()) > 2_000_000:
                    raise ValueError('This PDF page is too complex; use a text document')
                pages.append(page.extract_text() or '')
            if any(not page.strip() for page in pages):
                raise ValueError('Scanned or empty PDF pages need OCR. Use Vision Lab for an image.')
            text = '\f'.join(pages)
        else:
            raise ValueError('Use TXT, DOCX or a text PDF')
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('The document could not be read. Use UTF-8 TXT, DOCX or a text PDF.') from exc
    if not 3 <= len(text.strip()) <= 9000:
        raise ValueError('Use a document containing 3–9000 characters of readable text')
    return text


class FreeMode:
    def __init__(self, show, storage=None):
        self.show = show
        self.active = os.getenv('FURY_FREE_MODE') == '1'
        self.storage = storage or ROOT / 'state/free-mode'
        self.storage.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.jobs = {}
        self.tasks = {}
        self.slots = asyncio.Semaphore(3)
        self.voice_slot = asyncio.Semaphore(1)
        self.session = 'free_' + uuid.uuid4().hex
        self.editing = set()
        self.switching = False
        self.load()

    def load(self):
        for path in sorted(self.storage.glob('*/job.json'), key=lambda p: p.stat().st_mtime)[-50:]:
            if not re.fullmatch(ID, path.parent.name):
                continue
            try:
                row = json.loads(path.read_text())
                if row['id'] != path.parent.name or row['demo'] not in TOOLS:
                    continue
                if row['status'] in ACTIVE:
                    row.update(status='interrupted', error='The service restarted. Run this experience again.', ended=time.time())
                self.jobs[row['id']] = row
            except (OSError, ValueError, KeyError):
                continue

    def save(self, job):
        folder = self.folder(job['id'])
        temporary = folder / 'job.json.tmp'
        temporary.write_text(json.dumps(job, ensure_ascii=False))
        temporary.replace(folder / 'job.json')

    def folder(self, cid):
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, 'Unknown job')
        return self.storage / cid

    def job(self, cid):
        if cid not in self.jobs:
            raise HTTPException(404, 'Unknown job')
        return self.jobs[cid]

    def busy(self):
        return bool(self.editing) or any(row['status'] in ACTIVE for row in self.jobs.values())

    def available(self):
        if not self.active or self.switching:
            raise HTTPException(409, 'Switch to Free Mode before starting an experience')
        if self.show.resetting or (self.show.task and not self.show.task.done()) or (self.show.warm_task and not self.show.warm_task.done()):
            raise HTTPException(409, 'Presenter work is still running. Wait for it to finish.')
        if not all(self.show.health.get(name, {}).get('ready') for name in ('lead', 'text', 'image', 'tts', 'gateway')):
            raise HTTPException(503, 'Local models are starting or unavailable. Check model status.')
        from showcase_app.stage_common import memory
        if memory()['available'] < 5 * 2**30 or shutil.disk_usage(self.storage).free < 5 * 2**30:
            raise HTTPException(503, 'Free Mode needs at least 5 GiB available memory and disk space')

    async def set_mode(self, free):
        if self.switching:
            raise HTTPException(409, 'A mode switch is already running')
        if self.active == free:
            return
        if self.busy() or self.show.resetting or self.show.pending or getattr(self.show, 'maintenance', False) or (self.show.task and not self.show.task.done()) or (self.show.warm_task and not self.show.warm_task.done()):
            raise HTTPException(409, 'Wait for current work to finish or cancel it before switching modes')
        if free and self.show.view != -1:
            raise HTTPException(409, 'Reset the presenter show before entering Free Mode')
        # Claim ownership before the health probe yields to other requests.
        self.switching = True
        try:
            health = await self.show.fetch_health()
            if any(health.get(name, {}).get('active') or health.get(name, {}).get('queued') for name in ('gateway', 'image', 'tts')):
                raise HTTPException(409, 'The local lanes are still draining. Wait a moment before switching modes.')
            self.active = free
            self.show.keepalive_at = time.monotonic()
            if not free:
                # Arbitrary prompts change caches. Rehearse the exact show again.
                self.show.warm = self.show.full_warm_complete = False
                self.show.warm_task = asyncio.create_task(self.show.warmup())
        finally:
            self.switching = False

    def submit(self, specs):
        self.available()
        if len(specs) + sum(row['status'] in ACTIVE for row in self.jobs.values()) > 12:
            raise HTTPException(429, 'The Nano queue is full. Wait for a job to finish.')
        # Prune only finished work; never remove active outputs.
        finished = sorted((row for row in self.jobs.values() if row['status'] not in ACTIVE), key=lambda row: row['created'])
        while len(self.jobs) + len(specs) > 50 and finished:
            row = finished.pop(0)
            if row['id'] in self.editing:
                continue
            shutil.rmtree(self.folder(row['id']))
            self.jobs.pop(row['id'])
        result = []
        for spec in specs:
            cid = uuid.uuid4().hex
            folder = self.folder(cid)
            folder.mkdir(mode=0o700)
            row = {'id': cid, 'run_id': self.session + '_' + cid, 'demo': spec.demo, 'status': 'queued',
                   'created': time.time(), 'phase': 'Queued', 'prompt': spec.prompt, 'calls': []}
            self.jobs[cid] = row
            self.save(row)
            self.tasks[cid] = asyncio.create_task(self.execute(row, spec))
            result.append(dict(row))
        return result

    async def execute(self, job, spec):
        try:
            # Voice doesn't occupy a language slot, so Rush can't starve speech.
            async with self.voice_slot if spec.demo == 'voice' else self.slots:
                job.update(status='running', started=time.time())
                self.save(job)
                async with asyncio.timeout(420):
                    job['result'] = await TOOLS[spec.demo](job, spec, self, self.folder(job['id']))
                job.update(status='complete', phase='Complete')
        except asyncio.CancelledError:
            job.update(status='cancelled', phase='Cancelled')
        except Exception as exc:
            logging.error('Free Mode job failed demo=%s id=%s type=%s', spec.demo, job['id'], type(exc).__name__)
            error = str(exc) if isinstance(exc, ValueError) else 'The local job could not finish. Check model status and try again.'
            job.update(status='failed', phase='Failed', error=error)
        finally:
            job.pop('partial', None)
            job['ended'] = time.time()
            self.save(job)
            self.tasks.pop(job['id'], None)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for cid in list(self.tasks):
            row = self.jobs[cid]
            row.update(status='interrupted', phase='Interrupted', ended=time.time())
            self.save(row)
            self.tasks.pop(cid, None)

    def totals(self):
        path = ROOT / 'state/stage/usage.sqlite'
        if not path.exists():
            return {}
        with sqlite3.connect(path, timeout=2) as db:
            row = db.execute("SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(images),0), COALESCE(SUM(pages),0), COALESCE(SUM(images_analyzed),0) FROM events WHERE run_id LIKE ? AND status='complete' AND purpose='live'", (self.session + '%',)).fetchone()
        return dict(zip(('input_tokens', 'output_tokens', 'images', 'pages', 'images_analyzed'), row))


def create_router(show):
    manager = FreeMode(show)
    router = APIRouter()

    @router.get('/')
    async def home():
        return RedirectResponse('/free' if manager.active else '/stage', status_code=307)

    @router.get('/free')
    @router.get('/free/{demo}')
    async def page(demo: str = ''):
        if demo and demo not in (*TOOLS, 'jobs', 'models'):
            raise HTTPException(404)
        return FileResponse(STATIC / 'index.html')

    @router.get('/free/assets/{name}')
    async def asset(name: str):
        if name not in ('free.css', 'free.js'):
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @router.get('/free/api/state')
    async def state():
        return {'mode': 'free' if manager.active else 'presenter', 'catalog': CATALOG, 'languages': LANGUAGES,
                'jobs': sorted(manager.jobs.values(), key=lambda row: row['created'], reverse=True),
                'health': show.health, 'telemetry': {key: show.telemetry.get(key) for key in ('gpu', 'available', 'total', 'external_calls', 'clock')},
                'totals': manager.totals(), 'warming': bool(show.warm_task and not show.warm_task.done()),
                'excluded': [{'name': 'Video Studio', 'reason': 'The Nano profile has no video model loaded.'},
                             {'name': 'Action Trailer', 'reason': 'Requires the video pipeline and consented camera workflow.'}]}

    class Mode(BaseModel):
        mode: Literal['free', 'presenter']

    @router.post('/free/api/mode')
    async def mode(value: Mode):
        await manager.set_mode(value.mode == 'free')
        return {'mode': value.mode}

    @router.post('/free/api/jobs', status_code=202)
    async def submit(spec: JobRequest):
        return manager.submit([spec])[0]

    @router.post('/free/api/rush', status_code=202)
    async def rush(specs: list[JobRequest]):
        if len(specs) != 6 or {spec.demo for spec in specs} != {'atlas', 'slides', 'factory', 'images', 'vision', 'translate'}:
            raise HTTPException(422, 'Rush requires one of each of the six original Nano experiences')
        return {'jobs': manager.submit(specs)}

    @router.get('/free/api/jobs/{cid}')
    async def job(cid: str):
        return manager.job(cid)

    @router.post('/free/api/jobs/{cid}/cancel')
    async def cancel(cid: str):
        row = manager.job(cid)
        task = manager.tasks.get(cid)
        if task and not task.done():
            row['status'] = 'cancelling'
            task.cancel()
            # Keep it active until the downstream cancellation has drained.
            await asyncio.gather(task, return_exceptions=True)
            if row['status'] in ACTIVE:
                row.update(status='cancelled', phase='Cancelled', ended=time.time())
                manager.save(row)
                manager.tasks.pop(cid, None)
        return row

    @router.delete('/free/api/jobs/{cid}')
    async def delete(cid: str):
        row = manager.job(cid)
        if row['status'] in ACTIVE or cid in manager.editing:
            raise HTTPException(409, 'Cancel the job and wait for it to stop before deleting')
        shutil.rmtree(manager.folder(cid))
        manager.jobs.pop(cid)
        return {'deleted': True}

    @router.put('/free/api/jobs/{cid}/deck')
    async def edit_deck(cid: str, deck: Deck):
        row = manager.job(cid)
        if row['demo'] != 'slides' or row['status'] != 'complete' or cid in manager.editing:
            raise HTTPException(409, 'Wait for the presentation to finish before editing')
        if not manager.active or manager.switching:
            raise HTTPException(409, 'Enter Free Mode before editing the deck')
        manager.editing.add(cid)
        candidate = manager.folder(cid) / 'revision'
        try:
            candidate.mkdir(exist_ok=True)
            updated = await asyncio.to_thread(export_deck, deck.model_dump(), candidate)
            for name in updated['files']:
                (candidate / name).replace(manager.folder(cid) / name)
            row['result'] = updated
            row['revision'] = time.time_ns()
            manager.save(row)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            shutil.rmtree(candidate, ignore_errors=True)
            manager.editing.remove(cid)
        return row

    @router.post('/free/api/document')
    async def document(upload: Upload):
        try:
            text = await asyncio.to_thread(extract_document, upload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'text': text, 'filename': Path(upload.filename).name}

    @router.get('/free/files/{cid}/{name}')
    async def artifact(cid: str, name: str, download: bool = False):
        row = manager.job(cid)
        result = row.get('result', {})
        allowed = set(result.get('files', [])) | set(result.get('previews', []))
        if result.get('input'):
            allowed.add(result['input'])
        if row['status'] != 'complete' or name not in allowed or not re.fullmatch(r'[a-zA-Z0-9_.-]+', name):
            raise HTTPException(404, 'Artifact unavailable')
        path = manager.folder(cid) / name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404)
        return FileResponse(path, filename=name if download else None, content_disposition_type='attachment' if download else 'inline')

    return router, manager
