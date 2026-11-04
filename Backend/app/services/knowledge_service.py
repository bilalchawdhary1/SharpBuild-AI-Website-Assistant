"""Retrieval: find the stored chunks most relevant to a question."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.services.embeddings import EmbedFn


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    url: str
    title: str
    section: str
    page_type: str         # services, portfolio (client case study), facts, ...
    content: str
    similarity: float      # cosine similarity: 1.0 = identical direction. Model-specific scale!


def retrieve(db: Session, question: str, embed_query: EmbedFn, k: int = 4) -> list[Hit]:
    """embed_query must be a RETRIEVAL_QUERY embedder (see app.services.embeddings)."""
    vector = embed_query([question])[0]
    distance = Chunk.embedding.cosine_distance(vector)
    # Select columns, not the whole row: skips pulling 1536 floats per hit.
    stmt = (select(Chunk.chunk_id, Chunk.url, Chunk.title, Chunk.section, Chunk.page_type, Chunk.content,
                distance.label("dist"))
            .order_by(distance).limit(k))
    return [Hit(r.chunk_id, r.url, r.title, r.section, r.page_type, r.content, 1.0 - r.dist)
            for r in db.execute(stmt)]