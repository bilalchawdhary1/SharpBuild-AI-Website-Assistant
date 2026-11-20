"""SecurityMiddleware (core/security.py): body limit and headers. Pure ASGI, no web framework needed."""
import asyncio
import json
import unittest

from app.core.security import SecurityMiddleware


def run(app, method="POST", path="/chat", headers=(), chunks=(b"{}",)):
    """Drives an ASGI app once; returns (status, response_headers dict, body bytes)."""
    sent, incoming = [], list(chunks)
    scope = {"type": "http", "method": method, "path": path, "headers": [(k.lower(), v) for k, v in headers]}

    async def receive():
        body = incoming.pop(0) if incoming else b""
        return {"type": "http.request", "body": body, "more_body": bool(incoming)}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k: v for k, v in start["headers"]}, body


def reading_app(extra_headers=()):
    """An app that reads the whole body, like FastAPI does before validating it."""
    async def app(scope, receive, send):
        size = 0
        while True:
            message = await receive()
            size += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": [*extra_headers]})
        await send({"type": "http.response.body", "body": str(size).encode()})
    return app


class BodyLimitTest(unittest.TestCase):
    def mw(self, **kw):
        return SecurityMiddleware(reading_app(), max_body_bytes=100, **kw)

    def test_small_body_passes(self):
        status, _, body = run(self.mw(), headers=[(b"content-length", b"2")])
        self.assertEqual((status, body), (200, b"2"))

    def test_declared_oversize_is_rejected_before_the_app_runs(self):
        called = []

        async def app(scope, receive, send):
            called.append(1)

        status, headers, body = run(SecurityMiddleware(app, max_body_bytes=100), headers=[(b"content-length", b"101")])
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body), {"detail": "Request too large"})
        self.assertEqual(called, [])
        self.assertEqual(headers[b"x-content-type-options"], b"nosniff")

    def test_chunked_upload_without_content_length_is_cut_off(self):
        status, _, _ = run(self.mw(), chunks=[b"x" * 60, b"x" * 60])
        self.assertEqual(status, 413)

    def test_get_requests_and_exact_limit_are_not_blocked(self):
        self.assertEqual(run(self.mw(), method="GET", headers=[(b"content-length", b"500")])[0], 200)
        self.assertEqual(run(self.mw(), chunks=[b"x" * 100], headers=[(b"content-length", b"100")])[0], 200)

    def test_garbage_content_length_is_left_to_the_server(self):
        self.assertEqual(run(self.mw(), headers=[(b"content-length", b"abc")])[0], 200)


class HeadersTest(unittest.TestCase):
    def test_defensive_headers_on_every_response(self):
        _, headers, _ = run(SecurityMiddleware(reading_app()), path="/health", method="GET")
        self.assertEqual(headers[b"x-content-type-options"], b"nosniff")
        self.assertEqual(headers[b"referrer-policy"], b"no-referrer")
        self.assertNotIn(b"cache-control", headers)              # normal routes keep their own caching

    def test_personal_data_routes_are_never_cached(self):
        for path in ["/lead", "/internal/retry-lead-notifications"]:
            with self.subTest(path=path):
                _, headers, _ = run(SecurityMiddleware(reading_app()), path=path)
                self.assertEqual(headers[b"cache-control"], b"no-store")

    def test_a_route_that_sets_its_own_headers_is_not_overridden_or_duplicated(self):
        app = SecurityMiddleware(reading_app([(b"cache-control", b"no-cache, no-transform"),
                                              (b"x-content-type-options", b"nosniff")]))
        status, headers, _ = run(app, path="/lead")
        self.assertEqual(headers[b"cache-control"], b"no-cache, no-transform")

        sent = []
        scope = {"type": "http", "method": "GET", "path": "/lead", "headers": []}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            sent.append(m)
        asyncio.run(app(scope, receive, send))
        names = [k for k, _ in sent[0]["headers"]]
        self.assertEqual(names.count(b"x-content-type-options"), 1)

    def test_non_http_scopes_pass_straight_through(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        asyncio.run(SecurityMiddleware(app)({"type": "lifespan"}, None, None))
        self.assertEqual(seen, ["lifespan"])


if __name__ == "__main__":
    unittest.main()
