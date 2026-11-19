from types import SimpleNamespace

import pytest

from app.services.knowledge_service import Hit, hybrid_score, lexical_coverage, rerank_hits, retrieve
from scripts.eval_retrieval import check, found_expected, found_fact, path_of, summarize
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


def test_hybrid_retrieval_uses_exact_term_coverage():
    assert lexical_coverage(
        "Do you build Shopify stores?",
        "Shopify store development and ecommerce online stores",
    ) == pytest.approx(1.0)
    assert lexical_coverage(
        "Do you build Shopify stores?",
        "Mobile app development",
    ) == pytest.approx(0.0)
    assert hybrid_score(0.8, 1.0) == pytest.approx(0.83)


def test_verified_fact_section_match_is_reranked_first():
    fact = Hit("fact", "https://sharpbuild.io/contact", "SharpBuild FAQ",
               "Pricing and quotes", "facts", "No prices are published.", 0.74)
    page = Hit("page", "https://sharpbuild.io/services/web", "Web development",
               "Pricing", "services", "Web development options.", 0.75)
    reranked = rerank_hits("How much does a website cost?", [page, fact])
    assert reranked[0].chunk_id == "fact"


@needs_db
def test_retrieve_returns_ordered_hits(db):
    from ingestion.embed import sync_chunks
    sync_chunks(db, CHUNKS, fake_embed, "m1")
    hits = retrieve(db, "do you build shopify online stores", fake_embed, k=2)
    assert len(hits) == 2
    assert hits[0].url == "https://sharpbuild.io/services/ecommerce"
    assert hits[0].similarity > hits[1].similarity
    assert 0.0 <= hits[0].similarity <= 1.0


def test_fact_checks_and_fact_recall():
    fact = SimpleNamespace(url="https://sharpbuild.io/contact", page_type="facts", section="Pricing and quotes")
    page = SimpleNamespace(url="https://sharpbuild.io/services/web", page_type="services", section="Pricing and quotes")
    assert found_fact([fact], ["Pricing and quotes"]) is True
    assert found_fact([page], ["Pricing and quotes"]) is False        # must really be a fact chunk
    assert check([fact], {"expect": [], "expect_fact": ["Pricing and quotes"]}) is True
    assert check([page], {"expect": [], "expect_fact": ["Pricing and quotes"]}) is False
    assert check([page], {"expect": [], "expect_fact": []}) is None   # nothing expected -> not scored
    rows = [{"kind": "unpublished", "top1": 0.7, "ok": True}, {"kind": "unpublished", "top1": 0.6, "ok": False},
            {"kind": "unpublished", "top1": 0.5, "ok": None}]
    assert summarize(rows)["fact_recall"] == (1, 2)