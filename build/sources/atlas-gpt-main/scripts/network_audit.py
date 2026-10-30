"""Sample owned TCP sockets without altering the host's networking."""
import ipaddress,json,time
from pathlib import Path
from atlas.config import ROOT
from atlas.telemetry import own_pids,network_routes,interfaces

def address(hexadecimal,ipv6):
 data=bytes.fromhex(hexadecimal)
 if ipv6:data=b''.join(data[i:i+4][::-1] for i in range(0,16,4))
 else:data=data[::-1]
 return str(ipaddress.ip_address(data))

def connections():
 inodes=set()
 for pid in own_pids():
  try:
   for fd in Path(f'/proc/{pid}/fd').iterdir():
    try:target=fd.readlink().as_posix()
    except OSError:continue
    if target.startswith('socket:['):inodes.add(target[8:-1])
  except OSError:pass
 result=[]
 for name in ['tcp','tcp6']:
  for row in Path('/proc/net/'+name).read_text().splitlines()[1:]:
   fields=row.split()
   if fields[9] not in inodes:continue
   host,port=fields[2].split(':');remote=address(host,name=='tcp6');remote_port=int(port,16)
   if remote_port:result.append({'remote':remote,'port':remote_port,'state':fields[3],'loopback':ipaddress.ip_address(remote).is_loopback})
 return result

def run():
 report={'duration_s':45,'method':'Owned PID file-descriptor socket inodes matched to /proc/net/tcp and tcp6; sampled once per second. Listening sockets excluded.','samples':[],'host_default_routes':network_routes(),'host_interface_start':interfaces()}
 for _ in range(45):
  report['samples'].append({'at':time.time(),'connections':connections()});time.sleep(1)
 report['non_loopback_owned_connections']=[c for s in report['samples'] for c in s['connections'] if not c['loopback']]
 report['host_interface_end']=interfaces();report['physical_disconnect_tested']=False
 (ROOT/'eval/network-audit.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2),flush=True)
 assert not report['non_loopback_owned_connections']
if __name__=='__main__':run()
