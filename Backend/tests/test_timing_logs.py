import logging
from types import SimpleNamespace

import pytest

from app.services import chat_service
from app.services.ai_service import make_gemini_answerer
from app.services.chat_service import answer_question
from app.services.knowledge_service import Hit, retrieve


class FakeDb:
    def execute(self, stmt):
        return [SimpleNamespace(chunk_id="c1", url="https://sharpbuild.io/a", title="A", section="S",
                                page_type="services", content="text", dist=0.25)]


def test_retrieve_logs_embedding_and_database_time_separately(caplog):
    with caplog.at_level(logging.INFO, logger="sharpbuild.retrieval"):
        hits = retrieve(FakeDb(), "question", lambda texts: [[0.0] * 1536], k=4)
    assert hits[0].similarity == pytest.approx(0.75)
    assert "embed_ms=" in caplog.text and "db_ms=" in caplog.text and "hits=1" in caplog.text


class ApiError(Exception):
    def __init__(self, code):
        self.code = code


class Scripted:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def generate_content(self, **kw):
        outcome = self.outcomes[kw["model"]]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


HIT = Hit("c", "https://sharpbuild.io/a", "A", "S", "services", "text", 0.9)


def test_answerer_logs_which_model_answered_and_why_others_failed(caplog):
    answer = make_gemini_answerer("k", "main", client=SimpleNamespace(models=Scripted({"main": ApiError(503), "backup": "ok [1]"})),
                                  fallbacks=["backup"])
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        assert answer("q", [HIT]) == "ok [1]"
    assert "model main failed after" in caplog.text and "(503)" in caplog.text and "trying backup" in caplog.text
    assert "model backup answered in" in caplog.text


def test_answerer_logs_when_it_gives_up(caplog):
    answer = make_gemini_answerer("k", "main", client=SimpleNamespace(models=Scripted({"main": ApiError(400)})))
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        with pytest.raises(ApiError):
            answer("q", [HIT])
    assert "model main failed after" in caplog.text and "giving up" in caplog.text


def test_chat_summary_line_includes_stage_timings(caplog):
    original = chat_service.retrieve
    chat_service.retrieve = lambda *a, **k: [HIT]
    try:
        with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
            answer_question(None, "Do you build apps?", lambda t: [[0.0]], lambda q, h: "Yes [1]", min_similarity=0.58, k=4)
    finally:
        chat_service.retrieve = original
    assert "retrieve_ms=" in caplog.text and "answer_ms=" in caplog.text and "outcome=answered" in caplog.text
