"""Routing of intents inside chat_service.prepare (pytest; needs the project's dependencies)."""
from app.services import chat_service
from app.services.ai_service import HANDOFF
from app.services.chat_service import Generate, Ready, done_event, prepare
from app.services.knowledge_service import Hit


def _no_embed(_text):
    raise AssertionError("handoff must not call the embedder")


def test_handoff_skips_retrieval_and_offers_contact(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("handoff must not retrieve")
    monkeypatch.setattr(chat_service, "retrieve", boom)

    prepared = prepare(None, "I want to talk to a human", _no_embed, min_similarity=0.58, k=4)

    assert isinstance(prepared, Ready)
    assert prepared.response.answer == HANDOFF
    assert prepared.response.fallback is True            # widget shows contact options
    assert prepared.response.intent == "human_handoff"
    assert done_event(prepared.response)["intent"] == "human_handoff"


def test_pricing_still_uses_rag_and_carries_intent(monkeypatch):
    hit = Hit(chunk_id="c1", url="https://sharpbuild.io/pricing", title="Pricing", section="",
              page_type="facts", content="Pricing is project based.", similarity=0.9)
    monkeypatch.setattr(chat_service, "retrieve", lambda *a, **k: [hit])

    prepared = prepare(None, "How much does an MVP cost?", lambda t: [0.0], min_similarity=0.58, k=4)

    assert isinstance(prepared, Generate)
    assert prepared.intent == "pricing"
