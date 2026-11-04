"""Sanity check: embed a question and show the 3 closest chunks.

Usage:  python -m scripts.try_search "Do you build Shopify stores?"
"""
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.chunk import Chunk
from app.services.embeddings import make_gemini_embedder, with_retries


def main(question: str) -> None:
    settings = get_settings()
    embed = with_retries(make_gemini_embedder(
        settings.gemini_api_key, settings.embedding_model, "RETRIEVAL_QUERY"))
    vector = embed([question])[0]

    distance = Chunk.embedding.cosine_distance(vector)        # 0 = identical, 2 = opposite
    stmt = (select(Chunk.url, Chunk.section, Chunk.content, distance.label("dist"))
            .order_by(distance).limit(3))
    with SessionLocal() as db:
        for row in db.execute(stmt):
            print(f"\nsimilarity {1 - row.dist:.3f}  {row.url}")
            print(f"  section: {row.section}")
            print(f"  {row.content[:220]!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python -m scripts.try_search "your question"')
    main(" ".join(sys.argv[1:]))