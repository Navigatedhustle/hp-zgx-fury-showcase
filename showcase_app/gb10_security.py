"""Small-body and origin guard for the loopback stage control APIs."""
from starlette.responses import JSONResponse


class StageRequestGuard:
    def __init__(self, app, limit=65536):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        method = scope['method']
        if method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = headers.get(b'origin')
            if origin not in (None, b'http://127.0.0.1:18808', b'http://localhost:18808'):
                return await JSONResponse({'error': 'Only local stage origins are accepted'}, 403)(scope, receive, send)
            chunks = []
            length = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                length += len(chunk)
                if length > self.limit:
                    return await JSONResponse({'error': 'Stage control payload is too large'}, 413)(scope, receive, send)
                chunks.append(chunk)
                if not message.get('more_body', False):
                    break
            body = b''.join(chunks)
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)
