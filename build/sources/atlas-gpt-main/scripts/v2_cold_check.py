"""Exact-source cold-start audit of owned services, loopback binding and memory."""
import json,subprocess,time,urllib.request
from atlas.config import ROOT
from atlas.telemetry import Telemetry
healths={8200:'/api/health',8201:'/health',8202:'/v1/models',8203:'/v1/models',8204:'/health',8205:'/health',8206:'/health'}
subprocess.run([str(ROOT/'stop.sh')],check=True,cwd=ROOT)
start=time.perf_counter();subprocess.run([str(ROOT/'start.sh')],check=True,cwd=ROOT);ui=time.perf_counter()-start;ready={};samples=[];telemetry=Telemetry()
while time.perf_counter()-start<180:
    for port,endpoint in healths.items():
        if port in ready:continue
        try:
            if urllib.request.urlopen(f'http://127.0.0.1:{port}{endpoint}',timeout=.3).status==200:ready[port]=time.perf_counter()-start
        except Exception:pass
    m=telemetry.read();samples.append({'elapsed_s':time.perf_counter()-start,'lane_gb':m['app_memory_gb']*2**30/10**9,'available_gb':m['memory']['available_gb']*2**30/10**9})
    assert samples[-1]['lane_gb']<=48,samples[-1]
    assert samples[-1]['available_gb']>=16,samples[-1]
    if len(ready)==len(healths):break
    time.sleep(.7)
assert len(ready)==len(healths),ready
sockets=subprocess.check_output(['ss','-ltnp'],text=True)
owned_bindings=[line for line in sockets.splitlines() if any(f':{port} ' in line for port in healths)]
assert len(owned_bindings)==len(healths) and all('127.0.0.1:' in line for line in owned_bindings),owned_bindings
models=json.load(urllib.request.urlopen('http://127.0.0.1:8201/v1/models'));assert models['data'][0]['id']=='atlas-local'
report={'ui_ready_s':ui,'all_services_ready_s':max(ready.values()),'service_ready_s':ready,'bindings':owned_bindings,'peak_lane_gb':max(s['lane_gb'] for s in samples),'min_available_gb':min(s['available_gb'] for s in samples),'samples':samples,'model_alias':models['data'][0]['id']}
(ROOT/'eval/v2/cold-start.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
