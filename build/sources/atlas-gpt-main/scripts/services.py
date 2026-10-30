"""Own, warm and track lane-local services. Runtime never downloads assets."""
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from atlas.telemetry import Telemetry

def identity(pid):
    return Path(f'/proc/{pid}/stat').read_text().split()[21]

def path(role):
    d=json.loads((ROOT/'models'/f'{role}.json').read_text())
    return str(next(Path(d['path']).glob('*.gguf')))
def alive(service):
    try:
        pid=int((ROOT/'runtime'/f'{service}.server.pid').read_text())
        record=ROOT/'runtime'/f'{service}.server.json'
        owned=not record.exists() or json.loads(record.read_text())['start_ticks']==identity(pid)
        return owned and Path(f'/proc/{pid}/cwd').resolve()==ROOT and Path(f'/proc/{pid}/stat').read_text().split()[2]!='Z'
    except (OSError,ValueError,KeyError):return False
def spawn(service,command,extra_env=None):
    if alive(service):return
    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1','OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4',**(extra_env or {})}
    p=subprocess.Popen(['nohup','timeout','24h',*command],cwd=ROOT,env=env,stdout=(ROOT/'logs'/f'{service}.log').open('w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
    (ROOT/'runtime'/f'{service}.server.pid').write_text(str(p.pid))
    (ROOT/'runtime'/f'{service}.server.json').write_text(json.dumps({'pid':p.pid,'start_ticks':identity(p.pid),'command':command}))
    print(f'Started {service}: {p.pid}',flush=True)
def wait(port,endpoint='/health',seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            if urllib.request.urlopen(f'http://127.0.0.1:{port}{endpoint}',timeout=.5).status==200:return True
        except Exception:pass
        time.sleep(.25)
    return False
def start_ui():spawn('ui',[str(ROOT/'.venv/bin/python'),'-m','uvicorn','atlas.server:app','--host','0.0.0.0' if os.environ.get('ATLAS_HOST')=='0.0.0.0' else '127.0.0.1','--port','8200'])

def can_load(service,increment_gib):
    if alive(service):return False
    subprocess.run(['free','-g'],check=True)
    snapshot=Telemetry().read()
    available=snapshot['memory']['available_gb'];owned=snapshot['app_memory_gb']
    # Keep an additional 4 GiB margin above the shared-host 16 GiB floor.
    permitted=available-increment_gib>=20 and (owned+increment_gib)*2**30<=48*10**9
    print(f'{service}: available={available:.1f} GiB, lane estimate={owned:.1f} GiB, reserved increment={increment_gib} GiB; '+('load permitted' if permitted else 'skipped for memory safety'),flush=True)
    return permitted

def start_models():
    if (ROOT/'models/brain.json').exists() and not alive('brain'):
        with open('/tmp/atlas-heavy.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if can_load('brain',23):
                spawn('brain',[str(ROOT/'vendor/llama/llama-b11490/llama-server'),'-m',path('brain'),'--host','127.0.0.1','--port','8201','--ctx-size','2048','--parallel','1','--alias','atlas-local','--n-gpu-layers','999','--flash-attn','on','--threads','8','--jinja','--reasoning','off','--no-reasoning-preserve'])
            if alive('brain') and wait(8201):
                body=json.dumps({'messages':[{'role':'user','content':'Output {"tool":"forecast_quarter"} only.'}],'temperature':0,'max_tokens':20,'chat_template_kwargs':{'enable_thinking':False}}).encode()
                try:urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8201/v1/chat/completions',data=body,headers={'Content-Type':'application/json'}),timeout=10).read()
                except Exception as e:print('Brain warmup:',type(e).__name__,flush=True)
    if (ROOT/'models/asr.json').exists() and can_load('speech',3):
        spawn('speech',[str(ROOT/'vendor/speech/nemo-speech-nightly-linux-aarch64-cuda13/bin/nemo-speech'),'serve','--config',str(ROOT/'runtime/speech.yaml')])
        wait(8202,'/v1/models')
def start_tts():
    if (ROOT/'models/kokoro.json').exists() and can_load('tts',3):
        spawn('tts',[str(ROOT/'.venv/bin/python'),'-m','uvicorn','atlas.tts_server:app','--host','127.0.0.1','--port','8204'])
        wait(8204)

def start_embed():
    if os.environ.get('ATLAS_DOCUMENTS','1')!='0' and (ROOT/'models/embed.json').exists() and can_load('embed',4):
        spawn('embed',[str(ROOT/'.venv/bin/python'),'-m','uvicorn','atlas.embed_server:app','--host','127.0.0.1','--port','8206'],{'HF_MODULES_CACHE':str(ROOT/'models/embed-modules')})
        if wait(8206) and not (ROOT/'data/knowledge/index.json').exists():
            try:urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8200/api/knowledge/initialize',data=b'{}',headers={'Content-Type':'application/json'}),timeout=90).read()
            except Exception as e:print('Index startup:',type(e).__name__,flush=True)

def start_vision():
    if (ROOT/'models/rf-detr-nano.pth').exists() and can_load('vision',3):
        spawn('vision',[str(ROOT/'.venv/bin/python'),'-m','uvicorn','atlas.vision_server:app','--host','127.0.0.1','--port','8205'])
        wait(8205)

def start_decisions():
    if (ROOT/'models/decisions.json').exists() and can_load('decisions',17):
        spawn('decisions',[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/start_decisions.py')])
        wait(8203,'/v1/models')

if __name__=='__main__':
    os.chdir(ROOT)
    if sys.argv[1]=='ui':start_ui()
    elif sys.argv[1]=='launch':
        with open(ROOT/'runtime/start.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            start_ui()
            spawn('startup',['timeout','180',str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/services.py'),'models'])
    elif sys.argv[1]=='models':
        start_models();start_decisions();start_tts();start_vision();start_embed()
        if wait(8200,'/api/health',5) and wait(8204,seconds=1):
            subprocess.run([str(ROOT/'.venv/bin/python'),'-m','scripts.warm_voice'],timeout=100,check=False)
    elif sys.argv[1]=='decisions':start_decisions()
    elif sys.argv[1]=='vision':start_vision()
    elif sys.argv[1]=='tts':start_tts()
    elif sys.argv[1]=='embed':start_embed()
