"""Explicit, fail-closed launch profile for one GB300."""
import json,os,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from showcase_app.runtime_privacy import service_policy
service_policy(ROOT)
kind=sys.argv[1];plan=json.loads((ROOT/'config/gb300.json').read_text())
if kind not in ('lead','qwen'):raise SystemExit('Unknown model role')
os.environ.update(VLLM_HOST_IP='127.0.0.1',GLOO_SOCKET_IFNAME='lo',NCCL_SOCKET_IFNAME='lo',CUDA_VISIBLE_DEVICES=os.getenv('FURY_GPU','0'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',DO_NOT_TRACK='1')
if kind=='lead':
 binary=ROOT/'.deepseek-venv/bin/vllm';model=ROOT/'models/DeepSeek-V4-Flash-NVFP4';alias='fury-lead';port='8100';context=plan['lead_context'];seq=plan['lead_sequences'];fraction=plan['lead_fraction']
 extra=['--tokenizer-mode','deepseek_v4','--kv-cache-dtype','fp8','--block-size','256','--reasoning-parser','deepseek_v4','--max-num-batched-tokens',str(plan.get('lead_prefill',8192))]
else:
 binary=ROOT/'.model-venv/bin/vllm';model=ROOT/'models/Qwen3.6-27B-NVFP4';alias='unsloth/Qwen3.6-27B-NVFP4';port='8000';context=plan['qwen_context'];seq=plan['qwen_sequences'];fraction=plan['qwen_fraction']
 extra=['--enable-prefix-caching','--limit-mm-per-prompt','{"image":16}','--reasoning-parser','qwen3','--max-num-batched-tokens',str(plan.get('qwen_prefill',16384))]
# Kernel JIT helpers (including ninja) must come from the selected isolated runtime.
os.environ['PATH']=str(binary.parent)+os.pathsep+os.environ.get('PATH','')
os.environ['PYTHONPATH']=str(ROOT)
rows=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.total,memory.free','--format=csv,noheader,nounits'],text=True)
gpu=os.getenv('FURY_GPU','0')
selected=([rows.splitlines()[int(gpu)].split(',')] if gpu.isdigit() and int(gpu)<len(rows.splitlines()) else [s.split(',') for s in rows.splitlines() if s.split(',')[0].strip()==gpu])
if len(selected)!=1:raise SystemExit('Planned GPU is missing')
total,free=map(float,selected[0][1:])
if free/1024 < total/1024*fraction+plan['reserve_gib']:raise SystemExit('Insufficient free HBM for planned engine plus reserve. Stop only verified showcase services using their controller.')
args=[str(binary),'serve',str(model),'--served-model-name',alias,'--host','127.0.0.1','--allowed-origins','[]','--middleware','showcase_app.security.ModelLifecycleGuard','--middleware','showcase_app.security.RequestGuard','--middleware','showcase_app.security.HostGuard','--port',port,'--tensor-parallel-size','1','--max-model-len',str(context),'--max-num-seqs',str(seq),'--gpu-memory-utilization',str(fraction),*extra]
os.execv(str(binary),args)
