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


def save(row):
    folder = ROOT / 'state/gb10-qualification'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ('workload-' + row['quant'] + '.json')).write_text(json.dumps(row, indent=2) + '\n')
    public = ROOT / 'docs/verification/gb10_memory_plan.json'
    data = json.loads(public.read_text())
    data.setdefault('workloads', {})[row['quant']] = row
    if row.get('passed'):
        data['status'] = 'gate_1_passed'
        data['decision'] = {'passed': True, 'quant': row['quant'], 'lead_loading': 'no-mmap', 'text_loading': 'mmap',
                            'context_per_slot': 16384, 'lead_slots': 2, 'text_slots': 3,
                            'reason': 'Actual resident stack, Agent and five six-job Rush runs meet every required threshold'}
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
    try:
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
    except Exception as exc:
        sample.update(status='failed', seconds=time.monotonic() - began, error=type(exc).__name__, memory=monitor.summary())
        print(name, type(exc).__name__, str(exc), flush=True)
    save(row)
    print(json.dumps(sample), flush=True)
    return sample


async def main(args):
    os.environ.update(FURY_PROFILE='gb10', FURY_GB10_QUANT=args.quant,
                      FURY_GB10_LEAD_NO_MMAP='1', FURY_GB10_TEXT_NO_MMAP='0',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', LOGURU_LEVEL='WARNING',
                      PLAYWRIGHT_BROWSERS_PATH=str(ROOT / '.cache/ms-playwright'))
    module = benchmark_module()
    row = {'quant': args.quant, 'started_at': time.time(), 'status': 'running', 'passed': False, 'runs': [], 'loads': []}
    plan = ROOT / 'state/stage/plans/rehearsed.json'
    plan.parent.mkdir(parents=True, exist_ok=True)
    if not plan.exists():
        plan.write_bytes((ROOT / 'samples/stage/rehearsed-plan.json').read_bytes())
    if not args.resident:
        if module.other_compute_count():
            raise RuntimeError('Unrelated GPU workload present; resident qualification refused')
        records = json.loads((ROOT / 'state/gb10-qualification/measurements.json').read_text())['runs']
        chosen = []
        for lane, quant, loading in [('lead', 'MXFP4', 'no-mmap'), ('text', args.quant, 'mmap'), ('image', 'BF16', None), ('voice', 'publisher v1.0', None)]:
            matches = [r for r in records if r['lane'] == lane and r.get('quant') == quant and r.get('loading') == loading and r['status'] == 'measured' and r['qualification_scope'] == 'isolated_candidate']
            if not matches:
                raise RuntimeError('Missing isolated measurement: ' + lane + '/' + quant)
            chosen.append(matches[-1])
        predicted = module.memory()['available_bytes'] - sum(r['resident_memavailable_drop_bytes'] for r in chosen)
        row.update(predicted_memavailable_bytes=predicted, isolated_inputs=[{'lane': r['lane'], 'started_at': r['started_at'], 'resident_memavailable_drop_bytes': r['resident_memavailable_drop_bytes']} for r in chosen])
        if predicted < 10 * 2**30:
            row.update(status='admission_refused', reason='Sum of measured isolated residency would breach the 10 GiB floor before any concurrent workload')
            save(row)
            print(json.dumps(row), flush=True)
            return
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
                    return
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
    row['passed'] = (len(agents) == args.agent_runs and len(rushes) == max(5, args.rush_runs)
        and row['agent_p95_seconds'] <= 75 and max(rushes) <= 60
        and all(r['status'] == 'complete' for r in row['runs'])
        and row['memory']['min_available_bytes'] >= 10 * 2**30
        and row['memory']['swap_in_pages'] == row['memory']['swap_out_pages'] == 0)
    row.update(status='passed' if row['passed'] else 'failed', ended_at=time.time())
    save(row)
    print(json.dumps({k: v for k, v in row.items() if k != 'runs'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--quant', choices=['Q8_0', 'Q6_K', 'Q4_K_XL'], required=True)
    parser.add_argument('--resident', action='store_true', help='Use only the already verified, owned resident stack')
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--agent-runs', type=int, default=5)
    parser.add_argument('--rush-runs', type=int, default=5)
    parser.add_argument('--audio', action='store_true')
    asyncio.run(main(parser.parse_args()))
