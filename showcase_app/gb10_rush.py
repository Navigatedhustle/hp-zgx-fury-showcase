"""Actual six-job Nano Rush; the same jobs are used by qualification and the stage."""
import asyncio
import base64
import json
import logging
import re
import time
from pathlib import Path

import httpx

from showcase_app.gb10_agent import ACCOUNT, FILES, ROOT, image_job, object_schema
from showcase_app.gb10_client import LEAD, WORKER, infer, json_content
from showcase_app.gb10_miniapp import validate_app
from showcase_app.gb10_image_policy import RUSH_PROMPT

VOICE_LINE = 'Six jobs, four models, one Nano. Everything ran locally.'
APP_PROMPT = '''Write a complete self-contained HTML ROI calculator using only semantic HTML controls and inline vanilla JavaScript. The host adds the trusted stage layout, labels and styling: do not generate CSS, decorative markup, headers, frameworks or external resources. Keep the whole HTML under1200 characters. Include numeric inputs with ids hourly (default75), hours (default20), cost (default500); button id calculate; outputs id net and id roi. net=hourly*hours-cost. roi=net/cost*100 with percent, or N/A when cost is zero. Calculate on load and on button click using the current inputs. Direct arithmetic only, no eval. Label assumptions fictional, source date2026-11-08. Return JSON with one key html containing the entire working file. No Markdown.'''


