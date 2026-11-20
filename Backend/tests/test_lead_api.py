"""POST /lead and lead_service (pytest). Uses a fake DB session: no database needed."""
import logging
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.db.session import get_db
from app.main import app
from app.schemas.lead import LeadRequest
from app.services.lead_service import CONSENT_VERSION, build_record

GOOD = {"name": "Ali Khan", "email": "Ali@Example.com", "consent": True}


class FakeDb:
    def __init__(self, duplicate=False, fail=False):
        self.added, self.commits, self.rollbacks = [], 0, 0
        self.duplicate, self.fail = duplicate, fail

    def execute(self, *_a, **_k):
        return SimpleNamespace(first=lambda: (1,) if self.duplicate else None)

    def add(self, record):
        self.added.append(record)

    def commit(self):
        if self.fail:
            raise RuntimeError("db down")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, record):
        record.id = 1


@pytest.fixture(autouse=True)
def _fresh_limiter():
    rate_limit_module._lead_limiter.cache_clear()
    yield
    rate_limit_module._lead_limiter.cache_clear()
    app.dependency_overrides.clear()


def client_with(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_valid_lead_is_saved_with_server_side_score():
    db = FakeDb()
    payload = {**GOOD, "message": "I need an app by March, budget is $10k",
               "score": "cold"}                                     # client claim must be ignored
    response = client_with(db).post("/lead", json=payload)
    assert response.status_code == 200 and response.json() == {"ok": True}
    [record] = db.added
    assert record.score == "hot" and record.need and record.budget and record.timeline
    assert record.email == "ali@example.com"
    assert record.consent_version == CONSENT_VERSION and record.consent_at is not None
    assert record.status == "new" and db.commits == 1


def test_minimal_lead_is_warm_because_contact_was_given():
    db = FakeDb()
    assert client_with(db).post("/lead", json=GOOD).status_code == 200
    assert db.added[0].score == "warm"


def test_score_uses_visitor_history_but_not_assistant_email():
    history = [{"role": "user", "text": "I want to build a fintech app"},
               {"role": "assistant", "text": "Reach us at hello@sharpbuild.io in 2 weeks, budget $5k"}]
    record = build_record(LeadRequest(**GOOD, history=history))
    assert record.need is True and record.timeline is False and record.budget is False


@pytest.mark.parametrize("patch", [
    {"consent": False}, {"consent": None}, {"email": "not-an-email"}, {"name": "   "},
    {"phone": "abc"}, {"message": "x" * 1001}, {"name": "x" * 121},
])
def test_invalid_submissions_are_rejected_and_not_stored(patch):
    db = FakeDb()
    response = client_with(db).post("/lead", json={**GOOD, **patch})
    assert response.status_code == 422 and db.added == []


def test_missing_consent_is_rejected():
    db = FakeDb()
    payload = {k: v for k, v in GOOD.items() if k != "consent"}
    assert client_with(db).post("/lead", json=payload).status_code == 422 and db.added == []


def test_honeypot_pretends_success_and_stores_nothing():
    db = FakeDb()
    response = client_with(db).post("/lead", json={**GOOD, "website": "http://spam.example"})
    assert response.status_code == 200 and db.added == []


def test_duplicate_within_window_is_idempotent():
    db = FakeDb(duplicate=True)
    assert client_with(db).post("/lead", json=GOOD).status_code == 200 and db.added == []


def test_database_failure_returns_503_and_rolls_back():
    db = FakeDb(fail=True)
    response = client_with(db).post("/lead", json=GOOD)
    assert response.status_code == 503 and db.rollbacks == 1
    assert "hello@sharpbuild.io" in response.json()["detail"]


def test_lead_endpoint_is_rate_limited_per_visitor():
    client = client_with(FakeDb())
    codes = [client.post("/lead", json=GOOD).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_logs_never_contain_personal_details(caplog):
    caplog.set_level(logging.INFO)
    client_with(FakeDb()).post("/lead", json={**GOOD, "name": "Zed Unique", "phone": "0300-1234567"})
    assert "ali@example.com" not in caplog.text.lower()
    assert "Zed Unique" not in caplog.text and "1234567" not in caplog.text


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_save_and_dedupe_against_a_real_database():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.lead import LeadRecord
    from app.services.lead_service import save_lead

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    LeadRecord.__table__.create(engine, checkfirst=True)
    request = LeadRequest(name="Test", email="dedupe-test@example.com", consent=True)
    with Session(engine) as db:
        first = save_lead(db, request)
        try:
            assert first is not None and first.id
            assert save_lead(db, request) is None
        finally:
            if first is not None:
                db.delete(first)
                db.commit()
