"""Request ids, crash handling, log redaction and the stats endpoint through the real app (pytest, fake DB)."""
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.core.config import Settings, get_settings
from app.core.observability import LogContextFilter
from app.db.session import engine, get_db
from app.main import app

ADMIN = "a-long-random-admin-token-0123456789abcdef"


def cfg(**over) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://t:t@localhost/t", **over)


@pytest.fixture(autouse=True)
def _reset():
    for fn in (rate_limit_module._limiters, rate_limit_module._lead_limiter, rate_limit_module._admin_limiter):
        fn.cache_clear()
    yield
    app.dependency_overrides.clear()


def test_every_response_carries_a_request_id_and_a_safe_inbound_id_is_kept():
    client = TestClient(app)
    assert len(client.get("/").headers["x-request-id"]) == 16
    assert client.get("/", headers={"X-Request-ID": "trace-12345678"}).headers["x-request-id"] == "trace-12345678"
    assert client.get("/", headers={"X-Request-ID": "bad id"}).headers["x-request-id"] != "bad id"


def test_a_crash_returns_json_with_the_request_id_and_logs_it(caplog):
    async def boom():
        raise RuntimeError("kaboom")

    app.add_api_route("/__boom", boom)
    try:
        caplog.set_level(logging.ERROR)
        response = TestClient(app, raise_server_exceptions=False).get("/__boom", headers={"X-Request-ID": "trace-crash0001"})
    finally:
        app.router.routes.pop()
    assert response.status_code == 500
    body = response.json()
    assert body["request_id"] == "trace-crash0001" == response.headers["x-request-id"]
    assert "hello@sharpbuild.io" in body["detail"] and "kaboom" not in response.text
    assert any("unhandled error request_id=trace-crash0001" in r.getMessage() for r in caplog.records)


def test_database_errors_do_not_quote_sql_parameters():
    assert engine.hide_parameters is True


def test_a_failed_lead_save_does_not_write_the_visitors_email_to_the_log(monkeypatch):
    import io
    root = logging.getLogger()
    handler = next(h for h in root.handlers if any(isinstance(f, LogContextFilter) for f in h.filters))
    buffer = io.StringIO()
    previous = handler.setStream(buffer)

    class FailingDb:
        def execute(self, *a, **k):
            return SimpleNamespace(first=lambda: None)

        def add(self, r):
            pass

        def commit(self):       # what a driver error looks like when parameters are not hidden
            raise RuntimeError("insert failed [parameters: {'email': 'ali@example.com', 'phone': '0300-1234567'}]")

        def rollback(self):
            pass

    app.dependency_overrides[get_db] = lambda: FailingDb()
    app.dependency_overrides[get_settings] = lambda: cfg()
    try:
        response = TestClient(app).post("/lead", json={"name": "Ali", "email": "ali@example.com", "consent": True})
    finally:
        handler.setStream(previous)
    assert response.status_code == 503
    logged = buffer.getvalue()
    assert "lead save failed" in logged and "RuntimeError" in logged
    assert "ali@example.com" not in logged and "1234567" not in logged


class StatsDb:
    def __init__(self, row):
        self.row = row

    def execute(self, *a, **k):
        return SimpleNamespace(one=lambda: self.row)


def stats_client(row=(10, 3, 1, 2, 0), **over):
    settings = cfg(admin_token=ADMIN, **over)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: StatsDb(row)
    return TestClient(app)


def test_stats_requires_the_admin_token():
    client = stats_client()
    assert client.get("/internal/stats").status_code == 401
    assert client.get("/internal/stats", headers={"X-Admin-Token": "wrong"}).status_code == 401
    app.dependency_overrides[get_settings] = lambda: cfg()                  # no ADMIN_TOKEN configured
    assert TestClient(app).get("/internal/stats", headers={"X-Admin-Token": ADMIN}).status_code == 404


def test_stats_reports_volume_and_stuck_notifications():
    client = stats_client((10, 3, 1, 2, 4), lead_webhook_url="https://x.example/h", lead_webhook_secret="s")
    response = client.get("/internal/stats", headers={"Authorization": f"Bearer {ADMIN}"})
    assert response.status_code == 200
    assert response.json() == {
        "leads": {"total": 10, "last_24h": 3, "handoff_last_24h": 1},
        "notifications": {"configured": True, "pending": 2, "gave_up": 4},
    }
    assert response.headers["cache-control"] == "no-store"


def test_stats_says_when_no_notification_channel_is_configured():
    response = stats_client().get("/internal/stats", headers={"X-Admin-Token": ADMIN})
    assert response.json()["notifications"]["configured"] is False
