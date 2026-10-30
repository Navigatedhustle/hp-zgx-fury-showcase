#!/usr/bin/env python3
"""Read-only hardware and prerequisite checks. Never changes the host."""
import argparse,ctypes.util,json,os,platform,shutil,socket,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def check(ports=False):
 errors=[];info={'os':platform.platform(),'architecture':platform.machine(),'python':platform.python_version()}
 release=Path('/etc/os-release').read_text() if Path('/etc/os-release').exists() else ''
 if platform.system()!='Linux' or platform.machine()!='aarch64' or 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:errors.append('Only Ubuntu 24.04 ARM64 on a GB300 has been tested.')
 if sys.version_info[:2]!=(3,12):errors.append('Python 3.12 is required.')
 missing=[tool for tool in ['curl','tar','xz','gcc','g++','make','bwrap','dpkg-deb','apt-get','nvidia-smi','prlimit'] if not shutil.which(tool)]
 if missing:errors.append('Missing host prerequisites: '+', '.join(missing)+'. See docs/PREREQUISITES.md; install through your administrator.')
 if not ctypes.util.find_library('sndfile'):errors.append('Missing libsndfile1.')
 if not Path('/usr/local/cuda/bin/nvcc').exists():errors.append('CUDA toolkit /usr/local/cuda/bin/nvcc required for kernel JIT; tested 13.3. No automatic toolkit/driver install.')
 memory={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())};info['ram_gib']=round(memory['MemTotal']/1024**3,2);info['available_ram_gib']=round(memory['MemAvailable']/1024**3,2)
 if memory['MemTotal']<700*1024**3:errors.append('This complete profile requires at least 700 GiB system RAM; smaller hosts are unverified.')
 info['disk_free_gib']=round(shutil.disk_usage(ROOT).free/1024**3,2)
 required=40 if (ROOT/'state/setup.json').exists() else 350
 if info['disk_free_gib']<required:errors.append(f'Require {required} GiB free disk for this stage.')
 try:
  rows=subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,memory.total,memory.free,driver_version','--format=csv,noheader,nounits'],text=True).splitlines();gpu=os.getenv('FURY_GPU','0');row=rows[int(gpu)] if gpu.isdigit() else next(r for r in rows if r.split(',')[1].strip()==gpu);name,uuid,total,free,driver=[s.strip() for s in row.split(',')];info['gpu']={'name':name,'memory_mib':int(total),'free_mib':int(free),'driver':driver}
  if 'GB300' not in name or int(total)<256000:errors.append('The complete DeepSeek+Qwen profile requires the tested GB300 with 256703 MiB HBM; no smaller GPU support is claimed.')
 except Exception:errors.append('Cannot inspect selected NVIDIA GPU (FURY_GPU defaults to index 0).')
 if shutil.which('bwrap'):
  sys.path.insert(0,str(ROOT/'build/sources/fury_agent_factory'));from devteam_sandbox import available
  if not available():errors.append('Bubblewrap user namespaces are blocked. An administrator must enable scoped support; see docs/PREREQUISITES.md. No sandbox bypass is available.')
 if ports:
  from control import COMPONENTS,discover,port_open,ready
  occupied=[]
  for name,spec in COMPONENTS.items():
   if port_open(spec['port']):
    owned=discover(name);occupied.append({'component':name,'port':spec['port'],'owned':bool(owned),'ready':bool(owned and ready(name))})
    if not owned:errors.append(f"Port {spec['port']} is occupied by another installation/process; it will not be adopted or stopped.")
  info['occupied_ports']=occupied
 print(json.dumps({'checks':info,'errors':errors},indent=2))
 return not errors
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--ports',action='store_true');a=p.parse_args();sys.exit(0 if check(a.ports) else 1)
