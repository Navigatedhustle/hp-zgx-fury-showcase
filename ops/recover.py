#!/usr/bin/env python3
"""Guarded recovery through the existing identity-checked controller."""
import argparse,json,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def get(port,path):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}{path}',timeout=5) as r:return json.load(r)
p=argparse.ArgumentParser();p.add_argument('component',choices=['text','lead','gateway','asr','tts','atlas','slides','agent','image','operator']);a=p.parse_args()
checks=[]
for port,path,keys in [(8001,'/health',['active','queued']),(8501,'/api/devteam/status',['active']),(8800,'/health',['active','queued']),(8765,'/api/booth/status',['pending'])]:
 try:status=get(port,path);checks.append(not any(status.get(k) for k in keys))
 except Exception:
  from control import COMPONENTS,discover,port_open
  own_port=COMPONENTS[a.component]['port']
  checks.append(port==own_port and not port_open(port) and discover(a.component) is None)
if not all(checks):raise SystemExit('Cannot prove all workflows are idle. Wait for jobs or inspect ./launch.sh diagnostics before an explicit component restart.')
raise SystemExit(subprocess.call(['./showcase','restart',a.component],cwd=ROOT))
