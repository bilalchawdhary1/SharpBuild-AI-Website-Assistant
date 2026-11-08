import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.main import app
from app.schemas.chat import ChatRequest
from app.services import chat_service
from app.services.ai_service import (NO_ANSWER, NO_ANSWER_MARKER, UNAVAILABLE,
                                     make_gemini_answerer)
from app.services.chat_service import answer_question, attach_sources
from app.services.knowledge_service import Hit


def hit(n=1, url=None, page_type="services", sim=0.9, content="We build Shopify stores."):
    return Hit(f"chunk-{n}", url or f"https://sharpbuild.io/p{n}", f"Title {n}", f"Section {n}",
               page_type, content, sim)


# ---------- request validation ----------
def test_request_strips_message_and_rejects_blank_or_long():
    assert ChatRequest(message="  hello  ").message == "hello"
    with pytest.raises(ValueError, match="must not be blank"):
        ChatRequest(message="   ")
    with pytest.raises(ValueError):
        ChatRequest(message="x" * 501)


# ---------- Gemini answerer (prompt building) ----------
class FakeModels:
    def __init__(self, text="Yes. [1]"):
        self.calls, self.text = [], text

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


def test_answerer_sends_labelled_references_and_returns_text():
    fake = FakeModels("Yes, we build Shopify stores. [1]")
    answer = make_gemini_answerer("k", "test-model", client=SimpleNamespace(models=fake))
    hits = [hit(1, "https://sharpbuild.io/services/ecommerce"),
            hit(2, "https://sharpbuild.io/portfolio/hacksprint", page_type="portfolio", content="Free, Pro, Enterprise tiers"),
            hit(3, "https://sharpbuild.io/contact", page_type="facts", content="Pricing not published")]
    assert answer("Do you build Shopify stores?", hits) == "Yes, we build Shopify stores. [1]"
    sent = fake.calls[0]
    assert sent["model"] == "test-model"
    assert "[1] Type: SharpBuild website page" in sent["contents"]
    assert "[2] Type: Client case study" in sent["contents"]      # the HackSprint pricing trap is labelled
    assert "[3] Type: Verified FAQ" in sent["contents"]
    assert "Do you build Shopify stores?" in sent["contents"]
    assert "Client case study" in sent["config"].system_instruction


def test_answerer_fallback_without_context_and_error_on_empty_response():
    boom = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k: pytest.fail("must not call Gemini")))
    assert make_gemini_answerer("k", "m", client=boom)("q", []) == NO_ANSWER
    empty = SimpleNamespace(models=FakeModels(" "))
    with pytest.raises(RuntimeError, match="empty chat response"):
        make_gemini_answerer("k", "m", client=empty)("q", [hit()])


# ---------- citations -> sources ----------
def test_attach_sources_removes_markers_and_returns_cited_pages_once_in_citation_order():
    hits = [hit(1, "https://sharpbuild.io/a"), hit(2, "https://sharpbuild.io/b"),
            hit(3, "https://sharpbuild.io/a"), hit(4, "https://sharpbuild.io/c")]
    text, sources = attach_sources("We do X [3]. We also do Y [2, 1]. Ignore [9].", hits)
    assert text == "We do X. We also do Y. Ignore."                   # no [n] left in the visible text
    assert [s.url for s in sources] == ["https://sharpbuild.io/a", "https://sharpbuild.io/b"]   # [3] and [1] are one page; [9] is invalid
    assert attach_sources("No citations here.", hits) == ("No citations here.", [])


# ---------- pipeline ----------
def run(hits, answerer, **kw):
    chat_service.retrieve = lambda *a, **k: hits
    return answer_question(None, "question", lambda t: [[0.0]], answerer,
                           min_similarity=kw.get("min_similarity", 0.58), k=4)


@pytest.fixture(autouse=True)
def restore_retrieve():
    original = chat_service.retrieve
    yield
    chat_service.retrieve = original


def test_weak_matches_never_reach_the_llm():
    def answerer(q, hits):
        pytest.fail("LLM must not be called below the threshold")
    r = run([hit(1, sim=0.54), hit(2, sim=0.50)], answerer)
    assert r.fallback and r.answer == NO_ANSWER and r.sources == []
    assert run([], answerer).fallback


def test_only_relevant_hits_are_passed_as_evidence():
    seen = []
    def answerer(q, hits):
        seen.extend(hits)
        return "Yes [1]"
    r = run([hit(1, sim=0.70), hit(2, sim=0.60), hit(3, sim=0.50)], answerer)
    assert [h.chunk_id for h in seen] == ["chunk-1", "chunk-2"]
    assert not r.fallback and [s.url for s in r.sources] == ["https://sharpbuild.io/p1"]


def test_model_saying_no_answer_becomes_a_fallback():
    r = run([hit()], lambda q, h: NO_ANSWER_MARKER)
    assert r.fallback and r.answer == NO_ANSWER and r.sources == []


