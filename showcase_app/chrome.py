"""Read-only shell telemetry proxy; original application/frame policies stay intact."""
import anyio
import httpx
from starlette.responses import StreamingResponse


class TelemetryProxy:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
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
