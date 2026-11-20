"""Webhook/email delivery of saved leads (services/lead_notify.py). Pure Python: no network, no DB."""
import hashlib
import hmac
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from app.services import lead_notify as ln


def settings(**over):
    base = dict(lead_webhook_url="https://crm.example.com/hook", lead_webhook_secret="s3cret",
                smtp_host="", smtp_port=587, smtp_user="", smtp_password="", lead_email_from="",
                lead_email_to="", notify_timeout_seconds=4.0)
    return NS(**{**base, **over})


def record(**over):
    base = dict(id=7, name="Ali Khan", email="ali@example.com", phone="0300-1234567", company="Acme",
                message="I need an app", score="hot", need=True, budget=True, timeline=False,
                consent_at=datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc), consent_version="2026-11-v1",
                created_at=datetime(2026, 11, 19, 8, 0, 1, tzinfo=timezone.utc), notify_attempts=0, notified_at=None)
    return NS(**{**base, **over})


class FakeDb:
    def __init__(self, fail_commit=False):
        self.commits, self.rollbacks, self.fail_commit = 0, 0, fail_commit

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("db down")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class PayloadAndSignatureTest(unittest.TestCase):
    def test_payload_has_lead_fields_and_consent_but_no_conversation(self):
        p = ln.lead_payload(record())
        self.assertEqual((p["id"], p["email"], p["score"]), (7, "ali@example.com", "hot"))
        self.assertEqual(p["signals"], {"need": True, "budget": True, "timeline": False})
        self.assertEqual(p["consent"]["version"], "2026-11-v1")
        self.assertNotIn("history", p)
        json.dumps(p)                                           # serialisable

    def test_signature_matches_independent_hmac_and_binds_timestamp(self):
        body = b'{"id":7}'
        expected = "sha256=" + hmac.new(b"k", b"1700000000." + body, hashlib.sha256).hexdigest()
        self.assertEqual(ln.sign(body, "k", "1700000000"), expected)
        self.assertNotEqual(ln.sign(body, "k", "1700000001"), expected)
        self.assertNotEqual(ln.sign(body, "other", "1700000000"), expected)


class WebhookTest(unittest.TestCase):
    def test_posts_signed_json_with_timeout(self):
        seen = {}

        def opener(request, timeout):
            seen.update(request=request, timeout=timeout)
            return FakeResponse(204)

        ln.send_webhook({"id": 7, "name": "Zoë"}, "https://crm.example.com/hook", "k", 3.5, opener=opener, now=lambda: 1700000000)
        req = seen["request"]
        self.assertEqual((req.get_method(), req.full_url, seen["timeout"]), ("POST", "https://crm.example.com/hook", 3.5))
        self.assertEqual(req.get_header("X-sharpbuild-timestamp"), "1700000000")
        self.assertEqual(req.get_header("X-sharpbuild-signature"), ln.sign(req.data, "k", "1700000000"))
        self.assertEqual(json.loads(req.data), {"id": 7, "name": "Zoë"})

    def test_non_2xx_and_network_errors_raise(self):
        with self.assertRaises(RuntimeError):
            ln.send_webhook({}, "https://x.example", "k", 1, opener=lambda r, timeout: FakeResponse(500))

        def boom(r, timeout):
            raise urllib.error.URLError("down")
        with self.assertRaises(urllib.error.URLError):
            ln.send_webhook({}, "https://x.example", "k", 1, opener=boom)

    def test_enabled_only_for_https_with_a_secret(self):
        self.assertTrue(ln.webhook_enabled(settings()))
        self.assertFalse(ln.webhook_enabled(settings(lead_webhook_url="http://crm.example.com/hook")))
        self.assertFalse(ln.webhook_enabled(settings(lead_webhook_secret="")))
        self.assertFalse(ln.webhook_enabled(settings(lead_webhook_url="")))


class FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.args, self.calls, self.sent = (host, port, timeout, context), [], None
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.sent = message


class EmailTest(unittest.TestCase):
    def cfg(self, **over):
        return settings(smtp_host="smtp.example.com", lead_email_from="bot@sharpbuild.io",
                        lead_email_to="sales@sharpbuild.io", smtp_user="u", smtp_password="p", **over)

    def test_starttls_login_and_message_content(self):
        FakeSmtp.instances.clear()
        ln.send_email(record(), self.cfg(), smtp_factory=FakeSmtp)
        server = FakeSmtp.instances[0]
        self.assertEqual(server.calls, ["starttls", ("login", "u", "p")])
        self.assertEqual(server.args[:3], ("smtp.example.com", 587, 4.0))
        msg = server.sent
        self.assertEqual((msg["To"], msg["From"], msg["Reply-To"]), ("sales@sharpbuild.io", "bot@sharpbuild.io", "ali@example.com"))
        self.assertIn("New hot lead: Ali Khan", msg["Subject"])
        self.assertIn("I need an app", msg.get_content())

    def test_port_465_uses_ssl_without_starttls(self):
        FakeSmtp.instances.clear()
        ln.send_email(record(), self.cfg(smtp_port=465), smtp_factory=None, smtp_ssl_factory=FakeSmtp)
        self.assertEqual(FakeSmtp.instances[0].calls, [("login", "u", "p")])

    def test_line_breaks_in_name_cannot_inject_headers(self):
        FakeSmtp.instances.clear()
        ln.send_email(record(name="Evil\r\nBcc: attacker@example.com"), self.cfg(), smtp_factory=FakeSmtp)
        msg = FakeSmtp.instances[0].sent
        self.assertNotIn("\n", msg["Subject"])
        self.assertIsNone(msg["Bcc"])


class NotifyLeadTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._orig = (ln.send_webhook, ln.send_email)
        ln.send_webhook = lambda *a, **k: self.sent.append("webhook")
        ln.send_email = lambda *a, **k: self.sent.append("email")

    def tearDown(self):
        ln.send_webhook, ln.send_email = self._orig

    def both(self):
        return settings(smtp_host="h", lead_email_from="a@b.co", lead_email_to="c@d.co")

    def test_no_channel_configured_is_a_noop(self):
        db, rec = FakeDb(), record()
        self.assertFalse(ln.notify_lead(db, rec, settings(lead_webhook_url="")))
        self.assertEqual((db.commits, rec.notify_attempts, rec.notified_at, self.sent), (0, 0, None, []))

    def test_success_marks_notified_and_counts_attempt(self):
        db, rec = FakeDb(), record()
        self.assertTrue(ln.notify_lead(db, rec, self.both()))
        self.assertEqual(self.sent, ["webhook", "email"])
        self.assertIsNotNone(rec.notified_at)
        self.assertEqual((rec.notify_attempts, db.commits), (1, 1))

    def test_one_failing_channel_keeps_the_lead_pending(self):
        def bad(*a, **k):
            raise ConnectionError("https://secret-url.example/token")
        ln.send_email = bad
        db, rec = FakeDb(), record()
        with self.assertLogs("sharpbuild.notify", "INFO") as logs:
            self.assertFalse(ln.notify_lead(db, rec, self.both()))
        self.assertIsNone(rec.notified_at)
        self.assertEqual(rec.notify_attempts, 1)
        text = "\n".join(logs.output)
        self.assertIn("ConnectionError", text)
        self.assertNotIn("secret-url", text)                  # error text/URL never logged
        self.assertNotIn("ali@example.com", text)

    def test_never_raises_even_if_the_database_fails(self):
        db = FakeDb(fail_commit=True)
        self.assertTrue(ln.notify_lead(db, record(), self.both()))
        self.assertEqual(db.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