def test_llm_failure_degrades_gracefully_and_is_logged(caplog):
    def answerer(q, hits):
        raise RuntimeError("503 from Gemini")
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        r = run([hit()], answerer)
    assert r.fallback and r.answer == UNAVAILABLE
    assert "chat pipeline failed" in caplog.text and "outcome=error" in caplog.text


def test_logs_metadata_but_never_the_question_text(caplog):
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        chat_service.retrieve = lambda *a, **k: [hit()]
        answer_question(None, "my secret phone is 555-0100", lambda t: [[0.0]], lambda q, h: "Yes [1]",
                        min_similarity=0.58, k=4)
    assert "outcome=answered" in caplog.text and "555-0100" not in caplog.text


# ---------- HTTP route ----------
CFG = SimpleNamespace(gemini_api_key="k", embedding_model="e", generation_model="g",
                      min_similarity=0.58, retrieval_k=4,
                      rate_limit_per_minute=100, global_rate_limit_per_minute=100)


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: CFG
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[chat_route.get_embed_query] = lambda: (lambda texts: [[0.0]])
    app.dependency_overrides[chat_route.get_answerer] = lambda: (lambda q, hits: "Yes, we do. [1]")
    app.dependency_overrides[rate_limit] = lambda: None
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_route_returns_answer_sources_and_fallback_flag(client):
    chat_service.retrieve = lambda *a, **k: [hit(1, "https://sharpbuild.io/services/ecommerce")]
    r = client.post("/chat", json={"message": "Shopify?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Yes, we do." and body["fallback"] is False
    assert body["sources"] == [{"url": "https://sharpbuild.io/services/ecommerce", "title": "Title 1", "section": "Section 1"}]


@pytest.mark.parametrize("payload", [{"message": ""}, {"message": "   "}, {"message": "x" * 501}, {}])
def test_route_rejects_bad_input_with_422(client, payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_route_reports_unconfigured_ai_service():
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(gemini_api_key="")
    app.dependency_overrides[rate_limit] = lambda: None
    try:
        assert TestClient(app).post("/chat", json={"message": "hello"}).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_route_rate_limits_with_retry_after():
    cfg = SimpleNamespace(**{**CFG.__dict__, "rate_limit_per_minute": 2, "global_rate_limit_per_minute": 999})
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[chat_route.get_embed_query] = lambda: (lambda texts: [[0.0]])
    app.dependency_overrides[chat_route.get_answerer] = lambda: (lambda q, hits: "ok")
    chat_service.retrieve = lambda *a, **k: []
    try:
        c = TestClient(app)
        codes = [c.post("/chat", json={"message": "hi"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        blocked = c.post("/chat", json={"message": "hi"})
        assert int(blocked.headers["Retry-After"]) > 0 and "hello@sharpbuild.io" in blocked.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ---------- backup-model chain ----------
class ApiError(Exception):
    def __init__(self, code):
        self.code = code


class SlowError(Exception):
    pass


SlowError.__name__ = "ReadTimeout"


class ScriptedModels:
    """Each model name maps to a reply text or an exception to raise."""
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    def generate_content(self, **kw):
        self.calls.append(kw["model"])
        outcome = self.outcomes[kw["model"]]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def chain(outcomes, fallbacks):
    models = ScriptedModels(outcomes)
    answer = make_gemini_answerer("k", "main", client=SimpleNamespace(models=models), fallbacks=fallbacks)
    return answer, models


@pytest.mark.parametrize("failure", [ApiError(503), ApiError(404), ApiError(429), SlowError()])
def test_overloaded_retired_limited_or_slow_model_falls_back_to_next(failure):
    answer, models = chain({"main": failure, "backup": "From backup [1]"}, ["backup"])
    assert answer("q", [hit()]) == "From backup [1]"
    assert models.calls == ["main", "backup"]


def test_bad_request_or_bad_key_does_not_try_other_models():
    answer, models = chain({"main": ApiError(400), "backup": "never"}, ["backup"])
    with pytest.raises(ApiError):
        answer("q", [hit()])
    assert models.calls == ["main"]


def test_error_is_raised_when_every_model_fails_and_main_success_skips_backups():
    answer, models = chain({"main": ApiError(503), "backup": ApiError(503)}, ["backup"])
    with pytest.raises(ApiError):
        answer("q", [hit()])
    assert models.calls == ["main", "backup"]
    answer, models = chain({"main": "ok [1]", "backup": "never"}, ["backup"])
    assert answer("q", [hit()]) == "ok [1]" and models.calls == ["main"]


def test_settings_parse_fallback_list():
    from app.core.config import Settings
    s = Settings(database_url="x", generation_fallback_models=" a , b ,, ")
    assert s.fallback_models == ["a", "b"]
    assert Settings(database_url="x").generation_model == "gemini-3.5-flash-lite"
