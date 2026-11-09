"""Bounded live agent used by GB10 qualification and the executive stage."""
import asyncio
import base64
import html
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
from jsonschema import validate

from showcase_app.gb10_client import LEAD, WORKER, infer, json_content

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = ROOT / 'samples/stage/account_northwind'
GOAL = 'I meet the CIO of Northwind Regional Health tomorrow. Read my account notes, build a five slide briefing, draft my follow up email with a Spanish version, and make a cover image.'
FILES = ('meeting_notes.txt', 'quarterly_review.txt', 'it_priorities.txt', 'product_interests.txt')
DELIVERABLES = ('deck', 'email_en', 'email_es', 'image')


def check_claims(value):
    text = json.dumps(value, ensure_ascii=False)
    if re.search(r'\b(?:HIPAA|GDPR|SOC\s*2|ISO\s*27001|compliant|compliance|certified|certification)\b', text, re.I):
        raise ValueError('Draft contains an unsupported compliance or certification statement')
    return value


def object_schema(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required, 'additionalProperties': False}


TEXT = lambda maximum: {'type': 'string', 'minLength': 1, 'maxLength': maximum}
TOOL_SCHEMAS = {
    'list_files': object_schema({}),
    'read_file': object_schema({'files': {'type': 'array', 'items': {'type': 'string', 'enum': list(FILES)}, 'minItems': 4, 'maxItems': 4, 'uniqueItems': True}}),
    'build_deck': object_schema({'brief': TEXT(2000)}),
    'generate_image': object_schema({'prompt': TEXT(1500)}),
    'draft_email': object_schema({'subject': TEXT(120), 'body': TEXT(2200)}),
    'translate': object_schema({'source': {'const': 'email-en'}, 'languages': {'type': 'array', 'items': {'const': 'es'}, 'minItems': 1, 'maxItems': 1}}),
    'speak_summary': object_schema({'text': TEXT(300)}),
}
PLAN_SCHEMA = object_schema({
    'steps': {'type': 'array', 'minItems': 4, 'maxItems': 8, 'items': object_schema({'tool': {'type': 'string', 'enum': list(TOOL_SCHEMAS)}, 'label': TEXT(80)})},
    'deliverables': {'type': 'array', 'items': {'type': 'string', 'enum': list(DELIVERABLES)}, 'minItems': 4, 'maxItems': 4, 'uniqueItems': True},
})
SLIDE_SCHEMA = object_schema({'title': TEXT(70), 'subtitle': TEXT(120),
    'points': {'type': 'array', 'minItems': 2, 'maxItems': 3, 'items': TEXT(150)}, 'notes': TEXT(300)})
DECK_SCHEMA = object_schema({'title': TEXT(90), 'slides': {'type': 'array', 'items': SLIDE_SCHEMA, 'minItems': 5, 'maxItems': 5}})


def validate_plan(plan, audio=False):
    validate(plan, PLAN_SCHEMA)
    check_claims(plan)
    names = {step['tool'] for step in plan['steps']}
    if not {'list_files', 'read_file', 'build_deck', 'draft_email', 'translate', 'generate_image'} <= names:
        raise ValueError('Plan does not cover all required artifacts')
    ordered = [step['tool'] for step in plan['steps']]
    if ordered[:2] != ['list_files', 'read_file']:
        raise ValueError('Plan must list and read the sample before authoring')
    if not audio and 'speak_summary' in names:
        raise ValueError('Audio is off')
    if set(plan['deliverables']) != set(DELIVERABLES):
        raise ValueError('Plan has incomplete deliverables')
    return plan


async def parallel_tools(agent, parsed):
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(agent.tool(name, arguments)) for name, arguments in parsed]
    return [task.result() for task in tasks]


class AccountJail:
    def __init__(self, root=ACCOUNT):
        self.root = Path(root).resolve(strict=True)

    def list_files(self):
        return [name for name in FILES if (self.root / name).is_file() and not (self.root / name).is_symlink()]

    def read_file(self, name):
        if name not in FILES or '/' in name or '\\' in name:
            raise ValueError('Only allowlisted sample files may be read')
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(descriptor, 'rb') as stream:
                data = stream.read(16385)
            if len(data) > 16384:
                raise ValueError('Sample file exceeds the read limit')
            return data.decode('utf-8')
        finally:
            os.close(directory)


