#!/usr/bin/env python3
"""Live GB10 qualification. Never treats a health response as inference evidence."""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def memory():
    mem = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    vm = {line.split()[0]: int(line.split()[1]) for line in Path('/proc/vmstat').read_text().splitlines()}
    return {'time': time.time(), 'total_bytes': mem['MemTotal'], 'available_bytes': mem['MemAvailable'],
            'swap_used_bytes': mem['SwapTotal'] - mem['SwapFree'], 'pswpin': vm['pswpin'], 'pswpout': vm['pswpout'],
            'oom_kill': vm.get('oom_kill')}


def other_compute_count():
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Cannot verify isolated GPU process state')
    owned = {os.getpid()}
    registry = ROOT / 'state/supervisor.json'
    if registry.exists():
        import control
        for name, entry in json.loads(registry.read_text()).items():
            leader = entry.get('leader')
            if name in control.COMPONENTS and leader and control.unchanged(leader) and control.identity(control.process(leader['pid']), name):
                owned.add(leader['pid'])
    live = set()
    for line in result.stdout.splitlines():
        if not line.strip().isdigit():
            continue
        process = Path('/proc', line.strip())
        try:
            if process.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[0] != 'Z':
                live.add(int(line.strip()))
        except FileNotFoundError:
            pass
        except OSError:
            live.add(int(line.strip()))
    return len(live - owned)


class Monitor:
    def __enter__(self):
        self.samples = [memory()]
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.poll, daemon=True)
        self.thread.start()
        return self

    def poll(self):
        while not self.done.wait(.1):
            self.samples.append(memory())

    def __exit__(self, *_):
        self.done.set()
        self.thread.join()
        self.samples.append(memory())

    def summary(self):
        first, last = self.samples[0], self.samples[-1]
        return {'baseline': first, 'after': last,
                'min_available_bytes': min(s['available_bytes'] for s in self.samples),
                'peak_memory_used_bytes': max(s['total_bytes'] - s['available_bytes'] for s in self.samples),
                'swap_in_pages': last['pswpin'] - first['pswpin'],
                'swap_out_pages': last['pswpout'] - first['pswpout'], 'sample_interval_ms': 100}


def request(port, route, data=None):
    req = urllib.request.Request('http://127.0.0.1:' + str(port) + route,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=240) as response:
        return json.load(response)


from showcase_app.gb10_quality import canonical_table, extraction_matches


def chat(port, model, messages, max_tokens=256, **extras):
    payload = {'model': model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0,
               'seed': 42, 'cache_prompt': False, 'stream': True, 'stream_options': {'include_usage': True},
               'reasoning_effort': 'low', 'chat_template_kwargs': {'enable_thinking': False}, **extras}
    req = urllib.request.Request('http://127.0.0.1:' + str(port) + '/v1/chat/completions',
                                 data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    began = time.monotonic()
    ttft = None
    content = ''
    tool_calls = []
    timings = None
    usage = None
    finish_reason = None
    with OPENER.open(req, timeout=240) as response:
        for raw in response:
            if not raw.startswith(b'data: '):
                continue
            raw = raw[6:].strip()
            if raw == b'[DONE]':
                break
            part = json.loads(raw)
            for choice in part.get('choices', []):
                delta = choice.get('delta', {})
                if any(delta.get(k) for k in ('content', 'reasoning_content', 'reasoning', 'tool_calls')) and ttft is None:
                    ttft = time.monotonic() - began
                content += delta.get('content') or ''
                tool_calls += delta.get('tool_calls') or []
                finish_reason = choice.get('finish_reason') or finish_reason
            timings = part.get('timings') or timings
            usage = part.get('usage') or usage
    return {'seconds': time.monotonic() - began, 'ttft_seconds': ttft, 'timings': timings,
            'usage': usage, 'content': content, 'tool_call_deltas': tool_calls, 'finish_reason': finish_reason}


def context_messages(port, target):
    # Calibrate actual chat-template token length; retain the complete native template.
    words = max(1, target // 7)
    for _ in range(5):
        messages = [{'role': 'system', 'content': 'You are a concise local assistant.'},
                    {'role': 'user', 'content': ('The fictional account requires resilient local tools. ' * words) +
                     '\nWrite a detailed 300 word summary of the operational benefits, with no external facts.'}]
        prompt = request(port, '/apply-template', {'messages': messages})['prompt']
        actual = len(request(port, '/tokenize', {'content': prompt})['tokens'])
        if abs(actual - target) <= 10:
            break
        words = max(1, round(words * (target - 60) / max(1, actual - 60)))
    return messages, actual


def controller(action, lane, env):
    began = time.monotonic()
    result = subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / 'ops/control.py'), action, lane],
                            cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1000)
    log = ROOT / 'state/gb10-qualification/controller.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a') as stream:
        stream.write(result.stdout)
    if result.returncode:
        raise RuntimeError('Verified controller failed; inspect state/gb10-qualification/controller.log')
    return time.monotonic() - began


