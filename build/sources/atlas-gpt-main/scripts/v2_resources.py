import json,time
from atlas.config import ROOT
from atlas.telemetry import Telemetry
samples=[];t=Telemetry()
for _ in range(45):
    m=t.read();sample={'at':time.time(),'lane_gb':m['app_memory_gb']*2**30/10**9,'available_gb':m['memory']['available_gb']*2**30/10**9};samples.append(sample);assert sample['lane_gb']<=48 and sample['available_gb']>=16,sample;time.sleep(1)
report={'samples':samples,'peak_lane_gb':max(s['lane_gb'] for s in samples),'min_available_gb':min(s['available_gb'] for s in samples),'method':'Owned process PSS plus owned GPU allocations: conservative estimate on unified memory; sampled during generated microphone/voice/code checks.'};(ROOT/'eval/v2/resources.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