async def image_job(prompt, run_id, purpose='live', *, batch=1, width=1344, height=768, on_update=None):
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        response = await client.post('http://127.0.0.1:18800/generate', json={
            'prompt': prompt, 'run_id': run_id, 'purpose': purpose, 'batch': batch, 'width': width, 'height': height, 'seed': 42})
        response.raise_for_status()
        job = response.json()
        try:
            while job['status'] not in ('complete', 'failed', 'cancelled'):
                if on_update:
                    on_update(job)
                await asyncio.sleep(.15)
                response = await client.get('http://127.0.0.1:18800/jobs/' + job['id'])
                response.raise_for_status()
                job = response.json()
            if job['status'] != 'complete':
                raise RuntimeError('Local image generation did not complete')
            return job
        except asyncio.CancelledError:
            await client.post('http://127.0.0.1:18800/jobs/' + job['id'] + '/cancel')
            raise


def write_deck(data, folder):
    """Use the existing Presentations assembler with five validated, escaped specs."""
    validate(data, DECK_SCHEMA)
    check_claims(data)
    sys.path.insert(0, str(ROOT / 'build/sources/html_builder-main/backend'))
    from app.assemble import DeckInput, DeckSlide, assemble
    from app.spec import SlideSpec, SpecMeta
    specs = []
    for index, slide in enumerate(data['slides'], 1):
        points = ''.join('<li>' + html.escape(point) + '</li>' for point in slide['points'])
        markup = '<section class="nano-deck"><p class="tag">HP ZGX NANO / ' + str(index) + '</p><h1>' + html.escape(slide['title']) + '</h1><p class="subtitle">' + html.escape(slide['subtitle']) + '</p><ul>' + points + '</ul><footer>Fictional account notes · source date 2026-11-08</footer></section>'
        css = '.nano-deck{height:100%;box-sizing:border-box;padding:68px 80px;background:#0A0D14;color:white;font-family:Arial,Helvetica,"Liberation Sans",sans-serif}.nano-deck h1{font-size:72px;color:#D1DDF1;border-bottom:3px solid #004BDF;padding-bottom:22px;margin:36px 0}.nano-deck .tag{font-size:28px;letter-spacing:3px;color:#73A1FF}.nano-deck .subtitle{font-size:36px;color:#D1DDF1}.nano-deck li{font-size:36px;line-height:1.4;margin:20px 0}.nano-deck footer{position:absolute;bottom:40px;font-size:28px;color:#B4C1D7}'
        spec = SlideSpec(meta=SpecMeta(title=slide['title'], theme='paper', notes=[slide['notes']],
                         sources='Original fictional sample account notes, 2026-11-08'), html=markup, css=css)
        specs.append(DeckSlide(id='nano-' + str(index), spec=spec))
    wordmark = folder / 'wordmark.svg'
    wordmark.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60"><text x="0" y="44" fill="#D1DDF1" font-family="Arial,Helvetica,sans-serif" font-size="38">HP ZGX Nano</text></svg>')
    document = assemble(DeckInput(title=data['title'], slides=specs, assets={'hp': wordmark}), embed=True, instant=True)
    (folder / 'briefing.html').write_text(document)
    (folder / 'briefing.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return {'file': 'briefing.html', 'data_file': 'briefing.json', 'title': data['title'], 'slides': data['slides']}


class NanoAgent:
    def __init__(self, run_id=None, *, purpose='live', audio=False, emit=None):
        if os.getenv('FURY_PROFILE') != 'gb10':
            raise RuntimeError('Nano agent requires the GB10 profile')
        self.run_id = run_id or uuid.uuid4().hex
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', self.run_id):
            raise ValueError('Invalid run identity')
        self.purpose = purpose
        self.audio = audio
        self.emit = emit or (lambda event: None)
        self.folder = ROOT / 'state/stage/outputs' / self.run_id / 'S1'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.jail = AccountJail()
        self.notes = {}
        self.artifacts = {}
        self.steps = []
        self.email_ready = asyncio.Event()
        self.rehearsed = False

    def event(self, kind, **data):
        self.emit({'kind': kind, 'at': time.time(), **data})

    async def plan(self):
        prompt = 'Write a short executable plan for the supplied goal. JSON only: steps is a list of {tool,label}; deliverables is ["deck","email_en","email_es","image"]. Allowed tools: ' + ', '.join(name for name in TOOL_SCHEMAS if self.audio or name != 'speak_summary') + '. Read the account folder first. Cover all four deliverables. No other tools or deliverables.'
        for attempt in range(2):
            result = await infer([{'role': 'system', 'content': prompt}, {'role': 'user', 'content': GOAL}],
                run_id=self.run_id, purpose=self.purpose, role='agent_plan', max_tokens=450,
                response_format={'type': 'json_schema', 'json_schema': {'name': 'stage_plan', 'strict': True, 'schema': PLAN_SCHEMA}},
                on_text=lambda text: self.event('plan_stream', text=text))
            try:
                plan = validate_plan(json_content(result['content']), self.audio)
                self.event('plan', plan=plan, rehearsed=False)
                return plan
            except Exception as exc:
                # Validation failures are bounded, logged as types, and never executed.
                self.event('plan_rejected', attempt=attempt + 1, reason=type(exc).__name__)
        path = ROOT / 'state/stage/plans/rehearsed.json'
        plan = validate_plan(json.loads(path.read_text()), self.audio)
        self.rehearsed = True
        self.event('plan', plan=plan, rehearsed=True)
        return plan

    async def tool(self, name, arguments):
        if name not in TOOL_SCHEMAS or (name == 'speak_summary' and not self.audio):
            raise ValueError('Tool is not allowlisted for this run')
        validate(arguments, TOOL_SCHEMAS[name])
        step = {'tool': name, 'status': 'running', 'started': time.time(), 'model':
                {'build_deck': LEAD, 'generate_image': 'FLUX.2-klein-4B', 'translate': WORKER, 'speak_summary': 'Kokoro-82M'}.get(name, 'Local tool')}
        self.steps.append(step)
        self.event('step', step=dict(step))
        began = time.monotonic()
        try:
            result = await asyncio.wait_for(self.execute(name, arguments),
                {'list_files': 2, 'read_file': 2, 'draft_email': 2, 'build_deck': 50, 'generate_image': 50, 'translate': 40, 'speak_summary': 12}[name])
            step.update(status='complete', seconds=time.monotonic() - began)
            self.event('step', step=dict(step))
            return result
        except Exception:
            step.update(status='failed', seconds=time.monotonic() - began)
            self.event('step', step=dict(step))
            raise
        except asyncio.CancelledError:
            step.update(status='cancelled', seconds=time.monotonic() - began)
            self.event('step', step=dict(step))
            raise

    async def execute(self, name, arguments):
        if name == 'list_files':
            return {'files': self.jail.list_files()}
        if name == 'read_file':
            result = {name: self.jail.read_file(name) for name in arguments['files']}
            self.notes.update(result)
            return result
        if set(self.notes) != set(FILES):
            raise ValueError('Read all four sample notes before generating artifacts')
        context = '\n\n'.join(name + '\n' + self.notes[name] for name in FILES)
        if name == 'draft_email':
            check_claims(arguments)
            self.artifacts['email_en'] = dict(arguments)
            (self.folder / 'email-en.json').write_text(json.dumps(arguments, ensure_ascii=False, indent=2))
            self.email_ready.set()
            self.event('artifact', artifact='email_en', data=arguments)
            return {'artifact': 'email-en', 'draft_only': True}
        if name == 'build_deck':
            result = await infer([{'role': 'system', 'content': 'Author exactly five concise executive briefing slides from the fictional source. JSON only matching the schema. Each slide has a short title, subtitle, two or three short points, and notes. Ground all content in the source. No invented statistics, legal assurances, customer claims, HTML or URLs.'},
                {'role': 'user', 'content': context + '\nBrief: ' + arguments['brief']}], run_id=self.run_id, purpose=self.purpose,
                role='agent_deck', max_tokens=1800, response_format={'type': 'json_schema', 'json_schema': {'name': 'five_slide_deck', 'strict': True, 'schema': DECK_SCHEMA}})
            if result['finish_reason'] != 'stop':
                raise ValueError('Deck author response was incomplete')
            deck = write_deck(json_content(result['content']), self.folder)
            self.artifacts['deck'] = deck
            self.event('artifact', artifact='deck', data=deck)
            return {'artifact': 'deck', 'slides': len(deck['slides'])}
        if name == 'generate_image':
            result = await image_job(arguments['prompt'], self.run_id, self.purpose,
                on_update=lambda job: self.event('image_progress', job=job))
            self.artifacts['image'] = result
            self.event('artifact', artifact='image', data=result)
            return {'artifact': 'image', 'images': result['images_done']}
        if name == 'translate':
            await self.email_ready.wait()
            english = self.artifacts['email_en']
            result = await infer([{'role': 'system', 'content': 'Translate this email draft into Spanish. Return JSON with subject and body only. Preserve the fictional names and factual meaning. Do not send anything.'},
                {'role': 'user', 'content': json.dumps(english, ensure_ascii=False)}], model=WORKER, run_id=self.run_id,
                purpose=self.purpose, role='agent_spanish', max_tokens=1000,
                response_format={'type': 'json_schema', 'json_schema': {'name': 'spanish_email', 'strict': True,
                    'schema': object_schema({'subject': TEXT(200), 'body': TEXT(5000)})}})
            if result['finish_reason'] != 'stop':
                raise ValueError('Spanish email was incomplete')
            translated = json_content(result['content'])
            validate(translated, object_schema({'subject': TEXT(200), 'body': TEXT(5000)}))
            check_claims(translated)
            self.artifacts['email_es'] = translated
            (self.folder / 'email-es.json').write_text(json.dumps(translated, ensure_ascii=False, indent=2))
            self.event('artifact', artifact='email_es', data=translated)
            return {'artifact': 'email-es', 'language': 'es'}
        if name == 'speak_summary':
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                response = await client.post('http://127.0.0.1:18204/v1/audio/speech', json={'input': arguments['text'], 'voice': 'am_michael'})
                response.raise_for_status()
                (self.folder / 'summary.pcm').write_bytes(response.content)
            self.event('artifact', artifact='voice', data={'file': 'summary.pcm', 'sample_rate': 24000})
            return {'artifact': 'voice', 'pcm_bytes': len(response.content)}
        raise ValueError('Unknown allowlisted tool')

    async def rehearsed_run(self):
        await self.tool('list_files', {})
        await self.tool('read_file', {'files': list(FILES)})
        context = '\n\n'.join(self.notes.values())
        draft = await infer([{'role': 'system', 'content': 'Write a concise English follow up email draft from these fictional notes. Return JSON with subject and body. Ask for a pilot owner, a workshop and agreed success measures. Do not invent a commitment or send anything.'},
                             {'role': 'user', 'content': context}], run_id=self.run_id, purpose=self.purpose, role='agent_email', max_tokens=650)
        await self.tool('draft_email', json_content(draft['content']))
        await parallel_tools(self, [('build_deck', {'brief': 'Account context, priorities, bounded pilot, open risks and next actions.'}),
            ('generate_image', {'prompt': 'Original calm editorial illustration of connected planning cards beside a small navy desktop computer, blue light, no people, no text, no logos.'}),
            ('translate', {'source': 'email-en', 'languages': ['es']})])

    async def run(self):
        began = time.monotonic()
        plan = await self.plan()
        if self.rehearsed:
            await self.rehearsed_run()
        else:
            names = [name for name in TOOL_SCHEMAS if self.audio or name != 'speak_summary']
            tools = [{'type': 'function', 'function': {'name': name, 'description': {
                'list_files': 'List the fictional account notes.', 'read_file': 'Read one or more of the listed sample files in one bounded read-only batch.',
                'build_deck': 'Generate the five-slide briefing live using the local Presentations engine.', 'generate_image': 'Generate an original cover illustration live with FLUX.',
                'draft_email': 'Save the English email YOU author in subject/body as a draft. This never sends email.',
                'translate': 'Translate the saved email-en draft into Spanish live with Qwen. This may run in the same parallel batch as draft_email.',
                'speak_summary': 'Synthesize a short summary with the local Kokoro voice.'}[name], 'parameters': TOOL_SCHEMAS[name]}} for name in names]
            messages = [{'role': 'system', 'content': 'You are a local personal agent for fictional sample data. Execute the supplied plan using only the provided tools. First list files, then read ALL FOUR files in ONE read_file call. After reading, request build_deck, generate_image, draft_email and translate as independent parallel tool calls. The scheduler queues artifact requests until all four have been requested, then executes them together. A queued response means you must request the remaining tools, never repeat a queued request. Author the English email yourself in draft_email arguments, under 150 words. translate refers to email-en and waits for that draft. Do not type tool code or a final answer in place of calls. No more than eight tool calls total. No paths, URLs, shell commands or SQL. Audio is ' + ('on; also request speak_summary with a short account briefing summary.' if self.audio else 'off; never request speech.')},
                        {'role': 'user', 'content': GOAL + '\nValidated plan: ' + json.dumps(plan)}]
            total_calls = 0
            pending = {}
            required = {'build_deck', 'generate_image', 'draft_email', 'translate'} | ({'speak_summary'} if self.audio else set())
            for turn in range(8):
                result = await infer(messages, run_id=self.run_id, purpose=self.purpose, role='agent_tools', max_tokens=1500,
                                     tools=tools, parallel_tool_calls=True)
                calls = result['tool_calls']
                if not calls:
                    raise ValueError('Agent ended before producing its required artifacts')
                total_calls += len(calls)
                if total_calls > 8:
                    raise ValueError('Agent exceeded its eight-tool-call limit')
                parsed = []
                for call in calls:
                    name = call['function']['name']
                    arguments = json.loads(call['function']['arguments'])
                    if name not in names:
                        raise ValueError('Agent requested a non-allowlisted tool')
                    validate(arguments, TOOL_SCHEMAS[name])
                    parsed.append((name, arguments))
                messages.append({'role': 'assistant', 'content': result['content'] or None, 'tool_calls': calls})
                outputs = []
                for name, arguments in parsed:
                    if name in required:
                        if set(self.notes) != set(FILES) or name in pending:
                            raise ValueError('Artifact request requires all notes and cannot be repeated')
                        pending[name] = arguments
                        self.event('step', step={'tool': name, 'status': 'queued', 'model':
                            {'build_deck': LEAD, 'generate_image': 'FLUX.2-klein-4B', 'translate': WORKER,
                             'speak_summary': 'Kokoro-82M'}.get(name, 'Local tool'), 'queued_at': time.time()})
                        outputs.append({'status': 'queued', 'tool': name, 'remaining': sorted(required - set(pending)),
                                        'reason': 'Independent artifacts start together after all requests arrive'})
                    else:
                        outputs.append(await self.tool(name, arguments))
                for call, output in zip(calls, outputs):
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(output, ensure_ascii=False)})
                if set(pending) == required:
                    await parallel_tools(self, list(pending.items()))
                    break
            else:
                raise ValueError('Agent exceeded its bounded execution rounds')
        if not set(DELIVERABLES) <= set(self.artifacts):
            raise ValueError('Agent is missing a required deliverable')
        result = {'seconds': time.monotonic() - began, 'rehearsed_plan': self.rehearsed, 'artifacts': self.artifacts, 'steps': self.steps}
        (self.folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        self.event('complete', seconds=result['seconds'])
        return result
