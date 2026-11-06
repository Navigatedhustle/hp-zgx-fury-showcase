"""Read-only shell telemetry proxy; original application/frame policies stay intact."""
import anyio
import httpx
from starlette.responses import StreamingResponse,Response


class TelemetryProxy:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and scope['path'].startswith('/skin/') and scope['method'] in ('GET','POST'):
            from starlette.requests import Request
            request=Request(scope,receive)
            raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>2*1024*1024:return await Response('Maximum upload is two megabytes',413)(scope,receive,send)
            headers={k:v for k,v in request.headers.items() if k in ('content-type','cookie','origin','x-skin-name')}
            headers['host']=request.headers.get('host','localhost')
            async with httpx.AsyncClient(trust_env=False,timeout=12) as client:
                try:
                    result=await client.request(scope['method'],'http://127.0.0.1:8080'+scope['path'],headers=headers,content=bytes(raw))
                    response=Response(result.content,result.status_code,headers={k:v for k,v in result.headers.items() if k in ('content-type','cache-control','set-cookie','content-security-policy','x-content-type-options')})
                except httpx.HTTPError:response=Response('Operator unavailable',503)
            return await response(scope,receive,send)
        if scope['type']!='http' or scope['path']!='/showcase-telemetry' or scope['method']!='GET':
            return await self.app(scope,receive,send)
        async def stream():
            client=httpx.AsyncClient(trust_env=False,timeout=httpx.Timeout(None,connect=3))
            response=None
            try:
                response=await client.send(client.build_request('GET','http://127.0.0.1:8080/api/telemetry/stream'),stream=True)
                response.raise_for_status()
                async for chunk in response.aiter_bytes():yield chunk
            except httpx.HTTPError:
                yield b'event: unavailable\ndata: {}\n\n'
            finally:
                with anyio.CancelScope(shield=True):
                    if response:await response.aclose()
                    await client.aclose()
        return await StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})(scope,receive,send)
