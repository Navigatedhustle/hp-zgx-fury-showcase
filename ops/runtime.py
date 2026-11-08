"""Verified live component definitions; all paths are relative to the clone."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COMPONENTS={
 'text':{'port':8000,'health':'/health','model':'unsloth/Qwen3.6-27B-NVFP4','command':['bash','ops/serve-text.sh']},
 'gateway':{'port':8001,'health':'/health','command':['.venv/bin/python','-m','uvicorn','showcase_app.gateway:app','--host','127.0.0.1','--port','8001']},
 'asr':{'port':8202,'health':'/v1/models','model':'Zipformer English streaming int8 (CPU)','command':['.venv/bin/python','-m','uvicorn','showcase_app.asr:app','--host','127.0.0.1','--port','8202']},
 'tts':{'port':8204,'health':'/health','model':'hexgrad/Kokoro-82M','command':['.model-venv/bin/python','-m','uvicorn','atlas.tts_server:app','--host','127.0.0.1','--port','8204','--app-dir','build/sources/atlas-gpt-main']},
 'atlas':{'port':8200,'health':'/api/health','command':['.venv/bin/python','-m','uvicorn','atlas.server:app','--host','127.0.0.1','--port','8200','--app-dir','build/sources/atlas-gpt-main']},
 'slides':{'port':8765,'health':'/api/health','command':['.venv/bin/python','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765','--app-dir','build/sources/html_builder-main/backend']},
 'agent':{'port':8501,'health':'/health','command':['.venv/bin/python','-m','uvicorn','api:app','--app-dir','build/sources/fury_agent_factory','--host','127.0.0.1','--port','8501']},
 'image':{'port':8800,'health':'/health','model':'black-forest-labs/FLUX.2-klein-4B','command':['.model-venv/bin/python','-m','uvicorn','showcase_app.image:app','--host','127.0.0.1','--port','8800']},
 'operator':{'port':8080,'health':'/api/live','command':['.venv/bin/python','-m','uvicorn','showcase_app.operator:app','--host','127.0.0.1','--port','8080']}}
# The full GB300 profile always loads the DeepSeek lead.
_lead={'port':8100,'health':'/health','model':'fury-lead','command':['bash','ops/serve-lead.sh'],'enabled':True,'startup_timeout':3600}
COMPONENTS=dict([('text',COMPONENTS['text']),('lead',_lead)]+[(k,v) for k,v in COMPONENTS.items() if k!='text'])
# Bound shutdown even when a browser keeps an SSE/WebSocket connection open.
for spec in COMPONENTS.values():
 if 'uvicorn' in spec['command']:spec['command']+=['--timeout-graceful-shutdown','15']
SERVE={443:8080,8200:8200,8501:8501,8765:8765,8800:8800}
if os.getenv('FURY_PROFILE')=='gb10':
 from gb10_runtime import components
 COMPONENTS=components();SERVE={}
def environment():
 if os.getenv('FURY_PROFILE')=='gb10':
  from gb10_runtime import environment as gb10_environment
  return gb10_environment()
 r=ROOT
 import json
 plan=json.loads((ROOT/'config/gb300.json').read_text())
 os.environ['CUDA_VISIBLE_DEVICES']=os.getenv('FURY_GPU','0')
 os.environ['FURY_DEV_LEAD_CONTEXT']=str(plan['lead_context'])
 return {**os.environ,'C_INCLUDE_PATH':str(r/'.local-debs/extracted/usr/include')+':'+str(r/'.local-debs/extracted/usr/include/python3.12'),'LLM_BASE_URL':'http://127.0.0.1:8001/slides/v1','LLM_MODEL':'unsloth/Qwen3.6-27B-NVFP4','LLM_MOCK':'false','VISION':'off','THINKING_PLAN':'false','GUIDED_JSON':'false','DATA_DIR':str(r/'state/slides'),'LLM_MAX_CONCURRENCY':'2','QA_MAX_REPAIRS':'0','ATLAS_LLM_BASE':'http://127.0.0.1:8001/atlas','FURY_BASE_URL':'http://127.0.0.1:8001/agent/v1','FURY_MODEL':'unsloth/Qwen3.6-27B-NVFP4','FURY_LOCATION':'Fury host','FURY_MAX_WORKFLOWS':'1','FURY_MAX_INFLIGHT':'3','FURY_MAX_OUTPUT':'1200','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','DO_NOT_TRACK':'1','PYTHONUNBUFFERED':'1','LOGURU_LEVEL':'WARNING','ATLAS_DOCUMENTS':'0','ATLAS_FEED':'0'}
