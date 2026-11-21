"""scripts/smoke_test.py against a small local fake API: one correct, one deliberately misconfigured."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.smoke_test import main, run_checks

ORIGIN = "https://www.sharpbuild.io"
TOKEN = "t" * 40


def make_handler(bad: bool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body=b"", headers=None):
            self.send_response(status)
            base = {} if bad else {"X-Content-Type-Options": "nosniff", "X-Request-ID": "abcdef0123456789"}
            for key, value in {**base, **(headers or {})}.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def read_body(self):
            return self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))

        def authed(self):
            return bad or self.headers.get("Authorization") == f"Bearer {TOKEN}"

        def do_GET(self):
            if self.path == "/health":
                return self.send(200, b'{"status":"ok"}', {"Content-Type": "application/json"})
            if self.path in ("/docs", "/redoc", "/openapi.json"):
                return self.send(200 if bad else 404, b"{}")
            if self.path == "/internal/stats":
                if not self.authed():
                    return self.send(401, b"{}")
                stats = {"leads": {"total": 1}, "notifications": {"configured": True, "pending": 0, "gave_up": 0 if not bad else 3}}
                return self.send(200, json.dumps(stats).encode(), {"Content-Type": "application/json"})
            self.send(404, b"{}")

        def do_OPTIONS(self):
            origin = self.headers.get("Origin", "")
            if bad or origin == ORIGIN:
                return self.send(200, b"", {"Access-Control-Allow-Origin": origin})
            self.send(400, b"Disallowed CORS origin")

        def do_POST(self):
            body = self.read_body()
            if self.path == "/lead":
                if bad:
                    return self.send(500, b"boom")
                if len(body) > 32768:
                    return self.send(413, b"{}", {"Cache-Control": "no-store"})
                return self.send(422, b"{}", {"Cache-Control": "no-store"})
            if self.path == "/internal/retry-lead-notifications":
                return self.send(200 if bad else 401, b"{}")
            if self.path == "/chat/stream":
                headers = {"Content-Type": "text/event-stream"}
                if not bad:
                    headers.update({"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
                frames = [{"type": "start"}, {"type": "delta", "text": "We build apps."},
                          {"type": "done" if not bad else "error", "answer": "We build apps.", "sources": []}]
                return self.send(200, "".join(f"data: {json.dumps(f)}\n\n" for f in frames).encode(), headers)
            self.send(404, b"{}")
    return Handler


class FakeApi:
    def __init__(self, bad=False):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bad))
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def failed(checks):
    return sorted(c.name for c in checks if not c.ok)


class SmokeTest(unittest.TestCase):
    def test_a_correct_deployment_passes_every_check(self):
        with FakeApi() as api:
            checks = run_checks(api.url, ORIGIN, chat=True, token=TOKEN, timeout=5)
        self.assertEqual(failed(checks), [])
        self.assertGreaterEqual(len(checks), 14)

    def test_a_misconfigured_deployment_is_caught_check_by_check(self):
        with FakeApi(bad=True) as api:
            checks = run_checks(api.url, ORIGIN, chat=True, token=TOKEN, timeout=5)
        self.assertEqual(failed(checks), sorted([
            "responses carry a request id",
            "nosniff header present",
            "API docs are hidden",
            "CORS refuses other origins",
            "lead form rejects an empty submission (422, not 500)",
            "lead responses are not cached",
            "oversized request body is refused (413)",
            "admin endpoints are closed without a token",
            "no lead notification has given up",
            "stream is not buffered or transformed",
            "stream ends with a done event",
        ]))

    def test_wrong_origin_is_reported(self):
        with FakeApi() as api:
            checks = run_checks(api.url, "https://typo.example", timeout=5)
        self.assertEqual(failed(checks), ["CORS allows the website origin"])

    def test_without_flags_no_chat_or_admin_checks_run(self):
        with FakeApi() as api:
            names = [c.name for c in run_checks(api.url, ORIGIN, timeout=5)]
        self.assertFalse(any(n.startswith("stream") or "stats" in n for n in names))

    def test_an_unreachable_server_is_a_failed_check_not_a_crash(self):
        checks = run_checks("http://127.0.0.1:1", ORIGIN, timeout=1)
        self.assertTrue(checks and all(not c.ok for c in checks))

    def test_exit_codes(self):
        with FakeApi() as api:
            self.assertEqual(main([api.url, "--origin", ORIGIN, "--timeout", "5"]), 0)
        with FakeApi(bad=True) as api:
            self.assertEqual(main([api.url, "--origin", ORIGIN, "--timeout", "5"]), 1)


if __name__ == "__main__":
    unittest.main()