def benchmark_llama(args, records):
    lane, port, model = ('lead', 18100, 'gpt-oss-120b') if args.lane == 'lead' else ('text', 18000, 'Qwen3.6-35B-A3B')
    env = {**os.environ, 'FURY_PROFILE': 'gb10', 'FURY_GB10_QUANT': args.quant,
           'FURY_GB10_NO_MMAP': '1' if args.loading == 'no-mmap' else '0'}
    # A baseline load is required. Never adopt a server already resident for another run.
    os.environ.update({key: env[key] for key in ('FURY_PROFILE', 'FURY_GB10_QUANT', 'FURY_GB10_NO_MMAP')})
    import control
    if any(control.discover(name) for name in ('lead', 'text')) or control.port_open(port):
        raise RuntimeError('Qualification port already occupied; inspect verified controller status before proceeding')
    row = {'lane': args.lane, 'quant': 'MXFP4' if lane == 'lead' else args.quant, 'loading': args.loading,
           'cpu_prompt_cache_limit_mib': 256,
           'started_at': time.time(), 'status': 'running', 'benchmarks': [],
           'other_compute_processes_count': other_compute_count()}
    row['qualification_scope'] = 'isolated_candidate' if row['other_compute_processes_count'] == 0 else 'diagnostic_with_unrelated_workloads'
    records.append(row)
    save(records)
    baseline = memory()
    started = False
    try:
        with Monitor() as monitor:
            row['load_seconds'] = controller('start', lane, env)
            started = True
        row['load_memory'] = monitor.summary()
        row['resident_memavailable_drop_bytes'] = baseline['available_bytes'] - memory()['available_bytes']
        row['other_compute_processes_after_load'] = other_compute_count()
        # Run real decode at both requested context sizes. Keep actual template token counts.
        for target in (1024, 8192):
            messages, token_count = context_messages(port, target)
            for repeat in range(args.repeats):
                with Monitor() as monitor:
                    result = chat(port, model, messages)
                if not result['timings'] or not all(key in result['timings'] for key in ('prompt_per_second', 'predicted_per_second')):
                    raise RuntimeError('Native prompt/decode timings missing; no throughput result can be accepted')
                result.update(target_context=target, calibrated_prompt_tokens=token_count, repeat=repeat + 1,
                              memory=monitor.summary())
                row['benchmarks'].append(result)
                save(records)
        if lane == 'lead':
            result = chat(port, model, [{'role': 'user', 'content': 'First list the fictional account folder using the list_files tool.'}],
                max_tokens=512, tools=[{'type': 'function', 'function': {'name': 'list_files',
                'description': 'List read-only fictional account notes.',
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}],
                tool_choice={'type': 'function', 'function': {'name': 'list_files'}})
            calls = {}
            for delta in result['tool_call_deltas']:
                item = calls.setdefault(delta.get('index', 0), {'name': '', 'arguments': ''})
                function = delta.get('function') or {}
                item['name'] += function.get('name') or ''
                item['arguments'] += function.get('arguments') or ''
            result['parsed_calls'] = list(calls.values())
            result['passed'] = len(calls) == 1 and next(iter(calls.values()))['name'] == 'list_files'
            if result['passed']:
                try:
                    result['passed'] = json.loads(next(iter(calls.values()))['arguments']) == {}
                except ValueError:
                    result['passed'] = False
            row['native_tool_call'] = result
            save(records)
        if lane == 'text':
            row['vision_quality'] = []
            expected = json.loads((ROOT / 'samples/stage/vision/expected.json').read_text())
            for filename, answer in expected.items():
                data = base64.b64encode((ROOT / 'samples/stage/vision' / filename).read_bytes()).decode()
                if filename.startswith('whiteboard'):
                    instruction = 'Extract EVERY action item, owner and ISO date. Return only a JSON array of objects with action, owner, date. Preserve the exact action wording.'
                else:
                    instruction = 'Extract the entire chart as a data table. Return only JSON with columns and rows. Preserve exact labels and numeric values.'
                result = chat(port, model, [{'role': 'user', 'content': [
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}},
                    {'type': 'text', 'text': instruction}]}], max_tokens=1200)
                text = result['content'].strip()
                if text.startswith('```'):
                    text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
                try:
                    result['extracted'] = json.loads(text)
                    result['passed'] = extraction_matches(filename, result['extracted'], answer) and result['finish_reason'] == 'stop'
                except json.JSONDecodeError:
                    result['passed'] = False
                row['vision_quality'].append({'sample': filename, **result})
                save(records)
        row['status'] = 'measured'
    except Exception as exc:
        row.update(status='failed', error=str(exc))
        if 'monitor' in locals():
            row['last_memory_observation'] = monitor.summary()
        raise
    finally:
        # Controller verifies PID/starttime/cwd/executable/session before any signal.
        row['other_compute_processes_before_stop'] = other_compute_count()
        if started:
            controller('stop', lane, env)
        row['other_compute_processes_at_end'] = other_compute_count()
        if row.get('other_compute_processes_after_load') or row['other_compute_processes_before_stop']:
            row['qualification_scope'] = 'diagnostic_with_unrelated_workloads'
        row['ended_at'] = time.time()
        save(records)


