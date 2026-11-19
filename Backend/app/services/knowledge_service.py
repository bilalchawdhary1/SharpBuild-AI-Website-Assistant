"""Retrieval: find the stored chunks most relevant to a question."""
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.services.embeddings import EmbedFn

logger = logging.getLogger("sharpbuild.retrieval")


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    url: str
    title: str
    section: str
    page_type: str         # services, portfolio (client case study), facts, ...
    content: str
    similarity: float      # Hybrid rank score: 0.85 cosine + 0.15 lexical coverage.


STOP_WORDS = {
    "a", "an", "and", "are", "at", "be", "build", "can", "do", "for",
    "how", "i", "is", "it", "of", "on", "our", "the", "to", "we", "what",
    "when", "where", "which", "with", "you", "your",
}


def lexical_coverage(question: str, text: str) -> float:
    """Fraction of meaningful question terms found in chunk text."""
    terms = {
        term
        for term in re.findall(r"[a-z0-9]+", question.casefold())
        if len(term) > 2 and term not in STOP_WORDS
    }
    if not terms:
        return 0.0
    haystack = text.casefold()
    matched = sum(term in haystack for term in terms)
    return matched / len(terms)


def hybrid_score(cosine_similarity: float, lexical_similarity: float) -> float:
    return (0.85 * cosine_similarity) + (0.15 * lexical_similarity)


FACT_TOPIC_ALIASES = {
    "pricing and quotes": {"cost", "costs", "price", "prices", "pricing", "quote", "quotes", "budget", "rate", "rates", "hourly"},
    "project timelines": {"long", "timeline", "timelines", "duration", "delivery", "deadline", "deadlines", "weeks", "months"},
    "company size and history": {"team", "developers", "employees", "founded", "company", "size", "history", "staff"},
    "location and office": {"where", "located", "location", "office", "offices", "based", "headquarters", "country"},
    "contact details": {"contact", "email", "phone", "whatsapp", "call", "reach"},
    "technologies": {"technology", "technologies", "tech", "stack", "tools", "language", "languages", "framework"},
    "privacy policy and legal pages": {"privacy", "policy", "terms", "cookies", "legal"},
    "services overview": {"services", "service", "offer", "offers", "provide", "provides"},
}


def fact_topic_matches(question: str, section: str) -> bool:
    question_terms = set(re.findall(r"[a-z0-9]+", question.casefold()))
    aliases = FACT_TOPIC_ALIASES.get(section.casefold(), set())
    return bool(question_terms & aliases)


def rerank_hits(question: str, hits: list[Hit]) -> list[Hit]:
    """Apply a small, dependency-free rerank for authoritative fact chunks."""
    reranked = []
    for hit in hits:
        bonus = 0.0
        if hit.page_type == "facts":
            if fact_topic_matches(question, hit.section):
                bonus = 0.12
        reranked.append(
            Hit(hit.chunk_id, hit.url, hit.title, hit.section, hit.page_type,
                hit.content, min(1.0, hit.similarity + bonus))
        )
    reranked.sort(key=lambda hit: hit.similarity, reverse=True)
    return reranked


def retrieve(db: Session, question: str, embed_query: EmbedFn, k: int = 4) -> list[Hit]:
    """embed_query must be a RETRIEVAL_QUERY embedder (see app.services.embeddings)."""
    started = time.perf_counter()
    vector = embed_query([question])[0]
    embedded = time.perf_counter()
    distance = Chunk.embedding.cosine_distance(vector)
    # Select columns, not the whole row: skips pulling 1536 floats per hit.
    stmt = (select(Chunk.chunk_id, Chunk.url, Chunk.title, Chunk.section, Chunk.page_type, Chunk.content,
                   distance.label("dist"))
            .order_by(distance).limit(max(k * 5, 20)))
    rows = list(db.execute(stmt))
    done = time.perf_counter()
    # Timing split: tells a slow embedding API apart from a slow database (e.g. a sleeping Neon compute).
    logger.info("retrieve embed_ms=%d db_ms=%d hits=%d", (embedded - started) * 1000, (done - embedded) * 1000, len(rows))
    ranked = []
    for r in rows:
        cosine = 1.0 - r.dist
        searchable = f"{r.title} {r.section} {r.content}"
        lexical = lexical_coverage(question, searchable)
        ranked.append(Hit(r.chunk_id, r.url, r.title, r.section, r.page_type,
                          r.content, hybrid_score(cosine, lexical)))
    reranked = rerank_hits(question, ranked)
    return reranked[:k]
