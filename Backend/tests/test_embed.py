import hashlib
import math
import os
import re

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.chunk import EMBEDDING_DIMS, Chunk
from ingestion.embed import batched, plan_sync, sync_chunks


def chunk(cid, url="https://sharpbuild.io/x", content="text"):
    return {"chunk_id": cid, "url": url, "title": "T", "section": "S", "page_type": "services",
            "chunk_index": 0, "word_count": 3, "content": content}


# ---------- pure logic: always runs ----------
def test_batched():
    assert [list(b) for b in batched([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]


def test_plan_sync_keeps_adds_and_deletes():
    rows = [("a", "m"), ("b", "m"), ("c", "old"), ("e", "old")]
    chunks = [chunk("a"), chunk("d"), chunk("e")]
    to_add, to_delete = plan_sync(rows, chunks, "m")
    assert sorted(c["chunk_id"] for c in to_add) == ["d", "e"]   # d is new, e used an old model
    assert to_delete == {"b", "c", "e"}                           # b removed from site, c/e stale model


def test_plan_sync_dedupes_repeated_ids():
    to_add, _ = plan_sync([], [chunk("a"), chunk("a")], "m")
    assert len(to_add) == 1


# ---------- real Postgres + pgvector: runs only when TEST_DATABASE_URL is set ----------
URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to a TEST database")


def fake_embed(texts):
    """Deterministic bag-of-words vectors: shared words => similar vectors."""
    out = []
    for t in texts:
        v = [0.0] * EMBEDDING_DIMS
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % EMBEDDING_DIMS] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


@pytest.fixture
def db():
    # The fixture DROPS the chunks table, so refuse to run against anything not named *test*.
    assert "test" in (make_url(URL).database or "").lower(), "TEST_DATABASE_URL must point at a test database"
    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine, tables=[Chunk.__table__])
    Base.metadata.create_all(engine, tables=[Chunk.__table__])
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine, tables=[Chunk.__table__])


CHUNKS = [
    chunk("c1", "https://sharpbuild.io/services/ecommerce", "Shopify store development and WooCommerce online stores"),
    chunk("c2", "https://sharpbuild.io/services/mobile", "iOS and Android mobile app development"),
    chunk("c3", "https://sharpbuild.io/process", "Discovery, architecture, design, build, validation and shipping"),
]


@needs_db
def test_sync_is_idempotent_and_detects_changes(db):
    assert sync_chunks(db, CHUNKS, fake_embed, "m1", batch_size=2) == {"added": 3, "deleted": 0, "unchanged": 0}
    assert sync_chunks(db, CHUNKS, fake_embed, "m1") == {"added": 0, "deleted": 0, "unchanged": 3}

    edited = [chunk("c1b", CHUNKS[0]["url"], "changed text")] + CHUNKS[1:]
    assert sync_chunks(db, edited, fake_embed, "m1") == {"added": 1, "deleted": 1, "unchanged": 2}

    assert sync_chunks(db, edited, fake_embed, "m2") == {"added": 3, "deleted": 3, "unchanged": 0}  # new model => redo
    assert db.scalar(select(Chunk.embedding_model).limit(1)) == "m2"


@needs_db
def test_cosine_search_ranks_the_relevant_chunk_first(db):
    sync_chunks(db, CHUNKS, fake_embed, "m1")
    query = fake_embed(["do you build shopify online stores"])[0]
    distance = Chunk.embedding.cosine_distance(query)          # same expression scripts/try_search.py uses
    rows = db.execute(select(Chunk.url, distance.label("d")).order_by(distance).limit(3)).all()
    assert rows[0].url == "https://sharpbuild.io/services/ecommerce"
    assert rows[0].d < rows[1].d