def save(records):
    destination = ROOT / 'state/gb10-qualification/measurements.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'schema': 1, 'status': 'qualification_incomplete', 'runs': records}, indent=2) + '\n')
    temporary.replace(destination)
    public = ROOT / 'docs/verification/gb10_memory_plan.json'
    public.parent.mkdir(parents=True, exist_ok=True)
    prior = json.loads(public.read_text()) if public.exists() else {}
    def publish(value):
        if isinstance(value, list):
            return [publish(item) for item in value]
        if isinstance(value, dict):
            return {key: ('Qualification error; raw diagnostic retained privately' if key == 'error' else publish(item))
                    for key, item in value.items() if key not in ('content', 'tool_call_deltas', 'extracted', 'parsed_calls')}
        return value
    report = {'schema': 1, 'hardware': 'NVIDIA GB10', 'status': prior.get('status', 'qualification_incomplete'),
              'decision': {'passed': False, 'reason': 'All required residency, quality and workload measurements must complete'},
              'measurement': 'MemAvailable deltas and 100 ms /proc/meminfo sampling; /proc/vmstat swap deltas; native llama.cpp timings and observed SSE TTFT',
              'preexisting_workloads_present': any(row.get('other_compute_processes_count', 0) > 0 for row in records),
              'minimum_memavailable_gib': 10, 'runs': publish(records), 'workloads': prior.get('workloads', {}),
              'workload_attempts': prior.get('workload_attempts', [])}
    if prior.get('decision', {}).get('passed'):
        report['decision'] = prior['decision']
    public.write_text(json.dumps(report, indent=2) + '\n')


