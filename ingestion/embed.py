"""Stage 4b: embed chunks with OpenAI and store them in Postgres (pgvector).

Run from the backend root:  python -m ingestion.embed
Safe to re-run: only new or changed chunks are embedded (and billed).
"""
import json
import sys
import time
from pathlib import Path
from typing import Iterator, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.chunk import EMBEDDING_DIMS, Chunk
from app.services.embeddings import EmbedFn

CHUNKS_PATH = Path("data/chunks.json")
BATCH_SIZE = 64


def batched(items: Sequence, size: int) -> Iterator[Sequence]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def plan_sync(rows: list[tuple[str, str]], chunks: list[dict], model: str
            ) -> tuple[list[dict], set[str]]:
    """Decide what to embed and what to remove. Pure function: no DB, no network.

    rows   = (chunk_id, embedding_model) already stored.
    Returns (chunks to embed, chunk_ids to delete).
    A chunk_id is a hash of url+content, so edited text arrives as a NEW id and
    the old row is deleted. Rows made with a different model are redone.
    """
    wanted = {c["chunk_id"]: c for c in chunks}            # also dedupes repeated ids
    keep = {cid for cid, m in rows if m == model and cid in wanted}
    to_delete = {cid for cid, _ in rows if cid not in keep}
    to_add = [c for cid, c in wanted.items() if cid not in keep]
    return to_add, to_delete


def sync_chunks(db: Session, chunks: list[dict], embed_fn: EmbedFn, model: str,
                batch_size: int = BATCH_SIZE, pause: float = 0.0) -> dict:
    rows = [(r.chunk_id, r.embedding_model) for r in db.execute(
        select(Chunk.chunk_id, Chunk.embedding_model))]
    to_add, to_delete = plan_sync(rows, chunks, model)

    if to_delete:
        db.execute(delete(Chunk).where(Chunk.chunk_id.in_(to_delete)))
        db.commit()
    for n, batch in enumerate(batched(to_add, batch_size)):
        if n and pause:
            time.sleep(pause)             # stay under free-tier rate limits
        vectors = embed_fn([c["content"] for c in batch])
        if len(vectors) != len(batch) or any(len(v) != EMBEDDING_DIMS for v in vectors):
            raise RuntimeError(f"embedding API returned unexpected shapes (expected {EMBEDDING_DIMS} dims)")
        db.add_all(
            Chunk(chunk_id=c["chunk_id"], url=c["url"], title=c["title"],
                section=c["section"], page_type=c.get("page_type", "other"),
                chunk_index=c["chunk_index"], word_count=c["word_count"],
                content=c["content"], embedding=v, embedding_model=model)
            for c, v in zip(batch, vectors)
        )
        db.commit()            # commit per batch so a crash keeps earlier progress
        print(f"  embedded {len(batch)} chunks")
    return {"added": len(to_add), "deleted": len(to_delete),
            "unchanged": len({c["chunk_id"] for c in chunks}) - len(to_add)}


def main() -> None:
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.services.embeddings import make_gemini_embedder, with_retries

    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is empty. Get a free key at https://aistudio.google.com/apikey "
                "and add it to your .env file.")
    if not CHUNKS_PATH.exists():
        sys.exit(f"{CHUNKS_PATH} not found. Run: python -m ingestion.chunk")

    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    embed_fn = with_retries(make_gemini_embedder(
        settings.gemini_api_key, settings.embedding_model, "RETRIEVAL_DOCUMENT"))
    with SessionLocal() as db:
        result = sync_chunks(db, chunks, embed_fn, settings.embedding_model, pause=2.0)
    print(result)


if __name__ == "__main__":
    main()