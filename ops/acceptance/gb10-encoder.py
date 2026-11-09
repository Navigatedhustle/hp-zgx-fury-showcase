#!/usr/bin/env python3
"""Isolated real-image equivalence check. Requires all other model lanes stopped.

Run explicitly with .model-venv/bin/python; outputs remain in ignored state/.
This checks the image adapter, not Gate 1 or stage readiness.
"""
import os,sys,json,threading,time,gc,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
os.environ.update(FURY_PROFILE='gb10',FURY_GB10_FLUX_ENCODER='fp8',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.path.insert(0,str(root/'ops'))
import control
spec=importlib.util.spec_from_file_location('benchmark',root/'ops/gb10-benchmark.py');benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)
if any(control.discover(name) for name in control.COMPONENTS) or benchmark.other_compute_count():
 raise SystemExit('Isolated image check requires all model lanes stopped; inspect ops/control.py status')
headers=root/'.local-debs/extracted/usr/include';os.environ['C_INCLUDE_PATH']=str(headers)+':'+str(headers/'python3.12')
from showcase_app.creative import CreativeLane
import torch
import numpy as np
from PIL import Image
folder=root/'state/gb10-qualification/encoder-comparison';folder.mkdir(parents=True,exist_ok=True)
lane=CreativeLane();lane.load();wrapped=lane.flux.text_encoder;original=wrapped.encoder
prompt='Original editorial illustration of a small navy desktop computer beside a folded paper landscape, calm blue lighting, no text, no logo.'
inputs=lane.flux.tokenizer([prompt],padding='max_length',max_length=512,truncation=True,return_tensors='pt').to('cuda')
with torch.inference_mode():
 a=original(**inputs,output_hidden_states=True,use_cache=False)
 b=wrapped(**inputs,output_hidden_states=True,use_cache=False)
 equal=all(torch.equal(a.hidden_states[k],b.hidden_states[k]) for k in (9,18,27))
 assert equal
assert sum(p.numel() for p in original.parameters())==sum(p.numel() for p in wrapped.parameters())
del a,b,inputs;gc.collect();torch.cuda.empty_cache()
metrics={}
for name,encoder in [('full',original),('hidden_states',wrapped)]:
 lane.flux.text_encoder=encoder
 job={};path=folder/(name+'.png');began=time.monotonic()
 m=lane.run('image',prompt,path,threading.Event(),{'width':1344,'height':768,'batch':1,'seed':42},job)
 metrics[name]={'seconds':time.monotonic()-began,**m}
a=np.asarray(Image.open(folder/'full.png')).astype(np.int16);b=np.asarray(Image.open(folder/'hidden_states.png')).astype(np.int16)
result={'real_encoder_hidden_states_exactly_equal':equal,'all_parameters_retained':True,'identical_rendered_pixels':bool(np.array_equal(a,b)),'max_pixel_difference':int(np.abs(a-b).max()),'metrics':metrics}
(folder/'verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2),flush=True)
if not result['identical_rendered_pixels']:
 raise SystemExit('Image equivalence failed; inspect private outputs')
