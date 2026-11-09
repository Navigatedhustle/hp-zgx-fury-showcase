"""Loopback-only measured model client shared by GB10 qualification and stage runs."""
import json
import time
import uuid

import httpx

LEAD = 'gpt-oss-120b'
WORKER = 'Qwen3.6-35B-A3B'
GATEWAY = 'http://127.0.0.1:18001'


async def infer(messages, *, model=LEAD, caller='agent', run_id='', purpose='live', role='language',
                max_tokens=1200, on_text=None, call_id=None, **options):
    if model not in (LEAD, WORKER) or caller not in ('agent', 'rush', 'vision', 'translate', 'warmup', 'keepalive'):
        raise ValueError('Unknown local model or caller')
    cid = call_id or uuid.uuid4().hex
    headers = {'x-fury-call-id': cid, 'x-fury-role': role, 'x-stage-run': run_id, 'x-stage-purpose': purpose}
    body = {'model': model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0,
            'seed': 42, 'stream': True, 'stream_options': {'include_usage': True}, 'cache_prompt': True,
            **({'reasoning_effort': 'low'} if model == LEAD else {'chat_template_kwargs': {'enable_thinking': False}}),
            **options}
    started = time.monotonic()
    text = ''
    calls = {}
    usage = None
    timings = None
    finish = None
    actual = model
    routing = ''
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(90, connect=3)) as client:
        async with client.stream('POST', GATEWAY + '/stage/' + caller + '/v1/chat/completions', json=body, headers=headers) as response:
            response.raise_for_status()
            actual = response.headers.get('x-fury-model', model)
            routing = response.headers.get('x-fury-routing', '')
            async for line in response.aiter_lines():
                if not line.startswith('data:'):
                    continue
                raw = line[5:].strip()
                if raw == '[DONE]':
                    break
                item = json.loads(raw)
                if item.get('error'):
                    raise RuntimeError('Local inference failed: ' + actual)
                usage = item.get('usage') or usage
                timings = item.get('timings') or timings
                for choice in item.get('choices', []):
                    delta = choice.get('delta', {})
                    chunk = delta.get('content') or ''
                    text += chunk
                    if chunk and on_text:
                        on_text(text)
                    for part in delta.get('tool_calls') or []:
                        call = calls.setdefault(part.get('index', 0), {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        call['id'] += part.get('id') or ''
                        function = part.get('function') or {}
                        call['function']['name'] += function.get('name') or ''
                        call['function']['arguments'] += function.get('arguments') or ''
                    finish = choice.get('finish_reason') or finish
    if usage is None:
        raise RuntimeError('Local inference returned no measured token usage')
    return {'content': text, 'tool_calls': list(calls.values()), 'usage': usage, 'timings': timings,
            'finish_reason': finish, 'model': actual, 'requested': model, 'routing': routing,
            'seconds': time.monotonic() - started, 'call_id': cid}


def json_content(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json.loads(text)