def benchmark_creative(records):
    os.environ.update(FURY_PROFILE='gb10', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    from showcase_app.creative import CreativeLane
    row = {'lane': 'image', 'model': 'FLUX.2-klein-4B', 'quant': 'BF16/FP8 text encoder' if os.getenv('FURY_GB10_FLUX_ENCODER') == 'fp8' else 'BF16', 'started_at': time.time(),
           'status': 'running', 'benchmarks': [], 'other_compute_processes_count': other_compute_count()}
    row['qualification_scope'] = 'isolated_candidate' if row['other_compute_processes_count'] == 0 else 'diagnostic_with_unrelated_workloads'
    records.append(row)
    save(records)
    baseline = memory()
    lane = CreativeLane()
    try:
        began = time.monotonic()
        with Monitor() as monitor:
            lane.load()
        row.update(load_seconds=time.monotonic() - began, load_memory=monitor.summary(),
                   resident_memavailable_drop_bytes=baseline['available_bytes'] - memory()['available_bytes'])
        row['load_timings'] = lane.load_timings
        row['parameter_count'] = lane.parameter_count
        folder = ROOT / 'state/gb10-qualification/images'
        folder.mkdir(parents=True, exist_ok=True)
        prompt = 'Original editorial illustration of a small navy desktop computer beside a folded paper landscape, calm blue lighting, no text, no logo.'
        for width, height, batch in [(1344, 768, 1), (1024, 576, 4)]:
            for repeat in range(3):
                output = folder / f'{width}-{batch}-{repeat}.png'
                began = time.monotonic()
                job = {}
                with Monitor() as monitor:
                    metrics = lane.run('image', prompt, output, threading.Event(),
                        {'width': width, 'height': height, 'batch': batch, 'seed': 42}, job)
                row['benchmarks'].append({'width': width, 'height': height, 'batch': batch, 'steps': 4,
                    'warmup': repeat == 0, 'seconds': time.monotonic() - began, 'images_done': job['images_done'],
                    'memory': monitor.summary(), 'allocator': metrics})
                save(records)
        row['status'] = 'measured'
    except Exception as exc:
        row.update(status='failed', error=str(exc))
        raise
    finally:
        row['ended_at'] = time.time()
        save(records)


def benchmark_voice(records):
    os.environ.update(FURY_PROFILE='gb10', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    sys.path.insert(0, str(ROOT / 'build/sources/atlas-gpt-main'))
    row = {'lane': 'voice', 'model': 'Kokoro-82M', 'quant': 'publisher v1.0', 'started_at': time.time(),
           'status': 'running', 'benchmarks': [], 'other_compute_processes_count': other_compute_count()}
    row['qualification_scope'] = 'isolated_candidate' if row['other_compute_processes_count'] == 0 else 'diagnostic_with_unrelated_workloads'
    records.append(row)
    save(records)
    baseline = memory()
    try:
        began = time.monotonic()
        with Monitor() as monitor:
            from atlas import tts_server
            tts_server.load()
        row.update(load_seconds=time.monotonic() - began, load_memory=monitor.summary(),
                   resident_memavailable_drop_bytes=baseline['available_bytes'] - memory()['available_bytes'])
        for repeat in range(3):
            with Monitor() as monitor:
                audio, milliseconds = tts_server.generate('Six jobs, four models, one Nano. Everything ran locally.', 'am_michael')
            row['benchmarks'].append({'repeat': repeat + 1, 'seconds': milliseconds / 1000,
                                     'pcm_bytes': len(audio), 'audio_played': False, 'memory': monitor.summary()})
            save(records)
        row['status'] = 'measured'
    except Exception as exc:
        row.update(status='failed', error=str(exc))
        raise
    finally:
        row['ended_at'] = time.time()
        save(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lane', choices=['lead', 'text', 'image', 'voice'], required=True)
    parser.add_argument('--quant', choices=['Q8_0', 'Q6_K', 'Q4_K_XL'], default='Q8_0')
    parser.add_argument('--loading', choices=['mmap', 'no-mmap'], default='mmap')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--require-isolated', action='store_true')
    parser.add_argument('--flux-encoder', choices=['bf16', 'fp8'], default='bf16')
    args = parser.parse_args()
    # Ownership discovery imports the controller, whose profile is fixed at import.
    os.environ.update(FURY_PROFILE='gb10', FURY_GB10_QUANT=args.quant, FURY_GB10_FLUX_ENCODER=args.flux_encoder,
                      FURY_GB10_NO_MMAP='1' if args.loading == 'no-mmap' else '0')
    headers = ROOT / '.local-debs/extracted/usr/include'
    if headers.is_dir():
        os.environ['C_INCLUDE_PATH'] = str(headers) + ':' + str(headers / 'python3.12')
    if args.require_isolated:
        drain_deadline = time.monotonic() + 10
        while other_compute_count():
            if time.monotonic() >= drain_deadline:
                raise RuntimeError('Unrelated GPU compute workload present; isolated single-lane qualification refused')
            time.sleep(.2)
    path = ROOT / 'state/gb10-qualification/measurements.json'
    records = json.loads(path.read_text())['runs'] if path.exists() else []
    if args.lane == 'image':
        benchmark_creative(records)
    elif args.lane == 'voice':
        benchmark_voice(records)
    else:
        benchmark_llama(args, records)


if __name__ == '__main__':
    main()
