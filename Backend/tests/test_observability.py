"""Request ids, redaction, JSON logs and the request-log middleware (core/observability.py). Pure Python."""
import asyncio
import io
import json
import logging
import unittest

from app.core import observability as ob


def run(app, path="/chat", method="POST", headers=()):
    sent = []
    scope = {"type": "http", "method": method, "path": path, "headers": [(k.lower(), v) for k, v in headers]}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(ob.RequestLogMiddleware(app)(scope, receive, send))
    return scope, sent


def ok_app(seen=None, status=200):
    async def app(scope, receive, send):
        if seen is not None:
            seen.append(ob.request_id_var.get())
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    return app


class RequestIdTest(unittest.TestCase):
    def test_generated_when_absent_or_unsafe(self):
        self.assertRegex(ob.new_request_id(None), r"^[0-9a-f]{16}$")
        for bad in ["short", "has space in it 123", "x" * 65, "evil\nid-injected", "<script>alert(1)</script>"]:
            with self.subTest(bad=bad):
                self.assertRegex(ob.new_request_id(bad), r"^[0-9a-f]{16}$")

    def test_safe_inbound_id_is_kept(self):
        self.assertEqual(ob.new_request_id("req-1234.abcd_EF"), "req-1234.abcd_EF")


class RedactionTest(unittest.TestCase):
    def test_emails_and_phone_numbers_are_removed(self):
        text = "insert failed: {'email': 'ali.khan+x@example.co.uk', 'phone': '0300-1234567'} or +92 300 1234567"
        out = ob.redact(text)
        self.assertNotIn("example.co.uk", out)
        self.assertNotIn("1234567", out)
        self.assertEqual(out.count("[email]"), 1)
        self.assertEqual(out.count("[number]"), 2)

    def test_ordinary_log_numbers_survive(self):
        line = "chat outcome=answered top_similarity=0.812 question_chars=40 retrieve_ms=120 answer_ms=900 ms=1050"
        self.assertEqual(ob.redact(line), line)
        self.assertEqual(ob.redact("lead saved id=12345 score=hot"), "lead saved id=12345 score=hot")

    def test_request_ids_and_timestamps_are_not_mistaken_for_numbers(self):
        self.assertEqual(ob.redact("req 1234567890abcdef ok"), "req 1234567890abcdef ok")
        self.assertEqual(ob.redact("2026-11-19 08:25:00,123 INFO"), "2026-11-19 08:25:00,123 INFO")


def capture(fmt):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(ob.LogContextFilter())
    handler.setFormatter(ob.JsonFormatter() if fmt == "json" else logging.Formatter(ob.TEXT_FORMAT))
    logger = logging.getLogger("test.observability." + fmt)
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, stream


class FormatTest(unittest.TestCase):
    def test_text_lines_carry_the_request_id_and_no_personal_data(self):
        logger, stream = capture("text")
        token = ob.request_id_var.set("req-abc12345")
        try:
            logger.info("lead failed for %s", "ali@example.com")
        finally:
            ob.request_id_var.reset(token)
        line = stream.getvalue()
        self.assertIn("[req-abc12345]", line)
        self.assertIn("lead failed for [email]", line)
        self.assertNotIn("ali@example.com", line)

    def test_json_lines_are_valid_and_redacted_including_tracebacks(self):
        logger, stream = capture("json")
        try:
            raise RuntimeError("bad row: {'email': 'ali@example.com', 'phone': '+92 300 1234567'}")
        except RuntimeError:
            logger.exception("lead save failed")
        record = json.loads(stream.getvalue())
        self.assertEqual((record["level"], record["logger"], record["message"]),
                         ("ERROR", "test.observability.json", "lead save failed"))
        self.assertEqual(record["request_id"], "-")
        self.assertIn("RuntimeError", record["exception"])
        for leaked in ["ali@example.com", "1234567"]:
            self.assertNotIn(leaked, record["exception"])

    def test_configure_logging_replaces_handlers_and_sets_level(self):
        root = logging.getLogger()
        saved, level = list(root.handlers), root.level
        try:
            ob.configure_logging("json", "warning")
            self.assertEqual(len(root.handlers), 1)
            self.assertIsInstance(root.handlers[0].formatter, ob.JsonFormatter)
            self.assertEqual(root.level, logging.WARNING)
        finally:
            root.handlers[:] = saved
            root.setLevel(level)


class MiddlewareTest(unittest.TestCase):
    def test_every_response_gets_an_id_that_logs_can_see(self):
        seen = []
        with self.assertLogs("sharpbuild.request", "INFO") as logs:
            _, sent = run(ok_app(seen), path="/chat/stream")
        header = dict(sent[0]["headers"])[b"x-request-id"].decode()
        self.assertEqual(seen, [header])
        self.assertIn("request method=POST path=/chat/stream status=200 ms=", logs.output[0])
        self.assertEqual(ob.request_id_var.get(), "-")                  # reset afterwards

    def test_a_safe_inbound_id_is_echoed_and_an_unsafe_one_replaced(self):
        _, sent = run(ok_app(), headers=[(b"x-request-id", b"trace-12345678")])
        self.assertEqual(dict(sent[0]["headers"])[b"x-request-id"], b"trace-12345678")
        _, sent = run(ok_app(), headers=[(b"x-request-id", b"bad id\r\nX: y")])
        self.assertNotEqual(dict(sent[0]["headers"])[b"x-request-id"], b"bad id\r\nX: y")

    def test_summary_line_has_no_query_string_or_forged_lines(self):
        with self.assertLogs("sharpbuild.request", "INFO") as logs:
            run(ok_app(), path="/lead\nrequest method=GET path=/admin status=200 ms=1", method="GET")
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn("\n", logs.records[0].getMessage())

    def test_health_checks_are_quiet_and_server_errors_are_loud(self):
        with self.assertLogs("sharpbuild.request", "DEBUG") as logs:
            run(ok_app(), path="/health", method="GET")
        self.assertEqual(logs.records[0].levelno, logging.DEBUG)
        with self.assertLogs("sharpbuild.request", "DEBUG") as logs:
            run(ok_app(status=503), path="/chat")
        self.assertEqual(logs.records[0].levelno, logging.ERROR)

    def test_a_crash_is_logged_as_500_and_still_raised(self):
        async def boom(scope, receive, send):
            raise RuntimeError("boom")

        with self.assertLogs("sharpbuild.request", "INFO") as logs, self.assertRaises(RuntimeError):
            run(boom)
        self.assertIn("status=500", logs.output[0])
        self.assertEqual(logs.records[0].levelno, logging.ERROR)

    def test_non_http_scopes_pass_through(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        asyncio.run(ob.RequestLogMiddleware(app)({"type": "lifespan"}, None, None))
        self.assertEqual(seen, ["lifespan"])


if __name__ == "__main__":
    unittest.main()
