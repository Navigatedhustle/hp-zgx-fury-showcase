#!/usr/bin/env python3
"""Linux process supervisor: identity-checked sessions, readiness and verified shutdown."""
import argparse,fcntl,json,os,re,signal,socket,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
from runtime import ROOT,COMPONENTS,SERVE,environment
STATE=ROOT/'state';STOP_REQUEST=STATE/'stop-request';PIDFILE=STATE/'processes.json';REGISTRY=STATE/'supervisor.json'

def process(pid):
 try:
  p=Path('/proc')/str(pid);stat=p.joinpath('stat').read_text().rsplit(') ',1)[1].split()
  if stat[0]=='Z':return None
  return {'pid':int(pid),'ppid':int(stat[1]),'uid':p.stat().st_uid,'cwd':str(p.joinpath('cwd').resolve()),'exe':str(p.joinpath('exe').resolve()),'start':stat[19],'pgid':int(stat[2]),'sid':int(stat[3]),'args':p.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')}
 except (OSError,ValueError):return None

def processes():
 return [row for p in Path('/proc').iterdir() if p.name.isdigit() and (row:=process(p.name))]

def identity(row,name):
 if not row or row['uid']!=os.getuid() or row['cwd']!=str(ROOT):return False
 args=row['args'];cmd=COMPONENTS[name]['command']
 if name=='lead':
  if args==['bash','ops/serve-lead.sh']:return True
  if len(args)>2 and args[-2:]==['ops/launch-frankfurt-model.py','lead']:return Path(args[0]).resolve()==(ROOT/'.venv/bin/python').resolve()
  return len(args)>3 and Path(args[1]).name=='vllm' and Path(args[0]).resolve()==(ROOT/'.deepseek-venv/bin/python').resolve() and args[2:4]==['serve',str(ROOT/'models/DeepSeek-V4-Flash-NVFP4')] and '--served-model-name' in args and args[args.index('--served-model-name')+1]=='fury-lead' and '--port' in args and args[args.index('--port')+1]=='8100'
 if name=='text':
  if Path(args[0]).resolve()!=(ROOT/'.model-venv/bin/python').resolve() and args!=['bash','ops/serve-text.sh'] and not (len(args)>2 and args[-2:]==['ops/launch-frankfurt-model.py','qwen']):return False
  if len(args)>2 and args[-2:]==['ops/launch-frankfurt-model.py','qwen']:return Path(args[0]).resolve()==(ROOT/'.venv/bin/python').resolve()
  if args==['bash','ops/serve-text.sh']:return True
  return len(args)>3 and Path(args[1]).name=='vllm' and args[2:4]==['serve',str(ROOT/'models/Qwen3.6-27B-NVFP4')] and '--served-model-name' in args and args[args.index('--served-model-name')+1]=='unsloth/Qwen3.6-27B-NVFP4' and '--port' in args and args[args.index('--port')+1]=='8000'
 normalised=[a.replace('showcase.', 'showcase_app.') if a.startswith('showcase.') else a for a in args]
 allowed=[cmd[1:]]
 if cmd[-2:]==['--timeout-graceful-shutdown','15']:allowed.append(cmd[1:-2])
 return normalised[1:] in allowed and Path(args[0]).resolve()==(ROOT/cmd[0]).resolve()

def fingerprint(row):return {k:row[k] for k in ('pid','start','pgid','uid','cwd','exe')}
def unchanged(saved):
 now=process(saved['pid']);return now and fingerprint(now)==saved

def discover(name):
 rows=[r for r in processes() if identity(r,name)]
 if len(rows)>1:raise RuntimeError('Multiple verified '+name+' processes; refusing ambiguous control.')
 if rows and rows[0]['pid']!=rows[0]['pgid']:raise RuntimeError(name+' is not isolated in its own process group.')
 return rows[0] if rows else None

def port_open(port):
 with socket.socket() as s:s.settimeout(.25);return s.connect_ex(('127.0.0.1',port))==0

def ready(name):
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(f'http://127.0.0.1:{COMPONENTS[name]["port"]}{COMPONENTS[name]["health"]}',timeout=2) as response:
   raw=response.read();data=json.loads(raw) if raw.startswith(b'{') else {}
   if name not in ('text','lead') and (response.headers.get_content_type()!='application/json' or not isinstance(data,dict)):return False
   if data.get('ready',data.get('llm',{}).get('ok',True)) is not True:return False
   if name in ('text','lead'):
    with opener.open(f'http://127.0.0.1:{COMPONENTS[name]["port"]}/v1/models',timeout=2) as model_response:
     models=json.load(model_response).get('data',[])
    folder='DeepSeek-V4-Flash-NVFP4' if name=='lead' else 'Qwen3.6-27B-NVFP4'
    return any(m.get('id')==COMPONENTS[name]['model'] and Path(m.get('root','')).resolve()==(ROOT/'models'/folder).resolve() for m in models)
   return True
 except (OSError,ValueError,urllib.error.URLError):return False

def save(registry):
 temp=REGISTRY.with_suffix('.tmp');temp.write_text(json.dumps(registry,indent=2));temp.replace(REGISTRY)
 PIDFILE.write_text(json.dumps({n:r['leader']['pid'] for n,r in registry.items() if r.get('leader') and unchanged(r['leader'])},indent=2))

def tailscale_config():
 if os.getenv("FURY_REMOTE_ACCESS")!="1":return {}
 try:
  r=subprocess.run(['tailscale','serve','status','--json'],capture_output=True,text=True,timeout=8)
  return json.loads(r.stdout) if r.returncode==0 else {}
 except (OSError,ValueError,subprocess.TimeoutExpired):return {}

def serve(action):
 config=tailscale_config();owned=[]
 for key,web in config.get('Web',{}).items():
  try:port=int(key.rsplit(':',1)[1])
  except ValueError:continue
  if port not in SERVE:continue
  expected={'Handlers':{'/':{'Proxy':f'http://127.0.0.1:{SERVE[port]}'}}}
  if web!=expected:continue
  owned.append(port)
 if action=='stop':
  # Never stop the daemon or remove another application's Serve configuration.
  if owned:(STATE/'serve-ports.json').write_text(json.dumps(owned))
  for port in owned:
   r=subprocess.run(['tailscale','serve','--https='+str(port),'off'],capture_output=True,text=True,timeout=15)
   if r.returncode:raise RuntimeError('Could not disable showcase Serve port '+str(port)+'. '+r.stderr.strip()+' Grant this user Tailscale operator access; SSH and the daemon are untouched.')
  remaining=tailscale_config()
  for port in owned:
   expected={'Handlers':{'/':{'Proxy':f'http://127.0.0.1:{SERVE[port]}'}}}
   if any(key.endswith(':'+str(port)) and web==expected for key,web in remaining.get('Web',{}).items()):
    raise RuntimeError('A showcase Serve proxy remained after shutdown; inspect tailscale serve status.')
 elif (STATE/'serve-ports.json').exists():
  for port in json.loads((STATE/'serve-ports.json').read_text()):
   if port not in SERVE:raise RuntimeError('Unexpected saved Serve port.')
   config=tailscale_config()
   if any(key.endswith(':'+str(port)) for key in config.get('Web',{})) or str(port) in config.get('TCP',{}):
    if port not in owned:raise RuntimeError('Serve port is now occupied by another route; refusing overwrite.')
    continue
   r=subprocess.run(['tailscale','serve','--bg','--https='+str(port),'--yes',f'http://127.0.0.1:{SERVE[port]}'],capture_output=True,text=True,timeout=20)
   if r.returncode:raise RuntimeError('Showcase apps started, but private Serve route could not be restored: '+r.stderr.strip())

def same_session(member,leader):
 return member.get('sid',member['pgid'])==leader.get('sid',leader['pgid'])

def session_member_verified(member,leader,members,name):
 if member['uid']!=os.getuid() or not same_session(member,leader):return False
 if member['cwd']==str(ROOT):return True
 if name not in ('text','lead'):return False
 # Compilers may make nested process groups, but must remain in the exact
 # engine session, allowed cache scope, executable set and live ancestry.
 work=Path(member['cwd']).resolve()
 cache=Path(os.getenv('VLLM_CACHE_ROOT',str(Path.home()/'.cache/vllm')))/'deep_gemm/tmp'
 match=re.fullmatch(r'(\d+)-[0-9a-f-]+',work.name)
 deep=work.parent==cache.resolve() and bool(match)
 flash=Path(os.getenv('FLASHINFER_WORKSPACE_BASE',str(Path.home())))/'.cache/flashinfer'
 try:relative=str(work.relative_to(flash.resolve()))
 except ValueError:relative=''
 flash=bool(re.fullmatch(r'[^/]+/[^/]+/cached_ops/[A-Za-z0-9_.-]+',relative))
 if not deep and not flash:return False
 env='.deepseek-venv' if name=='lead' else '.model-venv'
 tools=['/bin/sh','/usr/bin/gcc','/usr/bin/g++','/usr/bin/as','/usr/bin/ld','/usr/lib/gcc/aarch64-linux-gnu/13/collect2','/usr/libexec/gcc/aarch64-linux-gnu/13/cc1plus',str(ROOT/env/'bin/ninja')]
 tools += ['/usr/local/cuda/'+s for s in ('bin/nvcc','bin/ptxas','bin/nvlink','bin/fatbinary','nvvm/bin/cicc','bin/cudafe++')]
 if member['exe'] not in {str(Path(p).resolve()) for p in tools}:return False
 rows={r['pid']:r for r in members}
 engines=[r for r in members if r['cwd']==str(ROOT) and r['uid']==leader['uid'] and r['exe']==str((ROOT/env/'bin/python').resolve()) and r['args']==['VLLM::EngineCore'] and r.get('ppid')==leader['pid']]
 if len(engines)!=1:return False
 engine=engines[0]
 if deep and int(match[1])!=engine['pid']:return False
 current=member;seen=set()
 while current['pid']!=engine['pid']:
  if current['pid'] in seen:return False
  seen.add(current['pid']);parent=rows.get(current.get('ppid'))
  if not parent or parent['uid']!=leader['uid'] or not same_session(parent,leader) or int(parent['start'])>int(current['start']):return False
  current=parent
 return True

def stop_one(name,registry):
 row=discover(name);saved=registry.get(name,{})
 if row:
  members=[r for r in processes() if same_session(r,row)]
  if not all(session_member_verified(r,row,members,name) for r in members):raise RuntimeError('Unrecognised process in '+name+' session; refusing signals.')
  saved={'leader':fingerprint(row),'members':[fingerprint(r) for r in members]};registry[name]=saved;save(registry)
  # Recheck the exact leader and every member immediately before the group signal.
  if not identity(process(row['pid']),name) or not all(unchanged(m) for m in saved['members']):raise RuntimeError('Process identity changed before stop.')
  os.killpg(row['pgid'],signal.SIGTERM)
  deadline=time.monotonic()+45
  while any(unchanged(m) for m in saved['members']) and time.monotonic()<deadline:time.sleep(.15)
  remaining=[m for m in saved['members'] if unchanged(m)]
  # A hung verified descendant may outlive its leader; signal only the recorded PID identity.
  for m in remaining:
   if unchanged(m):os.kill(m['pid'],signal.SIGTERM)
  deadline=time.monotonic()+10
  while any(unchanged(m) for m in remaining) and time.monotonic()<deadline:time.sleep(.15)
  if any(unchanged(m) for m in remaining):raise RuntimeError(name+' did not stop gracefully; surviving verified PIDs: '+str([m['pid'] for m in remaining if unchanged(m)]))
 elif saved:
  remaining=[m for m in saved.get('members',[]) if unchanged(m)]
  if remaining:
   for m in remaining:
    if unchanged(m):os.kill(m['pid'],signal.SIGTERM)
   deadline=time.monotonic()+30
   while any(unchanged(m) for m in remaining) and time.monotonic()<deadline:time.sleep(.15)
   if any(unchanged(m) for m in remaining):raise RuntimeError('Recorded orphan remains for '+name)
 if port_open(COMPONENTS[name]['port']):raise RuntimeError(name+' port remains occupied; no unverified process was signalled.')
 registry.pop(name,None);save(registry);print(name+' stopped; port closed',flush=True)

def _start_one(name,registry):
 started=time.monotonic()
 row=discover(name)
 if not row:
  if port_open(COMPONENTS[name]['port']):raise RuntimeError(name+' port '+str(COMPONENTS[name]['port'])+' is occupied by an unverified process. Inspect ss -ltnp and /proc/PID/{cwd,cmdline}; use the configured active deployment controller. No process was adopted or signalled.')
  command=COMPONENTS[name]['command'];program=ROOT/command[0]
  if '/' in command[0] and not program.exists():raise RuntimeError('Run bash ops/bootstrap.sh first: missing '+command[0])
  # The consent policy expires visitor media on every actual service start.
  # Status/idempotent launches do not clear a live session or signal a process.
  sys.path.insert(0,str(ROOT))
  from showcase_app.visitor_store import clear_on_start
  clear_on_start()
  with (ROOT/'logs'/f'{name}.log').open('ab') as log:p=subprocess.Popen(command,cwd=ROOT,env=environment(),stdout=log,stderr=log,start_new_session=True)
  time.sleep(.15);row=process(p.pid)
  if not row or not identity(row,name):raise RuntimeError(name+' failed to start; inspect logs/'+name+'.log')
 registry[name]={'leader':fingerprint(row),'members':[]};save(registry)
 deadline=time.monotonic()+COMPONENTS[name].get('startup_timeout',600)
 while not ready(name):
  if STOP_REQUEST.exists():raise RuntimeError('Startup interrupted by an explicit stop request.')
  if not identity(process(row['pid']),name):raise RuntimeError(name+' exited during startup; inspect logs/'+name+'.log')
  if time.monotonic()>deadline:raise RuntimeError(name+' readiness timed out; inspect logs/'+name+'.log')
  print(name+' loading / waiting for readiness…',flush=True);time.sleep(5)
 row=discover(name)
 registry[name]['leader']=fingerprint(row)
 registry[name]['members']=[fingerprint(r) for r in processes() if r['pgid']==row['pgid']];save(registry)
 elapsed=round(time.monotonic()-started,3)
 timing_path=STATE/'startup-timings.json'
 timings=json.loads(timing_path.read_text()) if timing_path.exists() else {}
 timings[name]={'seconds':elapsed,'observed_at':time.time()}
 timing_path.write_text(json.dumps(timings,indent=2))
 print(name+' ready on '+str(COMPONENTS[name]['port'])+' after '+str(elapsed)+' s',flush=True)

def start_one(name,registry):
 existing=discover(name)
 try:return _start_one(name,registry)
 except BaseException:
  # Roll back only the component this invocation launched. Verified pre-existing
  # services are never stopped merely because a readiness probe failed.
  if existing is None:
   row=discover(name)
   saved=registry.get(name,{}).get('leader')
   if row and saved and fingerprint(row)==saved:
    try:stop_one(name,registry)
    except Exception as cleanup:print('Cleanup requires operator inspection: '+str(cleanup),file=sys.stderr)
  raise

def gpu_status():
 try:
  summary=subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
  apps=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
  if summary.returncode or apps.returncode:return {'verified':False,'summary':summary.stderr.strip(),'processes':[]}
  return {'verified':True,'summary':summary.stdout.strip(),'processes':apps.stdout.strip().splitlines() if apps.stdout.strip() else []}
 except (OSError,subprocess.TimeoutExpired):return {'verified':False,'summary':'nvidia-smi unavailable','processes':[]}

def status():
 try:
  customer=json.loads((STATE/'skin/active.json').read_text())
  idle=json.loads((ROOT/'config/skin.json').read_text())['idle_hours']*3600
  skin_name=customer['name'] if time.time()-customer.get('touched',0)<idle else 'default · HP ZGX Fury'
 except (OSError,ValueError,KeyError):skin_name='default · HP ZGX Fury'
 print('Customer skin:',skin_name)
 try:print('Presenter PIN:',(STATE/'skin-presenter.pin').read_text().strip())
 except OSError:print('Presenter PIN: generated on first operator launch')
 print(f'{"COMPONENT":12} {"PORT":6} {"PID":8} {"PROCESS / READINESS":24} MODEL')
 for name,spec in COMPONENTS.items():
  row=discover(name);healthy=ready(name) if row else False
  state=('running / ready' if healthy else 'running / loading') if row else 'UNVERIFIED PORT OWNER' if port_open(spec['port']) else 'stopped'
  model=(('loaded' if healthy else 'loading / not ready' if row else 'unloaded')+' · '+spec['model']) if spec.get('model') else 'DeepSeek + Qwen via gateway' if name in ('agent','gateway') else 'shared Qwen via gateway' if name in ('atlas','slides') else 'no resident model (dashboard)'
  print(f'{name:12} {spec["port"]:<6} {str(row["pid"]) if row else "—":8} {state:24} {model}')
 gpu=gpu_status();print('GPU:',gpu['summary']);print('GPU compute processes:',*gpu['processes'],sep='\n  ')
 print('GPU FREE (no compute process)' if gpu['verified'] and not gpu['processes'] else 'GPU IN USE' if gpu['verified'] else 'GPU STATE UNKNOWN')
 config=tailscale_config();print('Private Serve listeners:',', '.join(config.get('TCP',{})) or 'none (daemon and SSH remain available)')
 if discover('operator') and ready('operator'):
  print('Browser: http://127.0.0.1:8080/')
  for host,web in config.get('Web',{}).items():
   if web=={'Handlers':{'/':{'Proxy':'http://127.0.0.1:8080'}}}:
    print('Private browser: https://'+host+'/')
 return gpu

def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['status','start','stop','restart']);parser.add_argument('components',nargs='*');args=parser.parse_args()
 if any(name not in COMPONENTS for name in args.components):parser.error('Unknown component; choose '+', '.join(COMPONENTS))
 STATE.mkdir(exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
 requested=time.time()
 if args.action=='status':status();return
 if args.action=='stop' and not args.components:STOP_REQUEST.write_text(str(requested))
 with (STATE/'control.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  registry=json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
  names=args.components or list(COMPONENTS)
  if args.action in ('stop','restart'):
   errors=[]
   for name in reversed(list(COMPONENTS)):
    if name in names:
     try:stop_one(name,registry)
     except RuntimeError as exc:errors.append(str(exc))
   if not args.components:
    gpu=status()
    if not gpu['verified']:errors.append('GPU release could not be verified.')
    elif gpu['processes']:errors.append('GPU compute processes remain; inspect identities above. Unrelated processes are never stopped.')
   if errors:raise RuntimeError('\n'.join(errors))
  if args.action in ('start','restart'):
   if STOP_REQUEST.exists():
    if float(STOP_REQUEST.read_text())>requested:raise RuntimeError('A newer stop request superseded startup.')
    STOP_REQUEST.unlink()
   for name in COMPONENTS:
    if name in names and COMPONENTS[name].get('enabled',True):start_one(name,registry)
   # Local launch does not alter remote access.
   status()
if __name__=='__main__':
 try:main()
 except (RuntimeError,OSError,ValueError) as exc:print('ERROR:',exc,file=sys.stderr);sys.exit(1)
