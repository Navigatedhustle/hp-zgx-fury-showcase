"""Pinned identity plus current service/process observations; no invented metrics."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def models(live):
    pins=json.loads((ROOT/'config/model-pins.json').read_text());creative=json.loads((ROOT/'config/creative-models.json').read_text());plan=json.loads((ROOT/'config/gb300.json').read_text())
    services=live.get('services',{});gateway=services.get('language',{}).get('data',{});lane=services.get('image',{}).get('data',{});memory=live.get('telemetry',{}).get('process_hbm_mib',{})
    rows=[]
    def add(repo,alias,component,ready,quant,slots,demos,allocation=None,**more):
        pin=pins.get(repo,{'revision':creative['revision'],'license':creative['license']})
        active=sum(v.get('model')==alias for v in gateway.get('active',{}).values()) if component in ('lead','text') else services.get(component,{}).get('data',{}).get('active',0)
        rows.append({'repo':repo,'alias':alias,'revision':pin['revision'],'license':pin['license'],'quantization':quant,'slots':slots,'demos':demos,'loaded':bool(ready),'state':'Busy' if active else 'Loaded' if ready else 'Unavailable','process_hbm_mib':memory.get(component),'allocation':allocation,'source':'config/model-pins.json + service readiness + verified controller process membership',**more})
    add('nvidia/DeepSeek-V4-Flash-NVFP4','fury-lead','lead',gateway.get('backends',{}).get('fury-lead'),'NVFP4',1,['Agent Factory','Vision executive brief','Translation terminology review','Trailer screenplay'],allocation=f"{plan['lead_gib']} GiB nominal engine budget",context=plan['lead_context'])
    add('unsloth/Qwen3.6-27B-NVFP4','unsloth/Qwen3.6-27B-NVFP4','text',gateway.get('backends',{}).get('unsloth/Qwen3.6-27B-NVFP4'),'NVFP4',4,['Atlas','Presentations','Factory specialists','Vision Lab','Translate Desk','Visible lead fallback'],allocation=f"{plan['qwen_gib']} GiB nominal engine budget",context=plan['qwen_context'])
    add('black-forest-labs/FLUX.2-klein-4B','FLUX.2-klein-4B','image',lane.get('flux_loaded'),'BF16','1 shared creative slot',['Image Studio','Trailer keyframes'],allocation='Shared creative process; per-model HBM split not exposed',placement=lane.get('flux_transformer'))
    add(creative['repo'],lane.get('video_model','Wan2.2-TI2V-5B'),'image',lane.get('video_loaded'),'BF16 transformer + FP32 VAE','1 shared creative slot',['Video Studio','Action Trailer'],allocation='Shares the same process with FLUX; counted once in telemetry',placement=lane.get('video_transformer'),adapters=[{'repo':a['repo'],'revision':a['revision'],'license':a['license']} for a in creative.get('reviewed_adapters',[])])
    add('hexgrad/Kokoro-82M','Kokoro-82M','tts',services.get('tts',{}).get('data',{}).get('ready'),'FP32',1,['Atlas voice','Trailer narrator'])
    add('csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26','Zipformer English','asr',services.get('asr',{}).get('data',{}).get('ready'),'INT8 / CPU','Not exposed',['Atlas speech recognition'],allocation='CPU; no GPU model allocation')
    return rows
