#!/usr/bin/env python3
"""Local reference server. Generated Python executes only inside bubblewrap."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CODE=Path(__file__).resolve().parent/'app'
sys.path.insert(0,str(ROOT/'build/sources/fury_agent_factory'))
from devteam_sandbox import execute
from fastapi import FastAPI,Request
from fastapi.responses import HTMLResponse,FileResponse,JSONResponse
import uvicorn
app=FastAPI()
@app.get('/')
def index():
 html=(CODE/'index.html').read_text();bridge='''<div style="position:fixed;bottom:0;background:#101820;color:white;z-index:99999;padding:10px">PREBUILT REFERENCE — no live generation</div><script>let token=sessionStorage.getItem('reference-token')||'';window.furyApi=async(method,path,body={})=>{const r=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,path,body,headers:token?{authorization:'Bearer '+token}:{}})});if(!r.ok)throw Error('Transport '+r.status);const d=await r.json();if(d.body?.token){token=d.body.token;sessionStorage.setItem('reference-token',token)}if(path==='/logout'){token='';sessionStorage.removeItem('reference-token')}return d};</script>'''
 banner,script=bridge.split('<script>',1)
 return HTMLResponse(html.replace('</head>','<script>'+script+'</head>').replace('</body>',banner+'</body>'))
@app.get('/{asset}')
def asset(asset:str):
 if asset not in ('app.js','styles.css'):return JSONResponse({'error':'Not found'},status_code=404)
 return FileResponse(CODE/asset)
@app.post('/api')
async def api(request:Request):
 import asyncio
 payload=await request.json()
 return await asyncio.to_thread(execute,CODE,ROOT/'state/reference-travel','api',payload)

# Apply after route/application middleware registration so Host validation is outermost.
from showcase_app.security import HostGuard
app.add_middleware(HostGuard)

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8510)
