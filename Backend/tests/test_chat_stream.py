import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import chat as chat_route
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.main import app
from app.services import chat_service
from app.services.ai_service import NO_ANSWER, UNAVAILABLE, make_gemini_streamer
from app.services.chat_service import Generate, stream_answer
from app.services.knowledge_service import Hit


def hit(n=1, sim=0.9):
    return Hit(f"c{n}", f"https://sharpbuild.io/p{n}", f"Title {n}", "S", "services", "We build Shopify stores.", sim)


class ApiError(Exception):
    def __init__(self, code):
        self.code = code


# ---------- Gemini streamer ----------
class StreamModels:
    """Each model name maps to: an exception to raise on call, or a list of chunk texts (an Exception item raises mid-stream)."""
    def __init__(self, scripts):
        self.scripts, self.calls = scripts, []

    def generate_content_stream(self, *, model, contents, config):
        self.calls.append(model)
        script = self.scripts[model]
        if isinstance(script, Exception):
            raise script

        def chunks():
            for item in script:
                if isinstance(item, Exception):
                    raise item
                yield SimpleNamespace(text=item)
        return chunks()


def streamer(scripts, fallbacks=("backup",)):
    models = StreamModels(scripts)
    return make_gemini_streamer("k", "main", client=SimpleNamespace(models=models), fallbacks=fallbacks), models


def test_streamer_yields_text_pieces_in_order_and_skips_empty_chunks():
    s, _ = streamer({"main": [None, "", "Hello", None, " world", ""]})
    assert list(s("q", [hit()])) == ["Hello", " world"]


@pytest.mark.parametrize("failure", [ApiError(503), ApiError(404), ApiError(429)])
def test_streamer_uses_the_backup_model_when_the_main_one_fails_before_any_text(failure):
    s, models = streamer({"main": failure, "backup": ["From ", "backup"]})
    assert list(s("q", [hit()])) == ["From ", "backup"]
    assert models.calls == ["main", "backup"]


def test_streamer_uses_the_backup_when_the_error_arrives_while_waiting_for_the_first_text():
    s, models = streamer({"main": [ApiError(503)], "backup": ["ok"]})
    assert list(s("q", [hit()])) == ["ok"] and models.calls == ["main", "backup"]


def test_streamer_never_switches_models_after_text_was_already_shown():
    s, models = streamer({"main": ["Part one ", ApiError(503)], "backup": ["never"]})
    out = []
    with pytest.raises(ApiError):
        for piece in s("q", [hit()]):
            out.append(piece)
    assert out == ["Part one "] and models.calls == ["main"]


def test_streamer_fails_fast_on_bad_requests_and_on_empty_answers():
    s, models = streamer({"main": ApiError(400), "backup": ["never"]})
    with pytest.raises(ApiError):
        list(s("q", [hit()]))
    assert models.calls == ["main"]
    s, _ = streamer({"main": [None, ""], "backup": ["never"]})
    with pytest.raises(RuntimeError, match="empty"):
        list(s("q", [hit()]))


# ---------- stream_answer: events + logging ----------
def generate(hits=None):
    return Generate("Do you build apps?", hits or [hit(1), hit(2)], top=0.9, retrieve_ms=120.0, started=0.0)


def test_stream_answer_emits_clean_events_and_logs_first_token_time(caplog):
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        events = list(stream_answer(generate(), lambda q, h: iter(["Yes, ", "we do [2]", "."])))
    assert [e["type"] for e in events] == ["delta", "delta", "delta", "done"]
    assert events[-1]["answer"] == "Yes, we do." and events[-1]["sources"][0]["url"] == "https://sharpbuild.io/p2"
    assert "outcome=answered" in caplog.text and "first_token_ms=" in caplog.text


def test_stream_answer_turns_failures_into_an_error_event_and_never_raises(caplog):
    def broken(q, h):
        yield "Part"
        raise RuntimeError("boom")
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        events = list(stream_answer(generate(), broken))
    assert events[0] == {"type": "delta", "text": "Part"}
    assert events[-1] == {"type": "error", "message": UNAVAILABLE}
    assert "chat stream failed" in caplog.text and "outcome=error" in caplog.text


