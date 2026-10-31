from types import SimpleNamespace

import pytest

from app.api.routes import chat as chat_route
from app.schemas.chat import ChatRequest
from app.services.ai_service import NO_ANSWER, make_gemini_answerer
from app.services.knowledge_service import Hit


def test_chat_request_strips_message_and_rejects_blank():
    assert ChatRequest(message="  hello  ").message == "hello"
    with pytest.raises(ValueError, match="must not be blank"):
        ChatRequest(message="   ")


def test_gemini_answerer_uses_retrieved_context_and_returns_text():
    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="Yes, we build Shopify stores. [1]")

    hit = Hit("chunk-1", "https://sharpbuild.io/services/ecommerce",
              "E-commerce", "Shopify", "We build Shopify stores.", 0.9)
    answer = make_gemini_answerer(
        "test-key", "test-model", client=SimpleNamespace(models=FakeModels()))

    assert answer("Do you build Shopify stores?", [hit]) == "Yes, we build Shopify stores. [1]"
    assert calls[0]["model"] == "test-model"
    assert "We build Shopify stores." in calls[0]["contents"]
    assert "[1] URL: https://sharpbuild.io/services/ecommerce" in calls[0]["contents"]


def test_gemini_answerer_returns_fallback_without_context():
    class FakeModels:
        def generate_content(self, **kwargs):
            pytest.fail("should not call Gemini without retrieved context")

    answer = make_gemini_answerer(
        "test-key", "test-model", client=SimpleNamespace(models=FakeModels()))
    assert answer("Unknown question", []) == NO_ANSWER


def test_gemini_answerer_rejects_empty_model_response():
    class FakeModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=" ")

    answer = make_gemini_answerer(
        "test-key", "test-model", client=SimpleNamespace(models=FakeModels()))
    with pytest.raises(RuntimeError, match="empty chat response"):
        answer("Question", [Hit("id", "https://sharpbuild.io/", "Home", "", "Text", 0.8)])


def test_chat_route_retrieves_context_and_returns_source_links(monkeypatch):
    hit = Hit("chunk-1", "https://sharpbuild.io/services/ecommerce",
              "E-commerce", "Shopify", "We build Shopify stores.", 0.9)
    monkeypatch.setattr(chat_route, "get_settings", lambda: SimpleNamespace(
        gemini_api_key="test-key",
        embedding_model="embedding-model",
        generation_model="generation-model",
    ))
    monkeypatch.setattr(chat_route, "make_gemini_embedder", lambda *args: lambda texts: [[0.0]])
    monkeypatch.setattr(chat_route, "retrieve", lambda *args: [hit])
    monkeypatch.setattr(chat_route, "make_gemini_answerer",
                        lambda *args: lambda question, hits: "Yes. [1]")

    response = chat_route.chat(ChatRequest(message="Shopify?"), db=object())

    assert response.answer == "Yes. [1]"
    assert response.sources[0].url == hit.url
    assert response.sources[0].section == "Shopify"


def test_chat_route_reports_unconfigured_ai_service(monkeypatch):
    monkeypatch.setattr(chat_route, "get_settings", lambda: SimpleNamespace(gemini_api_key=""))
    with pytest.raises(chat_route.HTTPException) as error:
        chat_route.chat(ChatRequest(message="hello"), db=object())
    assert error.value.status_code == 503