class NanoRush:
    def __init__(self, run_id, *, purpose='live', audio=False, emit=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id):
            raise ValueError('Invalid run identity')
        self.run_id = run_id
        self.purpose = purpose
        self.audio = audio
        self.emit = emit or (lambda event: None)
        self.folder = ROOT / 'state/stage/outputs' / run_id / 'S3'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.context = '\n\n'.join((ACCOUNT / name).read_text() for name in FILES)
        self.jobs = {}

    def event(self, kind, **data):
        self.emit({'kind': kind, 'at': time.time(), **data})

    async def language(self, messages, *, role, model=WORKER, tokens=1500, caller='rush', **options):
        return await infer(messages, model=model, caller=caller, run_id=self.run_id, purpose=self.purpose,
                           role=role, max_tokens=tokens, call_id=self.run_id + '_' + role, **options)

    async def risks(self):
        result = await self.language([{'role': 'system', 'content': 'Give exactly three short account risks grounded in these fictional notes. No new facts or legal claims.'},
                                     {'role': 'user', 'content': self.context + '\nWhat are the top three risks for this account?'}], role='risks', model=LEAD, tokens=260)
        if result['finish_reason'] != 'stop':
            raise ValueError('Risk readout was incomplete')
        (self.folder / 'risks.txt').write_text(result['content'])
        return {'text': result['content'], 'model': result['model'], 'routing': result['routing']}

    async def app(self):
        result = await self.language([{'role': 'user', 'content': APP_PROMPT}], role='app', tokens=900,
            response_format={'type': 'json_schema', 'json_schema': {'name': 'roi_app', 'strict': True,
                'schema': object_schema({'html': {'type': 'string', 'minLength': 50, 'maxLength': 65536}})}})
        if result['finish_reason'] != 'stop':
            raise ValueError('Generated app was incomplete')
        source = json_content(result['content'])['html']
        (self.folder / 'calculator-candidate.txt').write_text(source)
        self.event('app_validating')
        checked = await asyncio.wait_for(validate_app(source, self.folder), 18)
        return {**checked, 'model': result['model'], 'routing': result['routing']}

    async def images(self):
        return await image_job(RUSH_PROMPT,
            self.run_id, self.purpose, batch=4, width=1024, height=576, on_update=lambda job: self.event('images_progress', job=job))

    async def chart(self):
        image = base64.b64encode((ROOT / 'samples/stage/vision/chart.png').read_bytes()).decode()
        schema = object_schema({'columns': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 3, 'maxItems': 3},
            'rows': {'type': 'array', 'minItems': 4, 'maxItems': 4, 'items': {'type': 'array', 'minItems': 3, 'maxItems': 3,
                'items': {'anyOf': [{'type': 'string'}, {'type': 'number'}]}}}})
        result = await self.language([{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image}},
            {'type': 'text', 'text': 'Extract the entire chart as JSON with columns and rows. Use positional row arrays, preserve every label and numeric value, and include no other text.'}]}], role='chart', tokens=600,
            response_format={'type': 'json_schema', 'json_schema': {'name': 'chart_table', 'strict': True, 'schema': schema}})
        table = json_content(result['content'])
        (self.folder / 'chart-candidate.json').write_text(json.dumps(table, ensure_ascii=False, indent=2))
        from showcase_app.gb10_quality import extraction_matches
        expected = json.loads((ROOT / 'samples/stage/vision/expected.json').read_text())['chart.png']
        if result['finish_reason'] != 'stop' or not extraction_matches('chart.png', table, expected):
            raise ValueError('Chart extraction did not match all visible data')
        (self.folder / 'chart.json').write_text(json.dumps(table, ensure_ascii=False, indent=2))
        from showcase_app.gb10_accounting import validated_counts
        validated_counts(result['call_id'], images_analyzed=1)
        return {'table': table, 'model': result['model']}

    async def translate(self):
        pages = (ROOT / 'samples/stage/translation/two_pages.txt').read_text().split('--- PAGE BREAK ---')
        schema = object_schema({'pages': {'type': 'array', 'items': {'type': 'string', 'minLength': 30}, 'minItems': 2, 'maxItems': 2}})

        async def language(name, code):
            messages = [{'role': 'system', 'content': 'Translate both fictional document pages into ' + name + '. Return JSON with a pages array containing both complete translated pages. Preserve page boundaries, every number, the literal ISO date 2026-11-08, and the Latin proper name Northwind. Translate every ordinary English word into the requested language, with fluent native phrasing. In Japanese only Northwind should remain in Latin letters. No commentary or omissions.'},
                {'role': 'user', 'content': json.dumps({'pages': pages}, ensure_ascii=False)}]
            for attempt in range(2):
                result = await self.language(messages, role='translate_' + code + ('_retry' if attempt else ''), caller='translate', tokens=2300,
                    response_format={'type': 'json_schema', 'json_schema': {'name': 'translated_pages', 'strict': True, 'schema': schema}})
                if result['finish_reason'] != 'stop':
                    raise ValueError('Document translation was incomplete')
                data = json_content(result['content'])
                from jsonschema import validate
                validate(data, schema)
                for source, target in zip(pages, data['pages']):
                    if not set(re.findall(r'\d+', source)) <= set(re.findall(r'\d+', target)):
                        raise ValueError('Translated page lost a source number or date')
                untranslated = set(re.findall(r'[A-Za-z]+', '\n'.join(data['pages']))) - {'Northwind'} if code == 'ja' else set()
                if not untranslated:
                    from showcase_app.gb10_accounting import validated_counts
                    validated_counts(result['call_id'], pages=2)
                    (self.folder / ('document-' + code + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2))
                    return data['pages']
                (self.folder / ('document-' + code + '-rejected.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2))
                self.event('translation_retry', language=code, attempt=attempt + 1, reason='Ordinary English text remained untranslated')
                messages += [{'role': 'assistant', 'content': result['content']}, {'role': 'user', 'content': 'Some ordinary English words remained untranslated: ' + ', '.join(sorted(untranslated)) + '. Translate those words too. Return both complete corrected pages in the same JSON structure.'}]
            raise ValueError('Japanese document still contains untranslated ordinary English text')

        spanish, japanese = await asyncio.gather(language('Spanish', 'es'), language('Japanese', 'ja'))
        return {'languages': ['es', 'ja'], 'pages': 4, 'spanish': spanish, 'japanese': japanese, 'model': WORKER}

    async def voice_or_summary(self):
        if self.audio:
            async with httpx.AsyncClient(trust_env=False, timeout=12) as client:
                response = await client.post('http://127.0.0.1:18204/v1/audio/speech', json={'input': VOICE_LINE, 'voice': 'am_michael'})
                response.raise_for_status()
                (self.folder / 'voice.pcm').write_bytes(response.content)
            return {'file': 'voice.pcm', 'pcm_bytes': len(response.content), 'model': 'Kokoro-82M'}
        result = await self.language([{'role': 'system', 'content': 'Write one short paragraph summarizing this fictional local planning pilot. No invented statistics or claims.'},
                                     {'role': 'user', 'content': self.context}], role='summary', tokens=180)
        return {'text': result['content'], 'model': result['model']}

    async def job(self, name, function):
        row = {'name': name, 'status': 'queued', 'created': time.time()}
        self.jobs[name] = row
        self.event('job', job=dict(row))
        began = time.monotonic()
        try:
            row.update(status='running', started=time.time())
            self.event('job', job=dict(row))
            result = await function()
            row.update(status='complete', seconds=time.monotonic() - began, result=result)
        except Exception as exc:
            logging.exception('Nano Rush job failed name=%s', name)
            row.update(status='failed', seconds=time.monotonic() - began, error=type(exc).__name__)
        self.event('job', job=dict(row))

    async def run(self):
        began = time.monotonic()
        await asyncio.gather(*(self.job(name, function) for name, function in [
            ('risks', self.risks), ('app', self.app), ('images', self.images), ('chart', self.chart),
            ('translation', self.translate), ('voice' if self.audio else 'summary', self.voice_or_summary)]))
        result = {'seconds': time.monotonic() - began, 'done': sum(job['status'] == 'complete' for job in self.jobs.values()), 'jobs': self.jobs}
        (self.folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result
