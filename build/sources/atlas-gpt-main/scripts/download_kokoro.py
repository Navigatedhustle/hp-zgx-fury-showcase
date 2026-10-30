import os,json
from pathlib import Path
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
from huggingface_hub import snapshot_download
p=snapshot_download('hexgrad/Kokoro-82M',allow_patterns=['config.json','kokoro-v1_0.pth','voices/af_heart.pt','LICENSE','README.md'],token=False)
Path('models/kokoro.json').write_text(json.dumps({'repo':'hexgrad/Kokoro-82M','path':p}))
print('READY Kokoro',p,flush=True)
