#!/usr/bin/env python3
"""Measure the actual resident stack, native Agent and concurrent six-job Rush."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ops'))


def benchmark_module():
    spec = importlib.util.spec_from_file_location('gb10_benchmark', ROOT / 'ops/gb10-benchmark.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = int(position)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)


def process_scope(pid='self'):
    return next(line.split('::', 1)[1] for line in Path('/proc', str(pid), 'cgroup').read_text().splitlines() if line.startswith('0::'))


def scope_snapshot():
    folder = Path('/sys/fs/cgroup') / process_scope().lstrip('/')
    return {'swap_limit': (folder / 'memory.swap.max').read_text().strip(),
            'swap_current_bytes': int((folder / 'memory.swap.current').read_text()),
            'memory_current_bytes': int((folder / 'memory.current').read_text()),
            'memory_peak_bytes': int((folder / 'memory.peak').read_text())}


def assess_gate(row, *, warmups, agent_runs, rush_runs, require_no_swap_scope):
    """Evaluate recorded measurements; this never constitutes new acceptance."""
    runs = row.get('runs', [])
    agents = [r for r in runs if r['purpose'] == 'live' and r['segment'] == 'S1']
    rushes = [r for r in runs if r['purpose'] == 'live' and r['segment'] == 'S3']
    checks = {
        'two_full_warm_passes': warmups >= 2 and all(
            sum(r['purpose'] == 'warmup' and r['segment'] == segment for r in runs) >= warmups
            for segment in ('S1', 'S2', 'S3')),
        'five_agent_samples': agent_runs >= 5 and len(agents) == agent_runs,
        'five_rush_samples': rush_runs >= 5 and len(rushes) == rush_runs,
        'all_jobs_complete': bool(runs) and all(r['status'] == 'complete' for r in runs),
        'all_lanes_resident': bool(runs) and all(r.get('lanes_resident', False) for r in runs),
        'agent_p95_at_most_75_seconds': bool(agents) and percentile([r['seconds'] for r in agents], .95) <= 75,
        'rush_at_most_60_seconds': bool(rushes) and max(r['seconds'] for r in rushes) <= 60,
        'rush_minimum_10_gib_available': bool(rushes) and all(r.get('memory', {}).get('min_available_bytes', 0) >= 10 * 2**30 for r in rushes),
        'rush_zero_global_swap': bool(rushes) and all(r.get('memory', {}).get('swap_in_pages') == r.get('memory', {}).get('swap_out_pages') == 0 for r in rushes),
        'no_kernel_oom': bool(runs) and all(
            isinstance(r.get('memory', {}).get('baseline', {}).get('oom_kill'), int)
            and r.get('memory', {}).get('after', {}).get('oom_kill') == r['memory']['baseline']['oom_kill'] for r in runs),
        'runtime_scope_swap_zero': require_no_swap_scope and bool(runs) and all(
            r.get('runtime_memory', {}).get('swap_limit') == '0'
            and r.get('runtime_memory', {}).get('swap_current_bytes') == 0 for r in runs),
    }
    return {'passed': all(checks.values()), 'checks': checks}


def save(row):
    folder = ROOT / 'state/gb10-qualification'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ('workload-' + row['quant'] + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    (folder / ('workload-' + row['quant'] + '-' + str(int(row['started_at'])) + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    public = ROOT / 'docs/verification/gb10_memory_plan.json'
    data = json.loads(public.read_text())
    previous = data.setdefault('workloads', {}).get(row['quant'])
    if previous and previous['started_at'] != row['started_at']:
        data.setdefault('workload_attempts', []).append(previous)
    data['workloads'][row['quant']] = row
    if row.get('assessment'):
        agents = [r for r in row['runs'] if r['segment'] == 'S1' and r['purpose'] == 'live']
        rushes = [r for r in row['runs'] if r['segment'] == 'S3' and r['purpose'] == 'live']
        prior = data.get('latest_assessment')
        if prior and prior.get('source_started_at') != row['started_at']:
            data.setdefault('assessment_history', []).append(prior)
        data['latest_assessment'] = {
            'source_started_at': row['started_at'], 'quant': row['quant'], 'assessment': row['assessment'],
            'agent_p50_seconds': percentile([r['seconds'] for r in agents], .5) if agents else None,
            'agent_p95_seconds': row.get('agent_p95_seconds'),
            'rush_p50_seconds': percentile([r['seconds'] for r in rushes], .5) if rushes else None,
            'rush_p95_seconds': percentile([r['seconds'] for r in rushes], .95) if rushes else None,
            'rush_max_seconds': row.get('rush_max_seconds'),
            'rush_min_available_gib': min(r['memory']['min_available_bytes'] for r in rushes) / 2**30 if rushes else None,
            'rush_swap_in_pages': [r['memory']['swap_in_pages'] for r in rushes],
            'rush_swap_out_pages': [r['memory']['swap_out_pages'] for r in rushes]}
    if row.get('passed'):
        data['status'] = 'gate_1_passed'
        data['decision'] = {'passed': True, 'quant': row['quant'], 'lead_loading': row['lead_loading'], 'text_loading': row['text_loading'],
                            'flux_encoder': row['flux_encoder'], 'cpu_prompt_cache_limit_mib_per_server': 0,
                            'batch_tokens': 512, 'microbatch_tokens': 128, 'process_swap_limit_bytes': 0,
                            'voice_device': row['voice_device'],
                            'context_per_slot': 16384, 'lead_slots': 2, 'text_slots': 3,
                            'reason': 'Actual resident stack, Agent and five six-job Rush runs meet every required threshold'}
    elif row.get('assessment'):
        data['status'] = 'gate_1_blocked'
        data['decision'] = {'passed': False, 'quant': row['quant'], 'reason': 'The current candidate did not meet every required threshold',
                            'checks': row['assessment']['checks']}
    public.write_text(json.dumps(data, indent=2) + '\n')


async def one(name, number, purpose, row, module, audio=False):
    from showcase_app.gb10_agent import NanoAgent
    from showcase_app.gb10_rush import NanoRush
    from showcase_app.gb10_vision import run_vision
    run_id = 'qual_' + row['quant'] + '_' + name + '_' + purpose + '_' + str(number) + '_' + str(int(time.time()))
    events = ROOT / 'state/gb10-qualification' / (run_id + '.jsonl')
    def emit(event):
        with events.open('a') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    began = time.monotonic()
    sample = {'segment': name, 'run_id': run_id, 'purpose': purpose, 'audio': audio, 'status': 'running'}
    row['runs'].append(sample)
    save(row)
    import control
    identities = {lane: control.fingerprint(control.discover(lane)) if control.discover(lane) else None
                  for lane in ('image', 'tts', 'text', 'lead', 'gateway')}
    monitor = None
    try:
        if row.get('runtime_policy'):
            if any(not identity or process_scope(identity['pid']) != process_scope() for identity in identities.values()):
                raise RuntimeError('A model lane is outside the verified runtime memory scope')
        with module.Monitor() as monitor:
            if name == 'S1':
                result = await asyncio.wait_for(NanoAgent(run_id, purpose=purpose, audio=audio, emit=emit).run(), 90)
            elif name == 'S2':
                result = await asyncio.wait_for(run_vision(run_id, purpose, emit), 30)
            else:
                result = await asyncio.wait_for(NanoRush(run_id, purpose=purpose, audio=audio, emit=emit).run(), 75)
        sample.update(status='complete', seconds=time.monotonic() - began, memory=monitor.summary())
        if name == 'S3':
            sample['jobs'] = {key: {k: v for k, v in value.items() if k in ('name', 'status', 'seconds', 'error')} for key, value in result['jobs'].items()}
            if result['done'] != 6:
                sample['status'] = 'failed'
        if name == 'S1':
            sample['rehearsed_plan'] = result['rehearsed_plan']
            sample['tool_seconds'] = [{k: step[k] for k in ('tool', 'seconds', 'status')} for step in result['steps']]
        with sqlite3.connect(ROOT / 'state/stage/usage.sqlite') as db:
            tokens = db.execute('SELECT COALESCE(SUM(output_tokens),0) FROM events WHERE run_id=? AND status="complete"', (run_id,)).fetchone()[0]
        sample['output_tokens'] = tokens
        sample['aggregate_output_tokens_per_second'] = tokens / sample['seconds']
        sample['lanes_resident'] = all(identities[lane] and control.unchanged(identities[lane]) and control.ready(lane) for lane in identities)
        if row.get('runtime_policy'):
            sample['runtime_memory'] = scope_snapshot()
            if sample['runtime_memory']['swap_limit'] != '0' or sample['runtime_memory']['swap_current_bytes'] != 0:
                sample.update(status='failed', error='RuntimeScopeSwapInvariant')
        if not sample['lanes_resident']:
            sample.update(status='failed', error='ResidentLaneIdentityChanged')
    except Exception as exc:
        sample.update(status='failed', seconds=time.monotonic() - began, error=type(exc).__name__)
        if monitor is not None:
            sample['memory'] = monitor.summary()
        print(name, type(exc).__name__, str(exc), flush=True)
    save(row)
    print(json.dumps(sample), flush=True)
    return sample


async def main(args):
    os.environ.update(FURY_PROFILE='gb10', FURY_GB10_QUANT=args.quant, FURY_GB10_FLUX_ENCODER=args.flux_encoder, FURY_GB10_VOICE_DEVICE=args.voice_device,
                      FURY_GB10_LEAD_NO_MMAP='1', FURY_GB10_TEXT_NO_MMAP='1' if args.text_loading == 'no-mmap' else '0',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', LOGURU_LEVEL='WARNING',
                      PLAYWRIGHT_BROWSERS_PATH=str(ROOT / '.cache/ms-playwright'))
    os.environ['FURY_GB10_LEAD_LOAD_MODE'] = 'dio' if args.lead_loading == 'direct' else 'none'
    os.environ['FURY_GB10_TEXT_LOAD_MODE'] = {'mmap': 'auto', 'no-mmap': 'none', 'direct': 'dio'}[args.text_loading]
    module = benchmark_module()
    row = {'quant': args.quant, 'flux_encoder': args.flux_encoder, 'voice_device': args.voice_device, 'text_loading': args.text_loading, 'lead_loading': args.lead_loading,
           'started_at': time.time(), 'status': 'running', 'passed': False, 'runs': [], 'loads': []}
    if args.require_no_swap_scope:
        relative = next(line.split('::', 1)[1] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
        scope = Path('/sys/fs/cgroup') / relative.lstrip('/')
        if (scope / 'memory.swap.max').read_text().strip() != '0':
            raise RuntimeError('Qualification requires a transient user scope with MemorySwapMax=0')
        row['runtime_policy'] = {'process_swap_limit_bytes': 0, 'transient_user_scope': True,
                                 'weight_file_cache_advice': os.getenv('FURY_GB10_RELEASE_WEIGHT_CACHE') == '1',
                                 'global_swap_enabled': bool(Path('/proc/swaps').read_text().splitlines()[1:])}
        if not row['runtime_policy']['global_swap_enabled']:
            raise RuntimeError('Global swap must remain enabled for this acceptance test')
    plan = ROOT / 'state/stage/plans/rehearsed.json'
    plan.parent.mkdir(parents=True, exist_ok=True)
    if not plan.exists():
        plan.write_bytes((ROOT / 'samples/stage/rehearsed-plan.json').read_bytes())
    if not args.resident:
        if module.other_compute_count():
            raise RuntimeError('Unrelated GPU workload present; resident qualification refused')
        records = json.loads((ROOT / 'state/gb10-qualification/measurements.json').read_text())['runs']
        chosen = []
        image_quant = 'BF16/FP8 text encoder' if args.flux_encoder == 'fp8' else 'BF16'
        for lane, quant, loading in [('lead', 'MXFP4', args.lead_loading), ('text', args.quant, args.text_loading), ('image', image_quant, None), ('voice', 'publisher v1.0', None)]:
            matches = [r for r in records if r['lane'] == lane and r.get('quant') == quant and r.get('loading') == loading and r['status'] == 'measured' and r['qualification_scope'] == 'isolated_candidate']
            if lane == 'voice':
                matches = [r for r in matches if r.get('device', 'cuda') == args.voice_device]
            if not matches:
                raise RuntimeError('Missing isolated measurement: ' + lane + '/' + quant)
            if lane == 'text' and (len(matches[-1].get('vision_quality', [])) != 2 or not all(q['passed'] for q in matches[-1]['vision_quality'])):
                raise RuntimeError('Qwen quant has not passed both actual vision quality checks')
            if lane == 'lead' and not matches[-1].get('native_tool_call', {}).get('passed'):
                raise RuntimeError('Lead has not passed its actual native tool-call check')
            chosen.append(matches[-1])
        predicted = module.memory()['available_bytes'] - sum(r['resident_memavailable_drop_bytes'] for r in chosen)
        row.update(predicted_memavailable_bytes=predicted, isolated_inputs=[{'lane': r['lane'], 'started_at': r['started_at'], 'resident_memavailable_drop_bytes': r['resident_memavailable_drop_bytes']} for r in chosen])
        if predicted < 10 * 2**30:
            row.update(status='admission_refused', reason='Sum of measured isolated residency would breach the 10 GiB floor before any concurrent workload')
            save(row)
            print(json.dumps(row), flush=True)
            return False
        for name in ('image', 'tts', 'text', 'lead', 'gateway'):
            with module.Monitor() as monitor:
                seconds = await asyncio.to_thread(module.controller, 'start', name, dict(os.environ))
            row['loads'].append({'lane': name, 'seconds': seconds, 'memory': monitor.summary()})
            save(row)
    else:
        import control
        for name in ('image', 'tts', 'text', 'lead', 'gateway'):
            if not control.discover(name):
                raise RuntimeError('Requested resident lane is not verified as owned: ' + name)
            await asyncio.to_thread(module.controller, 'start', name, dict(os.environ))
    row['resident_memory'] = module.memory()
    save(row)
    with module.Monitor() as total_monitor:
        for number in range(1, args.warmups + 1):
            for name in ('S1', 'S2', 'S3'):
                sample = await one(name, number, 'warmup', row, module, args.audio)
                if sample['status'] != 'complete':
                    row.update(status='warmup_failed', memory=total_monitor.summary())
                    save(row)
                    return False
        for number in range(1, args.agent_runs + 1):
            if (await one('S1', number, 'live', row, module, args.audio))['status'] != 'complete':
                break
        for number in range(1, args.rush_runs + 1):
            if (await one('S3', number, 'live', row, module, args.audio))['status'] != 'complete':
                break
    row['memory'] = total_monitor.summary()
    agents = [r['seconds'] for r in row['runs'] if r['purpose'] == 'live' and r['segment'] == 'S1' and r['status'] == 'complete']
    rushes = [r['seconds'] for r in row['runs'] if r['purpose'] == 'live' and r['segment'] == 'S3' and r['status'] == 'complete']
    row['agent_p95_seconds'] = percentile(agents, .95) if agents else None
    row['rush_max_seconds'] = max(rushes) if rushes else None
    row['assessment'] = assess_gate(row, warmups=args.warmups, agent_runs=args.agent_runs,
                                  rush_runs=args.rush_runs, require_no_swap_scope=args.require_no_swap_scope)
    row['passed'] = row['assessment']['passed']
    row.update(status='passed' if row['passed'] else 'failed', ended_at=time.time())
    save(row)
    print(json.dumps({k: v for k, v in row.items() if k != 'runs'}, indent=2), flush=True)
    return row['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--quant', choices=['Q8_0', 'Q6_K', 'Q4_K_XL', 'Q4_K_M'], required=True)
    parser.add_argument('--resident', action='store_true', help='Use only the already verified, owned resident stack')
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--agent-runs', type=int, default=5)
    parser.add_argument('--rush-runs', type=int, default=5)
    parser.add_argument('--audio', action='store_true')
    parser.add_argument('--flux-encoder', choices=['bf16', 'fp8'], default='bf16')
    parser.add_argument('--voice-device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--lead-loading', choices=['no-mmap', 'direct'], default='no-mmap')
    parser.add_argument('--text-loading', choices=['mmap', 'no-mmap', 'direct'], default='mmap')
    parser.add_argument('--require-no-swap-scope', action='store_true')
    sys.exit(0 if asyncio.run(main(parser.parse_args())) else 1)
