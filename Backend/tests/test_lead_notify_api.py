"""Notification wiring: POST /lead -> notifier, and the protected retry endpoint (pytest, fake DB)."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import app
from app.schemas.lead import LeadRequest
from app.services import lead_notify
from app.services.lead_service import build_record, retry_pending

GOOD = {"name": "Ali Khan", "email": "ali@example.com", "consent": True}
ADMIN = "a-long-random-admin-token-0123456789abcdef"
HOOK = dict(lead_webhook_url="https://crm.example.com/hook", lead_webhook_secret="s3cret")


def cfg(**over) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://t:t@localhost/t", **over)


class FakeDb:
    def __init__(self, pending=()):
        self.added, self.commits, self.rollbacks, self.pending = [], 0, 0, list(pending)

    def execute(self, *_a, **_k):
        return SimpleNamespace(first=lambda: None, scalars=lambda: SimpleNamespace(all=lambda: self.pending))

    def add(self, record):
        self.added.append(record)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, record):
        record.id = 1


@pytest.fixture(autouse=True)
def _reset():
    rate_limit_module._lead_limiter.cache_clear()
    yield
    rate_limit_module._lead_limiter.cache_clear()
    app.dependency_overrides.clear()


def client_with(db, settings):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_saved_lead_is_sent_to_the_webhook_and_marked_notified(monkeypatch):
    calls = []
    monkeypatch.setattr(lead_notify, "send_webhook", lambda payload, *a, **k: calls.append(payload))
    db = FakeDb()
    assert client_with(db, cfg(**HOOK)).post("/lead", json=GOOD).status_code == 200
    assert len(calls) == 1 and calls[0]["email"] == "ali@example.com" and calls[0]["id"] == 1
    assert db.added[0].notified_at is not None and db.added[0].notify_attempts == 1


def test_webhook_failure_never_fails_the_visitor_and_leaves_lead_pending(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(lead_notify, "send_webhook", boom)
    db = FakeDb()
    assert client_with(db, cfg(**HOOK)).post("/lead", json=GOOD).status_code == 200
    assert db.added[0].notified_at is None and db.added[0].notify_attempts == 1


def test_nothing_is_sent_when_no_channel_is_configured(monkeypatch):
    monkeypatch.setattr(lead_notify, "send_webhook", lambda *a, **k: pytest.fail("must not send"))
    db = FakeDb()
    assert client_with(db, cfg()).post("/lead", json=GOOD).status_code == 200
    assert db.added[0].notified_at is None and db.added[0].notify_attempts in (None, 0)


def test_a_plain_http_webhook_url_is_never_used(monkeypatch):
    monkeypatch.setattr(lead_notify, "send_webhook", lambda *a, **k: pytest.fail("http must not be used"))
    settings = cfg(lead_webhook_url="http://crm.example.com/hook", lead_webhook_secret="s")
    assert client_with(FakeDb(), settings).post("/lead", json=GOOD).status_code == 200


def test_retry_endpoint_does_not_exist_without_an_admin_token():
    assert client_with(FakeDb(), cfg(**HOOK)).post("/internal/retry-lead-notifications").status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Token": "wrong"}, {"Authorization": "Bearer wrong"}])
def test_retry_endpoint_rejects_missing_or_wrong_token(headers):
    client = client_with(FakeDb(), cfg(admin_token=ADMIN, **HOOK))
    assert client.post("/internal/retry-lead-notifications", headers=headers).status_code == 401


@pytest.mark.parametrize("method,headers", [
    ("post", {"X-Admin-Token": ADMIN}), ("get", {"Authorization": f"Bearer {ADMIN}"}),   # GET: Vercel Cron
])
def test_retry_endpoint_resends_pending_leads(monkeypatch, method, headers):
    sent = []
    monkeypatch.setattr(lead_notify, "send_webhook", lambda payload, *a, **k: sent.append(payload["id"]))
    pending = [build_record(LeadRequest(**GOOD)) for _ in range(2)]
    for i, record in enumerate(pending, start=10):
        record.id = i
    db = FakeDb(pending)
    response = getattr(client_with(db, cfg(admin_token=ADMIN, **HOOK)), method)(
        "/internal/retry-lead-notifications", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"configured": True, "checked": 2, "sent": 2}
    assert sent == [10, 11] and all(r.notified_at for r in pending)


def test_retry_does_nothing_when_unconfigured():
    assert retry_pending(FakeDb([object()]), cfg()) == {"configured": False, "checked": 0, "sent": 0}
