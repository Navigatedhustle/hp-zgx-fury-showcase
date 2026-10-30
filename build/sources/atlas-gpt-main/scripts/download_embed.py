"""Build-time only, revision-pinned download after model-card license verification."""
import json,urllib.request,sys
from pathlib import Path
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
model='nvidia/llama-nemotron-embed-1b-v2'
card=urllib.request.urlopen('https://huggingface.co/'+model+'/raw/main/README.md').read().decode()
assert 'This model is ready for commercial use.' in card
assert 'NVIDIA Open Model License Agreement' in card
api=json.load(urllib.request.urlopen('https://huggingface.co/api/models/'+model))
revision=api['sha'];dest=ROOT/'models/embed'
(ROOT/'eval/model-cards/nvidia--llama-nemotron-embed-1b-v2.md').write_text(card)
snapshot_download(model,revision=revision,local_dir=dest,token=False,allow_patterns=['*.json','*.py','*.safetensors','*.model','*.txt','README.md','LICENSE*','modules/*','1_Pooling/*'],max_workers=3)
(ROOT/'models/embed.json').write_text(json.dumps({'id':model,'revision':revision,'path':str(dest),'license':'NVIDIA Open Model License; additional Llama 3.2 terms'},indent=2))
print('Embedding snapshot ready',revision)
