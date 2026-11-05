"""The chat pipeline: retrieve -> threshold -> answer -> sources. No web code here."""
import logging
import re
import time

from sqlalchemy.orm import Session

from app.schemas.chat import ChatResponse, ChatSource
from app.services.ai_service import NO_ANSWER, NO_ANSWER_MARKER, UNAVAILABLE, AnswerFn
from app.services.embeddings import EmbedFn
from app.services.knowledge_service import Hit, retrieve
from app.services.smalltalk import smalltalk_reply

logger = logging.getLogger("sharpbuild.chat")
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _plain_text(text: str) -> str:
    """The widget shows plain text, so markdown the model sneaks in would appear as stray symbols."""
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)                    # "## Heading" -> "Heading"
    text = re.sub(r"(?m)^(\s*)[*\-]\s+", "\\1\u2022 ", text)            # "* item" / "- item" -> "• item"
    return re.sub(r"(\[\d{1,2}\])\s*,\s*(?=\[\d{1,2}\])", r"\1", text)   # "[1], [2]" -> "[1][2]"


def attach_sources(answer: str, hits: list[Hit]) -> tuple[str, list[ChatSource]]:
    """Keep only sources the answer actually cites, one per page, and renumber the
    markers so [1], [2]... match the returned source list. Invalid markers are dropped."""
    order: list[str] = []
    found: dict[str, Hit] = {}

    def renumber(match: re.Match) -> str:
        tags: list[str] = []
        for n in (int(x) for x in re.split(r"\s*,\s*", match.group(1))):
            if 1 <= n <= len(hits):
                hit = hits[n - 1]
                if hit.url not in found:
                    order.append(hit.url)
                    found[hit.url] = hit
                tag = f"[{order.index(hit.url) + 1}]"
                if tag not in tags:
                    tags.append(tag)
        return "".join(tags)

    text = _plain_text(CITATION.sub(renumber, answer))
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text).strip()
    sources = [ChatSource(url=u, title=found[u].title, section=found[u].section) for u in order]
    return text, sources


def _fallback(message: str) -> ChatResponse:
    return ChatResponse(answer=message, sources=[], fallback=True)


def answer_question(db: Session, question: str, embed_query: EmbedFn, answerer: AnswerFn,
                    *, min_similarity: float, k: int) -> ChatResponse:
    canned = smalltalk_reply(question)
    if canned:                               # greetings/thanks/personal chatter: no embedding, no LLM
        logger.info("chat outcome=smalltalk question_chars=%d", len(question))
        return ChatResponse(answer=canned, sources=[], fallback=False)

    started = time.perf_counter()
    outcome, top = "error", 0.0
    retrieve_ms = answer_ms = 0.0
    try:
        hits = retrieve(db, question, embed_query, k=k)
        retrieve_ms = (time.perf_counter() - started) * 1000
        top = hits[0].similarity if hits else 0.0
        relevant = [h for h in hits if h.similarity >= min_similarity]   # weak matches never reach the LLM
        if not relevant:
            outcome = "below_threshold"
            return _fallback(NO_ANSWER)
        answer_started = time.perf_counter()
        try:
            raw = answerer(question, relevant)
        finally:
            answer_ms = (time.perf_counter() - answer_started) * 1000
        if NO_ANSWER_MARKER in raw:
            outcome = "model_no_answer"
            return _fallback(NO_ANSWER)
        text, sources = attach_sources(raw, relevant)
        outcome = "answered"
        return ChatResponse(answer=text, sources=sources, fallback=False)
    except Exception:
        logger.exception("chat pipeline failed")
        return _fallback(UNAVAILABLE)
    finally:
        # Metadata only: visitors may type personal details, so question text is not logged.
        logger.info("chat outcome=%s top_similarity=%.3f question_chars=%d retrieve_ms=%d answer_ms=%d ms=%d",
                    outcome, top, len(question), retrieve_ms, answer_ms, (time.perf_counter() - started) * 1000)
