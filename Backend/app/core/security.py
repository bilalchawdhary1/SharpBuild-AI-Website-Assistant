"""Security middleware (pure ASGI, standard library only, safe for streaming responses).

 - Rejects oversized request bodies with 413 before they are parsed. Pydantic caps every field,
   but without this a huge JSON body would still be read into memory first. Checks both the
   Content-Length header and the bytes actually received (chunked uploads have no header).
 - Adds defensive headers to every response, and `Cache-Control: no-store` on routes that
   handle personal data (/lead, /internal), unless the route already set its own.
"""
import json

SENSITIVE_PREFIXES = ("/lead", "/internal")
BODY_METHODS = {"POST", "PUT", "PATCH"}
BASE_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
)


class _TooLarge(Exception):
    pass


class SecurityMiddleware:
    def __init__(self, app, max_body_bytes: int = 32_768):
        self.app, self.max_body_bytes = app, max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        sensitive = scope.get("path", "").startswith(SENSITIVE_PREFIXES)
        started = False

        async def send_with_headers(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [h for h in BASE_HEADERS if h[0] not in present]
                if sensitive and b"cache-control" not in present:
                    extra.append((b"cache-control", b"no-store"))
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        async def too_large():
            body = json.dumps({"detail": "Request too large"}).encode()
            await send_with_headers({"type": "http.response.start", "status": 413, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send_with_headers({"type": "http.response.body", "body": body})

        if scope["method"] in BODY_METHODS:
            declared = dict(scope.get("headers", [])).get(b"content-length", b"")
            if declared.isdigit() and int(declared) > self.max_body_bytes:
                return await too_large()

        received = 0

        async def counting_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _TooLarge
            return message

        try:
            await self.app(scope, counting_receive, send_with_headers)
        except _TooLarge:
            if not started:
                await too_large()