def test_stream_answer_logs_when_the_visitor_goes_away(caplog):
    def endless(q, h):
        while True:
            yield "word "
    gen = stream_answer(generate(), endless)
    next(gen)
    with caplog.at_level(logging.INFO, logger="sharpbuild.chat"):
        gen.close()
    assert "outcome=client_closed" in caplog.text


def test_model_saying_no_answer_becomes_a_fallback_done_event():
    events = list(stream_answer(generate(), lambda q, h: iter(["[[NO_", "ANSWER]]"])))
    assert events == [{"type": "done", "answer": NO_ANSWER, "fallback": True, "sources": []}]


# ---------- HTTP endpoint ----------
CFG = SimpleNamespace(gemini_api_key="k", embedding_model="e", generation_model="g", min_similarity=0.58,
                      retrieval_k=4, rate_limit_per_minute=100, global_rate_limit_per_minute=100)


def frames(response):
    return [json.loads(f[len("data: "):]) for f in response.text.split("\n\n") if f.startswith("data: ")]


@pytest.fixture
def api():
    state = {"stream": lambda q, h: iter(["Yes, we do [1]."]), "hits": [hit(1)]}
    app.dependency_overrides[get_settings] = lambda: CFG
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[chat_route.get_embed_query] = lambda: (lambda t: [[0.0]])
    app.dependency_overrides[chat_route.get_streamer] = lambda: (lambda q, h: state["stream"](q, h))
    app.dependency_overrides[rate_limit] = lambda: None
    original = chat_service.retrieve
    chat_service.retrieve = lambda *a, **k: state["hits"]
    yield TestClient(app, raise_server_exceptions=False), state
    chat_service.retrieve = original
    app.dependency_overrides.clear()


def test_endpoint_streams_start_deltas_and_done_with_the_right_headers(api):
    client, _ = api
    r = client.post("/chat/stream", json={"message": "Do you build Shopify stores?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "no-cache" in r.headers["cache-control"] and r.headers["x-accel-buffering"] == "no"
    events = frames(r)
    assert [e["type"] for e in events] == ["start", "delta", "done"]
    assert events[-1]["answer"] == "Yes, we do." and events[-1]["sources"][0]["title"] == "Title 1"


def test_small_talk_and_weak_matches_answer_without_calling_the_model(api):
    client, state = api
    state["stream"] = lambda q, h: pytest.fail("the model must not be called")
    smalltalk = frames(client.post("/chat/stream", json={"message": "hello"}))
    assert [e["type"] for e in smalltalk] == ["start", "done"] and not smalltalk[-1]["fallback"]
    state["hits"] = [hit(1, sim=0.3)]
    weak = frames(client.post("/chat/stream", json={"message": "weather in Paris?"}))
    assert weak[-1] == {"type": "done", "answer": NO_ANSWER, "fallback": True, "sources": []}


def test_a_failure_halfway_ends_with_an_error_event_after_the_partial_text(api):
    client, state = api

    def half(q, h):
        yield "Partial answer "
        raise RuntimeError("model died")
    state["stream"] = half
    events = frames(client.post("/chat/stream", json={"message": "Tell me about apps"}))
    assert [e["type"] for e in events] == ["start", "delta", "error"]


def test_a_retrieval_failure_is_reported_as_unavailable(api):
    client, _ = api

    def broken(*a, **k):
        raise RuntimeError("database down")
    chat_service.retrieve = broken
    events = frames(client.post("/chat/stream", json={"message": "Tell me about apps"}))
    assert events[-1]["answer"] == UNAVAILABLE and events[-1]["fallback"] is True


@pytest.mark.parametrize("payload", [{"message": ""}, {"message": "x" * 501}, {}])
def test_endpoint_validates_input_like_the_plain_endpoint(api, payload):
    client, _ = api
    assert client.post("/chat/stream", json=payload).status_code == 422
