"""One server-side source for physical telemetry and measured engine throughput."""
import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
history = deque(maxlen=300)
previous_cpu = None
previous_tokens = {}


def number(value):
    try:return float(value.strip())
    except (ValueError, AttributeError):return None


def hardware():
    global previous_cpu
    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.used,memory.total,memory.free,utilization.gpu,power.draw,temperature.gpu', '--format=csv,noheader,nounits'], text=True, timeout=3).splitlines()[0].split(',')
    gpu = dict(zip(('name', 'hbm_used_mib', 'hbm_total_mib', 'hbm_free_mib', 'utilization', 'power_w', 'temperature_c'), [raw[0].strip(), *map(number, raw[1:])]))
    nodes = [p for p in Path('/sys/devices/system/node').glob('node[0-9]*') if (p/'cpulist').read_text().strip()]
    grace = {}
    if len(nodes) == 1:
        values = {line.split()[2].rstrip(':'):int(line.split()[3])*1024 for line in (nodes[0]/'meminfo').read_text().splitlines()}
        grace = {'total_bytes':values['MemTotal'], 'free_bytes':values['MemFree'], 'used_bytes':values['MemTotal']-values['MemFree'], 'available_bytes':None, 'node':nodes[0].name, 'note':'Used includes Linux page cache; per-node MemAvailable is not exposed.'}
    row = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    total, idle = sum(row), row[3]+row[4]
    cpu = None
    if previous_cpu and total > previous_cpu[0]:cpu = 100*(1-(idle-previous_cpu[1])/(total-previous_cpu[0]))
    previous_cpu = total, idle
    processes = {}
    try:
        text = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],text=True,timeout=3)
        allocations = {int(p):number(m) for p,m in (line.split(',') for line in text.splitlines())}
        registry = json.loads((ROOT/'state/supervisor.json').read_text())
        for name,spec in registry.items():
            processes[name] = sum(allocations.get(m['pid'],0) or 0 for m in spec.get('members',[]))
    except (OSError, ValueError, subprocess.SubprocessError):pass
    return {'gpu':gpu,'grace':grace,'cpu_percent':cpu,'cpu_cores':os.cpu_count(),'nvme_free_bytes':shutil.disk_usage(ROOT).free,'process_hbm_mib':processes}


async def sample(live):
    now = time.time()
    machine = await asyncio.to_thread(hardware)
    rates = {}
    async with httpx.AsyncClient(trust_env=False,timeout=2) as client:
        async def tokens(name,port):
            try:
                response = await client.get(f'http://127.0.0.1:{port}/metrics');response.raise_for_status()
                values = re.findall(r'^vllm:generation_tokens_total(?:\{[^\n]*\})?\s+([\d.eE+-]+)',response.text,re.M)
                if not values:return name,None
                current = sum(float(v) for v in values)
                previous = previous_tokens.get(name);previous_tokens[name] = now,current
                return name,max(0,(current-previous[1])/(now-previous[0])) if previous and now>previous[0] and current>=previous[1] else None
            except (httpx.HTTPError,ValueError):return name,None
        rates = dict(await asyncio.gather(tokens('qwen',8000),tokens('deepseek',8100)))
    services = live.get('services',{})
    gateway = services.get('language',{}).get('data',{})
    creative = services.get('image',{}).get('data',{})
    lanes = []
    for name,alias in [('DeepSeek','fury-lead'),('Qwen','unsloth/Qwen3.6-27B-NVFP4')]:
        running = [v for v in gateway.get('active',{}).values() if v.get('model')==alias]
        lanes.append({'name':name,'active':len(running),'queued':sum(v.get('model')==alias for v in gateway.get('queued',{}).values()),'routing':[v['routing'] for v in running if v.get('routing')], 'ready':gateway.get('backends',{}).get(alias,False)})
    for name,kind in [('FLUX','image'),('Video','video')]:
        lanes.append({'name':name,'active':sum(j.get('kind')==kind and j.get('status')=='generating' for j in creative.get('jobs',[])),'queued':sum(j.get('kind')==kind and j.get('status')=='queued' for j in creative.get('jobs',[])),'ready':creative.get('flux_loaded' if kind=='image' else 'video_loaded',False)})
    for name,key in [('Kokoro','tts'),('ASR','asr')]:
        voice = services.get(key,{}).get('data',{})
        lanes.append({'name':name,'active':voice.get('active',0),'queued':voice.get('queued',0),'last_request':voice.get('last_request',0),'ready':voice.get('ready',False)})
    total_rate = sum(v for v in rates.values() if v is not None) if any(v is not None for v in rates.values()) else None
    result = {'at':now,**machine,'tokens_per_second':total_rate,'tokens_by_engine':rates,'token_source':'Difference of native vLLM generation_tokens_total counters over the server sampling interval; all configured text inference uses the local gateway.','active_jobs':len(gateway.get('active',{}))+creative.get('active',0),'queued_jobs':len(gateway.get('queued',{}))+creative.get('queued',0),'job_scope':'Gateway inference requests plus creative jobs; workflow stage rows are shown separately.','external_api_calls':gateway.get('external_api_calls'),'external_counter_since':gateway.get('external_counter_since'),'local_only':gateway.get('local_only',False),'lanes':lanes,'routing':gateway.get('recent_routing',[]),'creative':creative}
    history.append({k:result[k] for k in ('at','gpu','grace','cpu_percent','tokens_per_second','tokens_by_engine','active_jobs','queued_jobs')})
    result['inference_jobs']=[{'id':cid,**value,'status':state} for state,key in [('active','active'),('queued','queued')] for cid,value in gateway.get(key,{}).items()]
    result['history'] = list(history)
    return result
