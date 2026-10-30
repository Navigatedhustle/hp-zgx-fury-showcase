"""Optional training feasibility under the mandatory shared heavy lock."""
import fcntl,json,time
from atlas.config import ROOT
from atlas.telemetry import Telemetry
with open('/tmp/atlas-heavy.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    m=Telemetry().read();lane=m['app_memory_gb']*2**30;available=m['memory']['available_gb']*2**30
    # Four-billion parameters need at least BF16 gradient storage in addition to loaded weights.
    lower_bound_gradient_bytes=4_000_000_000*2
    result={'measured_at':time.time(),'available_gb':available/10**9,'lane_gb':lane/10**9,'lane_budget_gb':48,'headroom_gb':(48*10**9-lane)/10**9,'minimum_extra_gradient_gb':lower_bound_gradient_bytes/10**9,'status':'skipped','reason':'Loaded demo plus the minimum BF16 gradient storage exceeds the 48 GB lane limit, before optimizer/activations. Keep released checkpoint; no domain accuracy or training claim.'}
    assert lane+lower_bound_gradient_bytes>48*10**9
    (ROOT/'eval/v2/fine-tune-feasibility.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
