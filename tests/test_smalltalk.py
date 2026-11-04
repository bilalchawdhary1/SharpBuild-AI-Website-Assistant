import pytest

from app.services import chat_service
from app.services.chat_service import answer_question
from app.services.smalltalk import smalltalk_reply


@pytest.mark.parametrize("message", [
    "hi", "Hello!", "hey there", "Good morning", "HELLO TEAM.", "hi sharpbuild",
    "thanks", "Thank you so much!", "thx", "cheers!",
    "bye", "Goodbye!", "that\u2019s all", "see you",
    "my name is bilal", "My name is Sarah Jane", "call me Bo",
    "tell me my name", "what's my name?", "What\u2019s my name", "do you remember me", "who am I",
])
def test_smalltalk_is_recognised(message):
    assert smalltalk_reply(message)


@pytest.mark.parametrize("message", [
    "Hello, do you build Shopify stores?",
    "Hi, how much does a website cost?",
    "My name is Bilal and I need a Shopify store built",
    "thanks, but what is your process?",
    "Do you build Shopify stores?",
    "What services do you offer?",
    "bye bye bye what do you do",
    "",
])
def test_real_questions_are_never_hijacked(message):
    assert smalltalk_reply(message) is None


def test_personal_replies_do_not_pretend_to_remember_or_store_anything():
    assert "can't recall your name" in smalltalk_reply("what is my name")
    assert "don't store personal details" in smalltalk_reply("my name is Bilal")
    assert "Bilal" not in smalltalk_reply("my name is Bilal")      # never echoes the name back


def test_pipeline_answers_smalltalk_without_retrieval_or_llm():
    def boom(*a, **k):
        raise AssertionError("must not retrieve or call the LLM for small talk")
    original = chat_service.retrieve
    chat_service.retrieve = boom
    try:
        r = answer_question(None, "my name is bilal", boom, boom, min_similarity=0.58, k=4)
    finally:
        chat_service.retrieve = original
    assert r.sources == [] and r.fallback is False and "Nice to meet you" in r.answer
