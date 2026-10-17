"""Origin-based CSRF protection, bounded requests, and per-IP auth throttling."""
import json
import time
from collections import deque

class SecurityMiddleware:
    def __init__(self, app, origin: str):
        self.app = app
        self.origin = origin
        self.buckets = {}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        api = scope['path'].startswith('/api/')
        headers = {key.lower(): value for key, value in scope.get('headers', [])}

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'),
                    (b'referrer-policy', b'no-referrer'),
                ]
                if api:
                    message['headers'].append((b'cache-control', b'no-store'))
            await send(message)

        async def reject(status, error, retry=None):
            response_headers = [(b'content-type', b'application/json')]
            if retry is not None:
                response_headers.append((b'retry-after', str(retry).encode()))
            await secured_send({'type': 'http.response.start', 'status': status, 'headers': response_headers})
            await secured_send({'type': 'http.response.body', 'body': json.dumps({'error': error}).encode()})

        if api and scope['method'] not in ('GET', 'HEAD', 'OPTIONS'):
            if headers.get(b'origin', b'').decode() != self.origin:
                return await reject(403, 'Request origin is not allowed.')

        limits = {'/api/auth/request-otp': 15, '/api/auth/verify-otp': 40}
        if scope['path'] in limits:
            now = time.monotonic()
            for key in list(self.buckets):
                bucket = self.buckets[key]
                while bucket and bucket[0] <= now - 900:
                    bucket.popleft()
                if not bucket:
                    del self.buckets[key]
            client = scope.get('client') or ('unknown', 0)
            key = (client[0], scope['path'])
            if key not in self.buckets and len(self.buckets) >= 4096:
                return await reject(429, 'Too many authentication requests. Try again later.', 900)
            bucket = self.buckets.setdefault(key, deque())
            if len(bucket) >= limits[scope['path']]:
                return await reject(429, 'Too many attempts. Try again in 15 minutes.', 900)
            bucket.append(now)

        if api and scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE'):
            multipart = headers.get(b'content-type', b'').startswith(b'multipart/form-data')
            limit = 6 * 1024 * 1024 if multipart else 32 * 1024
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > limit:
                    return await reject(413, 'Upload is too large. Choose an image up to 5 MB.' if multipart else 'Request is too large.')
                if not message.get('more_body', False):
                    break
            sent = False

            async def buffered_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            return await self.app(scope, buffered_receive, secured_send)
        await self.app(scope, receive, secured_send)
