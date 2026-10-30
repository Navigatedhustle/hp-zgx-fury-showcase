"""Fail-closed Linux namespace runner for model-generated code. No host execution fallback."""
import json,os,shutil,subprocess,sys,tempfile,math
from pathlib import Path
RUNNER=Path(__file__).with_name('devteam_worker.py')
def available():
 if sys.platform!='linux' or not shutil.which('bwrap'):return False
 try:
  cmd=['bwrap','--unshare-all','--ro-bind','/usr','/usr']
  for folder in ('/lib','/lib64'):
   if Path(folder).exists():cmd+=['--ro-bind',folder,folder]
  cmd+=['--symlink','usr/bin','/bin','--proc','/proc','--dev','/dev','/bin/true']
  r=subprocess.run(cmd,capture_output=True,timeout=4)
  return r.returncode==0
 except (OSError,subprocess.TimeoutExpired):return False
def execute(code:Path,data:Path,mode:str,payload=None):
 if sys.platform!='linux' or not shutil.which('bwrap'):raise RuntimeError('Generated code requires Linux bubblewrap; no unsandboxed fallback is allowed.')
 if mode not in ('test','traveltest','travellist','api','resources','travelroutes'):raise ValueError('Unsupported sandbox operation')
 data.mkdir(parents=True,exist_ok=True)
 cmd=['bwrap','--unshare-all','--die-with-parent','--new-session','--clearenv','--setenv','PATH','/usr/bin','--setenv','LANG','C.UTF-8','--ro-bind','/usr','/usr']
 for folder in ('/lib','/lib64'):
  if Path(folder).exists():cmd+=['--ro-bind',folder,folder]
 cmd+=['--symlink','usr/bin','/bin','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(code.resolve()),'/workspace','--bind',str(data.resolve()),'/data','--ro-bind',str(RUNNER.resolve()),'/runner.py','--chdir','/workspace','/usr/bin/python3','-I','-S','/runner.py',mode]
 try:
  r=subprocess.run(cmd,input=json.dumps(payload or {}),text=True,capture_output=True,timeout=12,start_new_session=True)
 except subprocess.TimeoutExpired:raise RuntimeError('Sandbox exceeded wall time limit')
 if len(r.stdout)>200000 or len(r.stderr)>200000:raise RuntimeError('Sandbox output exceeded limit')
 if r.returncode:raise RuntimeError('Sandbox failed (exit '+str(r.returncode)+'): '+r.stderr[-3000:])
 return json.loads(r.stdout)

def check_javascript(code:Path):
 """Parse generated JS without executing it, inside the same networkless namespace."""
 script=code/'app.js'
 if not script.exists():return
 node=Path(__file__).resolve().parents[3]/'.venv/lib/python3.12/site-packages/playwright/driver/node'
 if not node.is_file():raise RuntimeError('Local JavaScript parser is unavailable')
 cmd=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr']
 for folder in ('/lib','/lib64'):
  if Path(folder).exists():cmd+=['--ro-bind',folder,folder]
 cmd+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',str(code.resolve()),'/workspace','--ro-bind',str(node),'/node','/usr/bin/prlimit','--cpu=3','--fsize=1048576','--nofile=64','/node','--max-old-space-size=64','--check','/workspace/app.js']
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=8,start_new_session=True)
 except subprocess.TimeoutExpired:raise ValueError('Generated JavaScript syntax validation timed out')
 if r.returncode:raise ValueError('Generated app.js has invalid JavaScript syntax: '+r.stderr[-1800:])

