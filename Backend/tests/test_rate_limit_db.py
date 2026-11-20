"""Shared (database) rate limiting and admin hardening. Fake DB session: no database needed."""
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit as rl
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import app


class FakeSession:
    """Mimics the INSERT ... ON CONFLICT ... RETURNING hits counter."""
    counters: dict = {}
    fail = False
    executed: list = []

    def __enter__(self):
        if FakeSession.fail:
            raise RuntimeError("db down")
        return self

    def __exit__(self, *a):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        FakeSession.executed.append((sql, params))
        if sql.startswith("INSERT"):
            k = (params["key"], params["window"])
            FakeSession.counters[k] = FakeSession.counters.get(k, 0) + 1
            return SimpleNamespace(scalar_one=lambda: FakeSession.counters[k])
        return SimpleNamespace()

    def commit(self):
        pass


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    FakeSession.counters, FakeSession.fail, FakeSession.executed = {}, False, []
    monkeypatch.setattr(rl, "SessionLocal", FakeSession)
    for fn in (rl._limiters, rl._lead_limiter, rl._admin_limiter):
        fn.cache_clear()
    yield
    app.dependency_overrides.clear()


def cfg(**over) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://t:t@localhost/t", **over)


def test_db_retry_after_counts_per_key_and_reports_seconds_until_the_window_ends():
    now = lambda: 600.0 + 20          # 20 s into minute #10
    checks = [("visitor", 2), ("global", 100)]
    assert rl.db_retry_after(checks, now=now, cleanup_chance=0) == 0.0
    assert rl.db_retry_after(checks, now=now, cleanup_chance=0) == 0.0
    wait = rl.db_retry_after(checks, now=now, cleanup_chance=0)
    assert wait == pytest.approx(40.0)


def test_a_blocked_visitor_does_not_use_up_the_global_quota():
    now = lambda: 0.0
    for _ in range(3):
        rl.db_retry_after([("v", 1), ("g", 100)], now=now, cleanup_chance=0)
    assert FakeSession.counters[("g", 0)] == 1            # only the first, allowed request reached it


def test_old_windows_are_cleaned_up_and_new_window_starts_fresh():
    rl.db_retry_after([("v", 1)], now=lambda: 0.0, cleanup_chance=0)
    assert rl.db_retry_after([("v", 1)], now=lambda: 61.0, cleanup_chance=0) == 0.0
    rl.db_retry_after([("v", 1)], now=lambda: 1000.0, cleanup_chance=1)
    assert any(sql.startswith("DELETE") for sql, _ in FakeSession.executed)


def test_keys_are_hashed_so_no_ip_address_is_stored():
    key = rl._db_key("chat", "203.0.113.7")
    assert "203.0.113.7" not in key and len(key) == 32
    assert key != rl._db_key("lead", "203.0.113.7")


def test_chat_limit_is_shared_through_the_database():
    settings = cfg(rate_limit_backend="database", rate_limit_per_minute=2, gemini_api_key="k")
    app.dependency_overrides[get_settings] = lambda: settings
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.7"))
    rl.rate_limit(request, settings)
    rl.rate_limit(request, settings)
    with pytest.raises(Exception) as caught:
        rl.rate_limit(request, settings)
    assert caught.value.status_code == 429 and 1 <= int(caught.value.headers["Retry-After"]) <= 60
    # the in-memory limiters were never touched: the database was the source of truth
    assert rl._limiters.cache_info().currsize == 0


def test_database_failure_falls_back_to_the_memory_limiter_and_does_not_block_chat():
    FakeSession.fail = True
    settings = cfg(rate_limit_backend="database", rate_limit_per_minute=2)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.8"))
    rl.rate_limit(request, settings)
    rl.rate_limit(request, settings)
    with pytest.raises(Exception) as caught:
        rl.rate_limit(request, settings)
    assert caught.value.status_code == 429                  # still limited, by the memory limiter


def test_global_lead_cap_stops_a_rotating_attacker():
    settings = cfg(lead_rate_limit_per_minute=100, lead_global_rate_limit_per_minute=3)
    for i in range(3):
        rl.lead_rate_limit(SimpleNamespace(headers={}, client=SimpleNamespace(host=f"10.0.0.{i}")), settings)
    with pytest.raises(Exception) as caught:
        rl.lead_rate_limit(SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.99")), settings)
    assert caught.value.status_code == 429


ADMIN = "a-long-random-admin-token-0123456789abcdef"


def admin_client(**over):
    settings = cfg(admin_token=ADMIN, **over)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [])))
    return TestClient(app)


def test_a_short_admin_token_disables_the_endpoint():
    settings = cfg(admin_token="short-token")
    app.dependency_overrides[get_settings] = lambda: settings
    response = TestClient(app).post("/internal/retry-lead-notifications", headers={"X-Admin-Token": "short-token"})
    assert response.status_code == 404


def test_guessing_the_admin_token_is_throttled():
    client = admin_client(admin_rate_limit_per_minute=3, lead_webhook_url="https://x.example/h", lead_webhook_secret="s")
    codes = [client.post("/internal/retry-lead-notifications", headers={"X-Admin-Token": "guess"}).status_code
             for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_admin_endpoint_still_works_with_the_right_token():
    client = admin_client(lead_webhook_url="https://x.example/h", lead_webhook_secret="s")
    response = client.post("/internal/retry-lead-notifications", headers={"X-Admin-Token": ADMIN})
    assert response.status_code == 200 and response.json()["configured"] is True
    assert response.headers["cache-control"] == "no-store"


def test_api_responses_carry_security_headers_and_oversized_bodies_are_rejected():
    client = TestClient(app)
    ok = client.get("/")
    assert ok.headers["x-content-type-options"] == "nosniff" and ok.headers["referrer-policy"] == "no-referrer"
    big = client.post("/lead", content=b"{" + b" " * 40_000 + b"}", headers={"Content-Type": "application/json"})
    assert big.status_code == 413


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_real_postgres_counter():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.rate_limit import RateLimitHit

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    RateLimitHit.__table__.create(engine, checkfirst=True)
    rl.SessionLocal = sessionmaker(bind=engine)           # restored by monkeypatch teardown order below
    key = "pytest-real-counter"
    try:
        assert rl.db_retry_after([(key, 2)], cleanup_chance=0) == 0.0
        assert rl.db_retry_after([(key, 2)], cleanup_chance=0) == 0.0
        assert rl.db_retry_after([(key, 2)], cleanup_chance=0) > 0
    finally:
        with engine.begin() as conn:
            conn.execute(RateLimitHit.__table__.delete().where(RateLimitHit.key == key))
