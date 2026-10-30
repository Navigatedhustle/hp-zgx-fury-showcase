"""Truthful host route, traffic and resource measurements. No network probes."""
import os,subprocess,time
from pathlib import Path
from atlas.config import ROOT

def interfaces():
 results={}
 for p in Path('/sys/class/net').iterdir():
  if p.name=='lo':continue
  try:results[p.name]={'tx':int((p/'statistics/tx_bytes').read_text()),'rx':int((p/'statistics/rx_bytes').read_text()),'state':(p/'operstate').read_text().strip()}
  except OSError:continue
 return results
def network_routes():
 routes=[]
 for line in Path('/proc/net/route').read_text().splitlines()[1:]:
  p=line.split()
  if p[1]=='00000000' and int(p[3],16)&1:routes.append(p[0])
 ipv6=Path('/proc/net/ipv6_route')
 if ipv6.exists():
  for line in ipv6.read_text().splitlines():
   p=line.split()
   if len(p)>=10 and p[0]=='0'*32 and p[1]=='00' and int(p[8],16)&1 and p[-1]!='lo':routes.append(p[-1])
 return sorted(set(routes))
def memory():
 m={}
 for line in Path('/proc/meminfo').read_text().splitlines():
  k,v=line.split(':',1);m[k]=int(v.strip().split()[0])*1024
 return {'total_gb':m['MemTotal']/2**30,'available_gb':m['MemAvailable']/2**30,'used_gb':(m['MemTotal']-m['MemAvailable'])/2**30}
def own_pids():
 pids={os.getpid()}
 for f in (ROOT/'runtime').glob('*.server.pid'):
  try:
   pid=int(f.read_text())
   if Path(f'/proc/{pid}/cwd').resolve()==ROOT:pids.add(pid)
  except (ValueError,OSError):pass
 pending=list(pids)
 while pending:
  pid=pending.pop()
  try:children=[int(x) for x in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
  except OSError:continue
  for child in children:
   if child not in pids:pids.add(child);pending.append(child)
 return pids
def process_pss(pids):
 total=0
 for pid in pids:
  try:
   s=Path(f'/proc/{pid}/smaps_rollup').read_text();total+=int(next(l for l in s.splitlines() if l.startswith('Pss:')).split()[1])*1024
  except (OSError,StopIteration):pass
 return total/2**30
class Telemetry:
 def __init__(self):
  self.started=time.time();self.baseline=interfaces();self.peak=0;self.gpu=None;self.gpu_memory=0;self.last_gpu=0
 def read(self):
  now=interfaces();delta=sum(max(0,v['tx']-self.baseline.get(k,v)['tx']) for k,v in now.items())
  routes=network_routes();mem=memory();pids=own_pids();pss=process_pss(pids)
  if time.time()-self.last_gpu>3:
   try:
    s=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1)
    p=s.stdout.strip().split(',');self.gpu={'utilization':float(p[0]),'temperature':float(p[1]),'power_w':float(p[2])}
    s=subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1)
    self.gpu_memory=sum(float(p[1]) for line in s.stdout.splitlines() if len(p:=line.split(','))==2 and int(p[0]) in pids)/1024
   except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):self.gpu=None
   self.last_gpu=time.time()
  # On unified-memory hardware these views can overlap. The sum is a
  # conservative estimate/bound, clearly labeled, never presented as exact RSS.
  bound=pss+self.gpu_memory;self.peak=max(self.peak,bound)
  return {'offline':not routes,'routes':routes,'non_loopback_tx_bytes':delta,'tx_label':'Upper bound on cloud-bound data; all host outbound traffic, including other processes. Not attributed to Atlas.','interfaces':now,'memory':mem,'app_memory_gb':bound,'app_cpu_pss_gb':pss,'app_gpu_allocated_gb':self.gpu_memory,'memory_label':'Estimate / upper bound: process PSS + reported GPU allocations; unified-memory overlap may double-count.','peak_app_memory_gb':self.peak,'gpu':self.gpu,'uptime_s':time.time()-self.started,'cloud_endpoints_configured':0,'runtime_network_policy':'Loopback inference only'}
