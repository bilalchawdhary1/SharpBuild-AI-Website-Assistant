"""Handoff requests through POST /lead (pytest, fake DB)."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.db.session import get_db
from app.main import app
from app.schemas.lead import LeadRequest
from app.services.ai_service import HANDOFF
from app.services.lead_service import build_record, shared_context

GOOD = {"name": "Ali Khan", "email": "ali@example.com", "consent": True}
HISTORY = [
    {"role": "user", "text": "hi"},
    {"role": "assistant", "text": "Contact hello@sharpbuild.io. Our secret assistant text"},
    {"role": "user", "text": "I need a human\nabout pricing"},
    {"role": "user", "text": "x" * 500},
    {"role": "user", "text": "last question"},
]


class FakeDb:
    def __init__(self):
        self.added = []

    def execute(self, *a, **k):
        return SimpleNamespace(first=lambda: None)

    def add(self, r):
        self.added.append(r)

    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, r):
        r.id = 1


@pytest.fixture(autouse=True)
def _reset():
    rate_limit_module._lead_limiter.cache_clear()
    yield
    rate_limit_module._lead_limiter.cache_clear()
    app.dependency_overrides.clear()


def post(payload):
    db = FakeDb()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app).post("/lead", json=payload), db


def test_handoff_reply_points_to_the_form_and_the_email():
    assert "form below" in HANDOFF and "hello@sharpbuild.io" in HANDOFF


def test_handoff_is_stored_with_its_kind_and_source_intent():
    response, db = post({**GOOD, "kind": "handoff", "message": "Please call me"})
    assert response.status_code == 200
    record = db.added[0]
    assert (record.kind, record.source_intent) == ("handoff", "human_handoff")


def test_default_kind_is_sales():
    _, db = post(GOOD)
    assert (db.added[0].kind, db.added[0].source_intent) == ("sales", "project_request")


def test_unknown_kind_is_rejected():
    response, db = post({**GOOD, "kind": "admin"})
    assert response.status_code == 422 and db.added == []


def test_chat_context_is_not_stored_unless_the_visitor_opts_in():
    _, db = post({**GOOD, "kind": "handoff", "history": HISTORY})
    assert db.added[0].context is None


def test_shared_context_has_only_the_visitors_last_messages_truncated():
    context = shared_context(LeadRequest(**GOOD, history=HISTORY, share_chat=True))
    lines = context.splitlines()
    assert len(lines) == 3                                   # last three visitor messages
    assert "secret assistant text" not in context and "hello@sharpbuild.io" not in context
    assert all(len(line) <= 302 for line in lines)           # "- " + 300 characters
    assert lines[-1] == "- last question"


def test_opt_in_context_reaches_the_record():
    _, db = post({**GOOD, "kind": "handoff", "history": HISTORY, "share_chat": True})
    assert "last question" in db.added[0].context


def test_share_chat_with_no_visitor_messages_stores_nothing():
    assert build_record(LeadRequest(**GOOD, share_chat=True)).context is None
