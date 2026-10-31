import json

import pytest

from ingestion.facts import FACTS_PATH, load_facts


def write(tmp_path, facts):
    p = tmp_path / "facts.json"
    p.write_text(json.dumps(facts), encoding="utf-8")
    return p


GOOD = {"id": "a", "topic": "Pricing", "text": "Not published.", "source_url": "https://sharpbuild.io/contact", "verified_on": "2026-10-31"}


def test_fact_becomes_a_chunk_with_context_header():
    chunks = load_facts(FACTS_PATH)                      # the real content/facts.json must be valid
    assert chunks and all(c["page_type"] == "facts" for c in chunks)
    assert all(c["content"].startswith("Page: SharpBuild FAQ\nSection: ") for c in chunks)
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)


def test_missing_file_gives_no_facts(tmp_path):
    assert load_facts(tmp_path / "nope.json") == []


def test_validation_errors(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        load_facts(write(tmp_path, [{**GOOD, "text": ""}]))
    with pytest.raises(ValueError, match="duplicate"):
        load_facts(write(tmp_path, [GOOD, GOOD]))
    with pytest.raises(ValueError, match="source_url"):
        load_facts(write(tmp_path, [{**GOOD, "source_url": "https://evil.example/x"}]))


def test_changing_fact_text_changes_chunk_id(tmp_path):
    a = load_facts(write(tmp_path, [GOOD]))[0]["chunk_id"]
    b = load_facts(write(tmp_path, [{**GOOD, "text": "Now published."}]))[0]["chunk_id"]
    assert a != b