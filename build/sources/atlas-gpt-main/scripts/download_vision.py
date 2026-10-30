from pathlib import Path
import requests,hashlib
p=Path('models/rf-detr-nano.pth');url='https://storage.googleapis.com/rfdetr/nano_coco/checkpoint_best_regular.pth'
if not p.exists():
 with requests.get(url,stream=True,timeout=60) as r:
  r.raise_for_status()
  with p.open('wb') as f:
   for chunk in r.iter_content(1048576):f.write(chunk)
assert hashlib.md5(p.read_bytes()).hexdigest()=='fb6504cce7fbdc783f7a46991f07639f'
print('Verified RF-DETR Nano weights',p.stat().st_size,flush=True)