def check_backend_contract(code:Path,data:Path):
 """Exercise exact public statuses on the real generated backend before merge."""
 resources=execute(code,data/'resource-probe','resources')
 if not resources.get('passed'):raise ValueError('Generated backend leaks database connections: '+str(resources.get('opened_fds'))+' descriptors after16 calls. SQLite connection context managers commit but DO NOT CLOSE. Use contextlib.closing(sqlite3.connect(...)) plus transaction management, or finally:connection.close(). Preserve all API behavior.')
 cold=execute(code,data/'cold-start','api',{'method':'POST','path':'/bookings','body':{'hotel_id':1,'guest':'Fictional Cold Start','date':'2028-11-18'}})
 if cold.get('status')!=201:raise ValueError('A newly created booking on a fresh database must return201, not '+str(cold.get('status'))+'. Seed the five fictional hotels during database initialization for EVERY route; POST must not require a previous GET /hotels. Preserve existing reservations.')
 persisted=execute(code,data/'cold-start','api',{'method':'GET','path':'/bookings','body':{}})
 if not any(b.get('guest')=='Fictional Cold Start' and b.get('date')=='2028-11-18' and b.get('hotel_id')==1 for b in persisted.get('body',{}).get('bookings',[])):raise ValueError('POST returned201 but a fresh GET /bookings cannot see the reservation. Every handle call runs in a NEW process; Python globals do not persist. COMMIT SQLite writes before closing. contextlib.closing only closes and never commits; use with closing(connection) as conn, conn: or conn.commit(). Preserve the real reservation and duplicate protection.')
 inventory=execute(code,data,'api',{'method':'GET','path':'/hotels','body':{}})
 if inventory.get('status')!=200 or len(inventory.get('body',{}).get('hotels',[]))!=5:raise ValueError('GET /hotels must return200 and exactly five hotels')
 ids=[h.get('id') for h in inventory['body']['hotels']]
 if any(type(i) is not int for i in ids) or set(ids)!=set(range(1,6)):raise ValueError('Hotel inventory IDs must be the five unique integers1 through5')
 for hotel in inventory['body']['hotels']:
  if not all(isinstance(hotel.get(key),str) and hotel[key].strip() for key in ('name','city')) or type(hotel.get('price')) not in (int,float) or not math.isfinite(hotel['price']) or hotel['price']<0:raise ValueError('Each hotel needs nonempty name/city strings and a finite nonnegative numeric price; do not change prices to strings to work around frontend escaping.')
 hid=inventory['body']['hotels'][0]['id']
 for unknown in (99,999):
  reply=execute(code,data,'api',{'method':'POST','path':'/bookings','body':{'hotel_id':unknown,'guest':'Fictional Contract Guest','date':'2028-11-17'}})
  if reply.get('status')!=404:raise ValueError('Unknown numeric hotel ID '+str(unknown)+' must return404 consistently, not '+str(reply.get('status')))
 for body in ({'hotel_id':hid,'date':'2028-11-17'},{'hotel_id':hid,'guest':'Fictional Contract Guest','date':'2027-02-30'}):
  reply=execute(code,data,'api',{'method':'POST','path':'/bookings','body':body})
  if reply.get('status')!=400:raise ValueError('Missing guest or invalid calendar date must return400, not '+str(reply.get('status')))
 request={'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional Contract Guest','date':'2028-11-17'}}
 reply=execute(code,data,'api',request)
 if reply.get('status')!=201:raise ValueError('A newly created booking must return201, not '+str(reply.get('status')))
 duplicate=execute(code,data,'api',request)
 if duplicate.get('status')!=409:raise ValueError('Duplicate booking must return409, not '+str(duplicate.get('status'))+'. Verify the previous INSERT was committed and visible to a new SQLite connection before close.')


def check_generated_qa(code:Path,data:Path):
 """Reject generated-test contract contradictions with a trusted fixture.

 This temporary oracle is never merged or published. The generated backend
 remains independently checked and must subsequently pass every generated test.
 """
 # Actual generated tests plus immutable trusted acceptance are authoritative
 # when they agree. Unspecified behavior (extra keys/metadata/unknown routes)
 # must not be rejected merely because the diagnostic oracle chooses differently.
 real=execute(code,data/'actual-tests','test')
 if real.get('passed'):return
 inventory=execute(code,data/'inventory','api',{'method':'GET','path':'/hotels','body':{}})
 if inventory.get('status')!=200:raise ValueError('Cannot verify QA without actual hotel inventory')
 # Preserve the actual generated error envelope rather than giving QA extra
 # fields the application does not have. Only status semantics use the oracle.
 hid=inventory['body']['hotels'][0]['id'];error_fields={}
 valid={'method':'POST','path':'/bookings','body':{'hotel_id':hid,'guest':'Fictional QA Shape','date':'2028-10-19'}}
 execute(code,data/'shapes','api',{'method':'GET','path':'/hotels','body':{}})
 execute(code,data/'shapes','api',valid)
 probes=[(400,{'method':'POST','path':'/bookings','body':{'hotel_id':hid,'date':'2028-10-20'}}),(404,{'method':'POST','path':'/bookings','body':{'hotel_id':999,'guest':'Fictional QA Shape','date':'2028-10-20'}}),(409,valid)]
 for status,request in probes:
  reply=execute(code,data/'shapes','api',request)
  fields=[key for key in ('error','message') if isinstance(reply.get('body',{}).get(key),str) and reply['body'][key]]
  if fields:error_fields[str(status)]=fields
 fallback=next(iter(error_fields.values()),['error'])
 for status in (400,404,409):error_fields.setdefault(str(status),fallback)
 with tempfile.TemporaryDirectory(prefix='fury-qa-oracle-') as temporary:
  fixture=Path(temporary)
  shutil.copy2(code/'test_backend.py',fixture/'test_backend.py')
  shutil.copy2(Path(__file__).with_name('devteam_reference.py'),fixture/'backend.py')
  (fixture/'qa-reference.json').write_text(json.dumps({'hotels':inventory['body']['hotels'],'error_fields':error_fields}))
  result=execute(fixture,data/'oracle','test')
 if not result.get('passed'):
  log=result.get('log','')
  raise ValueError('Generated QA contradicts the trusted public-contract reference. Correct only contradictory test expectations; preserve all legitimate cases and assertions. Calendar dates follow Python datetime:2028-02-29 and2024-02-29 are VALID;2027-02-29 is INVALID. The reference is only a QA fixture and is never the generated application. Actual reference failure:\n'+log[-1500:])
