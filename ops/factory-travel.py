#!/usr/bin/env python3
"""Operate one session-owned sustained Factory project. Stdlib only."""
import argparse,http.cookiejar,json,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('action',choices=['start','status','stop','resume']);p.add_argument('--origin',default='http://127.0.0.1:8501');p.add_argument('--session',type=Path,default=Path(__file__).resolve().parents[1]/'state/factory-travel-session.cookies');p.add_argument('--full',action='store_true');a=p.parse_args()
jar=http.cookiejar.MozillaCookieJar(str(a.session))
try:jar.load(ignore_discard=True,ignore_expires=True)
except FileNotFoundError:pass
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
route={'start':'runs','status':'run','stop':'stop','resume':'resume'}[a.action]
body=None if a.action=='status' else json.dumps({'product':'travel','automatic':True} if a.action=='start' else {}).encode()
request=urllib.request.Request(a.origin+'/api/devteam/'+route,data=body,headers={'Content-Type':'application/json'})
try:
 with opener.open(request,timeout=20) as response:d=json.load(response)
except urllib.error.HTTPError as e:raise SystemExit(e.read().decode())
a.session.parent.mkdir(parents=True,exist_ok=True);jar.save(ignore_discard=True,ignore_expires=True);a.session.chmod(0o600)
if a.full:print(json.dumps(d,indent=2))
else:print(json.dumps({k:d.get(k) for k in ('id','state','error','elapsed_s','cumulative_tokens','application_url')}|{'next_action':d.get('product',{}).get('next_action'),'criteria':d.get('product',{}).get('criteria')},indent=2))
