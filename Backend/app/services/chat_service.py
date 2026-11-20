"""The chat pipeline: retrieve -> threshold -> answer -> sources. No web code here.

Two ways to answer, sharing the same first steps (prepare):
  answer_question  returns the whole answer at once (POST /chat)
  stream_answer    yields events while the answer is being written (POST /chat/stream)
"""
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Iterator

from sqlalchemy.orm import Session

from app.schemas.chat import ChatResponse, ChatSource, ChatTurn, LeadInfo
from app.services.ai_service import HANDOFF, NO_ANSWER, NO_ANSWER_MARKER, UNAVAILABLE, AnswerFn, StreamFn
from app.services.embeddings import EmbedFn
from app.services.knowledge_service import Hit, retrieve
from app.services.intent import detect_intent
from app.services.lead_scoring import assess_lead
from app.services.smalltalk import smalltalk_reply
from app.services.streaming import (
    CitationStripper,
    is_clarifying_question,
    sources_from_citations,
    stream_events,
)

logger = logging.getLogger("sharpbuild.chat")


@dataclass(frozen=True)
class Ready:
    """Nothing to generate: the answer is already known (small talk, no match, or an error)."""
    response: ChatResponse


@dataclass
class Generate:
    """Relevant sources were found: the language model should write an answer from them."""
    question: str
    hits: list[Hit]
    top: float
    retrieve_ms: float
    started: float
    history: list[ChatTurn] = field(default_factory=list)
    intent: str = "information"
    lead: LeadInfo | None = None


def attach_sources(answer: str, hits: list[Hit]) -> tuple[str, list[ChatSource]]:
    """Removes the [n] citation markers from the text and returns the pages they pointed to
    (one per page, in the order first cited)."""
    stripper = CitationStripper()
    text = (stripper.feed(answer) + stripper.finish()).strip()
    return text, sources_from_citations(stripper.cited, hits)


def _fallback(message: str, intent: str | None = None, lead: LeadInfo | None = None) -> ChatResponse:
    return ChatResponse(answer=message, sources=[], fallback=True, intent=intent, lead=lead)


def _lead_info(question: str, history: list[ChatTurn], intent: str) -> LeadInfo | None:
    """Lead qualification is a bonus: if it ever fails, the chat answer must still go out."""
    try:
        lead = assess_lead(question, history, intent)
        if lead is None:
            return None
        logger.info("chat lead score=%s next_field=%s", lead.score, lead.next_field)   # no personal values
        return LeadInfo(**asdict(lead))
    except Exception:
        logger.exception("lead scoring failed")
        return None


def _log(outcome: str, top: float, question: str, retrieve_ms: float, answer_ms: float, started: float,
         first_token_ms: float | None = None) -> None:
    # Metadata only: visitors may type personal details, so question text is never logged.
    extra = f" first_token_ms={first_token_ms:.0f}" if first_token_ms is not None else ""
    logger.info("chat outcome=%s top_similarity=%.3f question_chars=%d retrieve_ms=%d answer_ms=%d ms=%d%s",
                outcome, top, len(question), retrieve_ms, answer_ms, (time.perf_counter() - started) * 1000, extra)


