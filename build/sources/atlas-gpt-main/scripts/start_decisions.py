import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/kev'))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',KEV_CUDA_GRAPHS='0',KEV_FUSED='0',KEV_DTYPE='bf16',KEV_PREFIX_MAX_TOKENS='4096',OMP_NUM_THREADS='4')
sys.path.insert(0,str(ROOT))
from atlas.offline_guard import install
install()
from kev.serve import main
sys.argv=['kev.serve','--run',json.loads((ROOT/'models/decisions.json').read_text())['path'],'--host','127.0.0.1','--port','8203']
main()
