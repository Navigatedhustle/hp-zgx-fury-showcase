import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import sys,json,torch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from transformers import Qwen3Config,Qwen3ForCausalLM
from torchao.quantization import Float8WeightOnlyConfig,quantize_
from showcase_app.gb10_encoder import restore_conditioning_ties
model=Qwen3ForCausalLM(Qwen3Config(vocab_size=128,hidden_size=64,intermediate_size=128,num_hidden_layers=4,num_attention_heads=4,num_key_value_heads=2,tie_word_embeddings=True)).to(torch.bfloat16).eval()
quantize_(model,Float8WeightOnlyConfig(set_inductor_config=False))
ids=torch.tensor([[1,2,3,4,5,6]])
with torch.inference_mode():
 before=model.model(ids,output_hidden_states=True,use_cache=False).hidden_states
 info=restore_conditioning_ties(model)
 after=model.model(ids,output_hidden_states=True,use_cache=False).hidden_states
 assert len(before)==len(after)
 errors=[(a-b).abs().max().item() for a,b in zip(before,after)]
 assert max(errors)==0 and info['restored']
report={'scope':'Pinned Qwen3 and torchao on a small real Qwen3 architecture, before/after restoring the quantization-broken embedding tie','maximum_hidden_state_difference':max(errors),'checkpoint_weight_sharing_restored':True,'layers_compared':len(errors),'metadata':info}
(ROOT/'state/stage').mkdir(parents=True,exist_ok=True)
(ROOT/'state/stage/conditioning-proof.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
