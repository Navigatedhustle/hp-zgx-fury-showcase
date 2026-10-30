"""Read-only Tailscale onboarding metadata; no enrollment keys or identity listing."""
import asyncio,json,os

SERVICES=[('Showcase','443',8080,'/'),('Atlas','8200',8200,'/'),('Presentation Creator','8765',8765,'/booth'),('Agent Factory','8501',8501,'/'),('Image Studio','8800',8800,'/')]
async def command(*args):
    process=await asyncio.create_subprocess_exec('tailscale',*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        out,err=await asyncio.wait_for(process.communicate(),4)
    except asyncio.TimeoutError:
        process.kill();await process.communicate();raise RuntimeError('Tailscale status timed out')
    if process.returncode:raise RuntimeError('Tailscale status is unavailable')
    return json.loads(out)

async def device_status():
    if os.getenv("FURY_REMOTE_ACCESS")!="1":return {"connected":False,"ready":False,"links":[],"error":"Optional remote access is disabled; see docs/REMOTE-ACCESS.md"}
    try:
        status,serve=await asyncio.gather(command('status','--json'),command('serve','status','--json'))
        host=status.get('Self',{}).get('DNSName','').rstrip('.')
        if not host.endswith('.ts.net'):raise RuntimeError('No private Tailscale DNS name available')
        links=[]
        for name,port,target,path in SERVICES:
            url='https://'+host+(':'+port if port!='443' else '')
            configured=serve.get('Web',{}).get(host+':'+port,{}).get('Handlers',{}).get('/',{}).get('Proxy')==f'http://127.0.0.1:{target}'
            public=bool(serve.get('AllowFunnel',{}).get(host+':'+port))
            links.append({'name':name,'url':url+path,'ready':configured and not public,'public':public})
        return {'connected':status.get('BackendState')=='Running','host':host,'links':links,'ready':all(l['ready'] for l in links),'home':'https://'+host,'connect_url':'https://'+host+'/connect'}
    except (OSError,ValueError,RuntimeError) as e:
        return {'connected':False,'ready':False,'links':[],'error':str(e)}
