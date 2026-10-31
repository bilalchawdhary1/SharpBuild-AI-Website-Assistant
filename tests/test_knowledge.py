from types import SimpleNamespace

import pytest

from app.services.knowledge_service import retrieve
from scripts.eval_retrieval import found_expected, path_of, summarize
from test_embed import CHUNKS, db, fake_embed, needs_db   # noqa: F401  (db is a fixture)


def test_path_of_and_found_expected():
    assert path_of("https://sharpbuild.io/") == "/"
    assert path_of("https://sharpbuild.io/process/") == "/process"
    hits = [SimpleNamespace(url="https://sharpbuild.io/a"), SimpleNamespace(url="https://sharpbuild.io/b"),
            SimpleNamespace(url="https://sharpbuild.io/c"), SimpleNamespace(url="https://sharpbuild.io/d")]
    assert found_expected(hits, ["/c"]) is True
    assert found_expected(hits, ["/d"]) is False           # outside top-3
    assert found_expected(hits, ["/"]) is False            # exact path match, not substring


def test_summarize():
    rows = [{"kind": "answerable", "top1": 0.7, "ok": True}, {"kind": "answerable", "top1": 0.6, "ok": False},
            {"kind": "offtopic", "top1": 0.4, "ok": None}]
    s = summarize(rows)
    assert s["recall"] == (1, 2)
    assert s["answerable"]["min"] == 0.6 and s["offtopic"]["max"] == 0.4


@needs_db
def test_retrieve_returns_ordered_hits(db):
    from ingestion.embed import sync_chunks
    sync_chunks(db, CHUNKS, fake_embed, "m1")
    hits = retrieve(db, "do you build shopify online stores", fake_embed, k=2)
    assert len(hits) == 2
    assert hits[0].url == "https://sharpbuild.io/services/ecommerce"
    assert hits[0].similarity > hits[1].similarity
    assert 0.0 <= hits[0].similarity <= 1.0