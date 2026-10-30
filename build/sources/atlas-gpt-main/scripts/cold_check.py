"""Cold acceptance on owned services, with sampled resource evidence."""
import json,subprocess,time,socket
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import httpx
from atlas.config import ROOT,GOLDEN
from atlas.telemetry import Telemetry,own_pids
from atlas.offline_guard import install
install()

def listening(port):
 try:
  with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
 except OSError:return False

def run():
 report={'measured_at':datetime.now(ZoneInfo('America/Denver')).isoformat(),'samples':[]}
 report['stop']=subprocess.run([str(ROOT/'stop.sh')],cwd=ROOT,capture_output=True,text=True,timeout=35).stdout
 report['all_owned_ports_closed']=not any(listening(p) for p in range(8200,8206))
 assert report['all_owned_ports_closed'],'Owned service remains listening after stop'
 start=time.perf_counter();result=subprocess.run([str(ROOT/'start.sh')],cwd=ROOT,capture_output=True,text=True,timeout=45)
 report['start_exit']=result.returncode;report['start_output']=result.stdout+result.stderr
 assert result.returncode==0,report['start_output']
 report['ui_start_s']=time.perf_counter()-start
 checks={8200:'/api/health',8201:'/health',8202:'/v1/models',8203:'/v1/models',8204:'/health',8205:'/health'}
 ready={};telemetry=Telemetry()
 with httpx.Client(timeout=.7,trust_env=False) as c:
  while time.perf_counter()-start<175:
   report['samples'].append({'elapsed_s':time.perf_counter()-start,**telemetry.read()})
   for port,path in checks.items():
    if port in ready:continue
    try:
     response=c.get(f'http://127.0.0.1:{port}{path}');response.raise_for_status();ready[port]=time.perf_counter()-start
    except httpx.HTTPError:pass
   if len(ready)==len(checks):break
   time.sleep(1)
  report['ready_s_by_port']=ready;report['full_stack_ready']=len(ready)==len(checks)
  if report['full_stack_ready']:
   from scripts.services import alive
   while alive('startup') and time.perf_counter()-start<175:
    report['samples'].append({'elapsed_s':time.perf_counter()-start,**telemetry.read()});time.sleep(1)
   report['warmup_complete_s']=time.perf_counter()-start
   response=c.get('http://127.0.0.1:8200');response.raise_for_status();report['ui_html_loaded']='HP ZGX' in response.text
  c.timeout=30
  response=c.post('http://127.0.0.1:8200/api/query',json={'question':GOLDEN[0][2],'persona':'enterprise'});response.raise_for_status();answer=response.json()
  report['text_q1']={k:answer[k] for k in ['tool','headline','answer','grounding','routing','timings']}
  report['telemetry']=c.get('http://127.0.0.1:8200/api/telemetry').json()
 report['peak_mem_gib_estimate']=max(r['app_memory_gb'] for r in report['samples'])
 report['minimum_host_available_gib']=min(r['memory']['available_gb'] for r in report['samples'])
 (ROOT/'eval/cold-start.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k not in ['samples','telemetry']},indent=2),flush=True)
 assert report['full_stack_ready'] and report['ui_start_s']<180
 assert report['text_q1']['tool']=='forecast_quarter' and report['text_q1']['grounding']['passed']
 assert report['peak_mem_gib_estimate']<=48 and report['minimum_host_available_gib']>=16
 subprocess.run([str(ROOT/'.venv/bin/python'),'-m','scripts.voice_browser_qa'],cwd=ROOT,timeout=90,check=True)
if __name__=='__main__':run()
