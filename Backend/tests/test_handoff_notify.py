"""Handoff vs sales in lead notifications (services/lead_notify.py). Pure Python."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from app.services import lead_notify as ln


class FakeSmtp:
    sent = None

    def __init__(self, host, port, timeout=None, context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, *a):
        pass

    def send_message(self, message):
        FakeSmtp.sent = message


CFG = NS(smtp_host="h", smtp_port=587, smtp_user="", smtp_password="", lead_email_from="a@b.co",
         lead_email_to="c@d.co", notify_timeout_seconds=4.0)


def record(**over):
    base = dict(id=3, name="Ali", email="ali@example.com", phone=None, company=None, message="Need a human",
                score="warm", need=False, budget=False, timeline=False,
                consent_at=datetime(2026, 11, 19, tzinfo=timezone.utc), consent_version="v1", created_at=None,
                kind="handoff", context=None)
    return NS(**{**base, **over})


class HandoffNotifyTest(unittest.TestCase):
    def test_payload_marks_handoff_and_carries_opt_in_context(self):
        p = ln.lead_payload(record(context="- I want a human"))
        self.assertEqual((p["kind"], p["context"]), ("handoff", "- I want a human"))

    def test_payload_defaults_to_sales_for_older_records(self):
        p = ln.lead_payload(NS(**{k: v for k, v in record().__dict__.items() if k not in ("kind", "context")}))
        self.assertEqual((p["kind"], p["context"]), ("sales", None))

    def test_handoff_email_is_clearly_labelled(self):
        ln.send_email(record(), CFG, smtp_factory=FakeSmtp)
        msg = FakeSmtp.sent
        self.assertTrue(msg["Subject"].startswith("HANDOFF REQUEST: Ali"))
        body = msg.get_content()
        self.assertIn("asked to talk to a person", body)
        self.assertIn("Chat context: not shared", body)

    def test_shared_context_appears_in_the_email(self):
        ln.send_email(record(context="- I need a human\n- about pricing"), CFG, smtp_factory=FakeSmtp)
        body = FakeSmtp.sent.get_content()
        self.assertIn("shared by them", body)
        self.assertIn("- about pricing", body)

    def test_sales_email_keeps_its_old_subject(self):
        ln.send_email(record(kind="sales", score="hot"), CFG, smtp_factory=FakeSmtp)
        self.assertTrue(FakeSmtp.sent["Subject"].startswith("New hot lead: Ali"))
        self.assertIn("Type: sales enquiry", FakeSmtp.sent.get_content())


if __name__ == "__main__":
    unittest.main()
