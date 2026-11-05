"""The development team is the only active Agent Factory application.

Historical supplier/prospecting source and audits remain on disk for rollback;
none of their workflows, inbox collectors or browser assets are mounted here.
"""
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio,logging,uuid
import httpx
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse,JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
import devteam_routes
from showcase_app.frame_policy import station_ancestors
ROOT=Path(__file__).resolve().parent
SHOWCASE=ROOT.parents[2]/'showcase_app/assets'
ACTIVE_STATIC={'devteam.css','devteam.js','devteam-stack.css','devteam-stack.js'}
LEGACY_PAGES={'/','/prospecting','/supplier','/sales','/research','/factory','/static/index.html','/static/prospecting.html'}
@asynccontextmanager
async def lifespan(app):
    devteam_routes.recover_sessions()
    yield
    for run in devteam_routes.active_runs():
        if getattr(run,'travel',False) and not run.stop_event.is_set():run.interrupt()
        else:run.stop()
    for run in devteam_routes.active_runs():await asyncio.to_thread(run.thread.join,15)
app=FastAPI(title='Fury Agent Factory — Development Team',docs_url=None,redoc_url=None,lifespan=lifespan)
app.mount('/showcase-assets',StaticFiles(directory=SHOWCASE),name='showcase-assets')
@app.middleware('http')
async def security_headers(request,call_next):
    key=request.cookies.get('fury_factory_session')
    fresh=not (key and __import__('re').fullmatch('[0-9a-f]{32}',key))
    if fresh:key=uuid.uuid4().hex
    token=devteam_routes.session.set(key)
    if request.url.path in LEGACY_PAGES:

        response=RedirectResponse('/devteam',status_code=307)
    else:response=await call_next(request)
    devteam_routes.session.reset(token)
    if fresh:response.set_cookie('fury_factory_session',key,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=86400)
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/') else 'no-cache'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    if request.url.path=='/api/devteam/preview-frame':
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'"
    if request.url.path.startswith('/travel/'):
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
    if request.url.path.startswith('/api/travel/') and request.url.path.endswith('/frame'):
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'"
    if request.url.path in ('/devteam','/devteam/build','/api/devteam/preview-frame') or request.url.path.startswith('/travel/') or (request.url.path.startswith('/api/travel/') and request.url.path.endswith('/frame')):
        policy=response.headers['Content-Security-Policy']
        response.headers['Content-Security-Policy']=__import__('re').sub(r"frame-ancestors [^;]+",'frame-ancestors '+station_ancestors(request.url.hostname),policy)
    return response
@app.get('/static/{filename}')
async def static_file(filename:str):
    if filename not in ACTIVE_STATIC:raise HTTPException(410,'This legacy Agent Factory asset is retired. Open /devteam.')
    return FileResponse(ROOT/'static'/filename)
@app.get('/_stcore/health')
@app.get('/health')
async def health():
    try:
        async with httpx.AsyncClient(timeout=2,trust_env=False) as client:
            response=await client.get('http://127.0.0.1:8001/health');response.raise_for_status();backends=response.json().get('backends',{})
        return {'ready':all(backends.get(m) for m in devteam_routes.MODEL_DETAILS),'mode':'development-team','backends':backends,'active':bool(devteam_routes.active_runs())}
    except (httpx.HTTPError,ValueError):return {'ready':False,'mode':'development-team'}
@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    reference=uuid.uuid4().hex[:12]
    logging.getLogger('uvicorn.error').error('Agent Factory request failed reference=%s',reference,exc_info=exc)
    return JSONResponse({'detail':'Coordinator failed. Check service logs with reference '+reference,'reference':reference},status_code=500)
app.include_router(devteam_routes.router)
@app.api_route('/api/{retired:path}',methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'])
async def retired_api(retired:str):
    if retired=='devteam' or retired.startswith('devteam/'):raise HTTPException(404,'Unknown development API route')
    return JSONResponse({'detail':'The supplier and research/sales Agent Factory versions are retired. Use the development team.','entry':'/devteam'},status_code=410)