def prepare(db: Session, question: str, embed_query: EmbedFn, *, min_similarity: float, k: int,
            history: list[ChatTurn] | None = None) -> Ready | Generate:
    history = history or []
    intent = detect_intent(question)
    logger.info("chat intent=%s question_chars=%d", intent, len(question))
    canned = smalltalk_reply(question)
    if canned:                               # greetings/thanks/personal chatter: no embedding, no LLM
        logger.info("chat outcome=smalltalk question_chars=%d", len(question))
        return Ready(ChatResponse(answer=canned, sources=[], fallback=False, intent=intent))
    if intent == "human_handoff":            # the visitor asked for a person: no retrieval, no LLM
        logger.info("chat outcome=human_handoff question_chars=%d", len(question))
        return Ready(_fallback(HANDOFF, intent))     # fallback=True makes the widget offer contact options

    lead = _lead_info(question, history, intent)

    started = time.perf_counter()
    try:
        hits = retrieve(db, question, embed_query, k=k)
    except Exception:
        logger.exception("chat pipeline failed")
        _log("error", 0.0, question, 0.0, 0.0, started)
        return Ready(_fallback(UNAVAILABLE, intent, lead))
    retrieve_ms = (time.perf_counter() - started) * 1000
    top = hits[0].similarity if hits else 0.0
    relevant = [h for h in hits if h.similarity >= min_similarity]       # weak matches never reach the LLM
    if not relevant:
        _log("below_threshold", top, question, retrieve_ms, 0.0, started)
        return Ready(_fallback(NO_ANSWER, intent, lead))
    return Generate(question, relevant, top, retrieve_ms, started, history, intent, lead)


def answer_question(db: Session, question: str, embed_query: EmbedFn, answerer: AnswerFn,
                    *, min_similarity: float, k: int, history: list[ChatTurn] | None = None) -> ChatResponse:
    prepared = prepare(db, question, embed_query, min_similarity=min_similarity, k=k, history=history)
    if isinstance(prepared, Ready):
        return prepared.response

    outcome = "error"
    answer_started = time.perf_counter()
    answer_ms = 0.0
    try:
        raw = answerer(prepared.question, prepared.hits, prepared.history)
        answer_ms = (time.perf_counter() - answer_started) * 1000
        if NO_ANSWER_MARKER in raw:
            outcome = "model_no_answer"
            return _fallback(NO_ANSWER, prepared.intent, prepared.lead)
        text, sources = attach_sources(raw, prepared.hits)
        if text.strip() and not sources and not is_clarifying_question(text):
            outcome = "model_no_answer"
            return _fallback(NO_ANSWER, prepared.intent, prepared.lead)
        outcome = "answered"
        return ChatResponse(answer=text, sources=sources, fallback=False, intent=prepared.intent,
                            lead=prepared.lead)
    except Exception:
        answer_ms = answer_ms or (time.perf_counter() - answer_started) * 1000
        logger.exception("chat pipeline failed")
        return _fallback(UNAVAILABLE, prepared.intent, prepared.lead)
    finally:
        _log(outcome, prepared.top, prepared.question, prepared.retrieve_ms, answer_ms, prepared.started)


def done_event(response: ChatResponse) -> dict:
    event = {"type": "done", "answer": response.answer, "fallback": response.fallback,
             "sources": [s.model_dump() for s in response.sources], "intent": response.intent}
    if response.lead is not None:            # only sales conversations carry a lead block
        event["lead"] = response.lead.model_dump()
    return event


def stream_answer(prepared: Generate, streamer: StreamFn) -> Iterator[dict]:
    """Events for the browser: delta* then done, or error. Never raises."""
    outcome = "error"
    answer_started = time.perf_counter()
    first_token_ms: float | None = None
    try:
        history = prepared.history or []
        for event in stream_events(streamer(prepared.question, prepared.hits, history), prepared.hits):
            if event["type"] == "no_answer":
                outcome = "model_no_answer"
                yield done_event(_fallback(NO_ANSWER, prepared.intent, prepared.lead))
                return
            if event["type"] == "delta" and first_token_ms is None:
                first_token_ms = (time.perf_counter() - answer_started) * 1000
            if event["type"] == "done":
                outcome = "answered"
                event["intent"] = prepared.intent
                if prepared.lead is not None:
                    event["lead"] = prepared.lead.model_dump()
            yield event
    except GeneratorExit:                    # the visitor closed the page or pressed Stop
        outcome = "client_closed"
        raise
    except Exception:
        logger.exception("chat stream failed")
        yield {"type": "error", "message": UNAVAILABLE}
    finally:
        _log(outcome, prepared.top, prepared.question, prepared.retrieve_ms,
             (time.perf_counter() - answer_started) * 1000, prepared.started, first_token_ms)
