import os,time
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1')
from rfdetr import RFDETRNano
from PIL import Image
import torch
start=time.perf_counter();torch.set_num_threads(4)
m=RFDETRNano(pretrain_weights=str(Path('models/rf-detr-nano.pth').resolve()),device='cuda')
print('Loaded',time.perf_counter()-start,flush=True)
for i in range(3):
 s=time.perf_counter();d=m.predict(Image.new('RGB',(640,360),'white'),threshold=.45)
 print('predict',i,(time.perf_counter()-s)*1000,'detections',len(d),flush=True)
