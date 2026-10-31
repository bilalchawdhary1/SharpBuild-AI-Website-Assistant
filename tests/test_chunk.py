from ingestion import chunk as c


def page(text, title="Services | SharpBuild", url="https://sharpbuild.io/services"):
    return {"url": url, "title": title, "text": text}


def test_heading_breadcrumbs():
    blocks = c.parse_blocks("# Services\n## Web Development\nWe build sites.\n## Mobile\nWe build apps.")
    assert [b.path for b in blocks] == [
        ["Services"], ["Services", "Web Development"], ["Services", "Mobile"]]


def test_small_sections_merge_and_header_is_clean():
    chunks = c.build_chunks(page(
        "# Services\n## Web Development\nWe build websites with Next.js and Laravel today.\n"
        "## Mobile\nWe build mobile apps for iOS and Android platforms."))
    assert len(chunks) == 1
    assert chunks[0]["content"].startswith("Page: Services\nSection: Services")
    assert "| SharpBuild" not in chunks[0]["content"]


def test_big_section_is_split_with_heading_and_overlap():
    lines = [f"line{i} " + "word " * 9 for i in range(60)]          # about 600 words
    chunks = c.build_chunks(page("# Big\n" + "\n".join(lines)))
    assert len(chunks) > 1
    bodies = [ch["content"].split("\n\n", 1)[1].splitlines() for ch in chunks]
    for ch, body in zip(chunks, bodies):
        assert ch["word_count"] <= c.MAX_WORDS
        assert body[0] == "# Big"                                    # heading repeated
    for prev, nxt in zip(bodies, bodies[1:]):
        assert prev[-1] == nxt[1]                                    # one-line overlap


def test_big_sections_under_different_h2_stay_separate():
    text = "## One\n" + " ".join(["w"] * 60) + "\n## Two\n" + " ".join(["v"] * 60)
    assert len(c.build_chunks(page(text))) == 2


def test_tiny_pages_are_dropped():
    assert c.build_chunks(page("# Hi\nok")) == []


def test_chunk_ids_are_stable_and_change_with_content():
    text = "# A\n" + " ".join(["w"] * 20)
    assert c.build_chunks(page(text))[0]["chunk_id"] == c.build_chunks(page(text))[0]["chunk_id"]
    assert c.build_chunks(page(text))[0]["chunk_id"] != c.build_chunks(page(text + " extra"))[0]["chunk_id"]


def test_build_corpus_chunks_includes_curated_facts_and_skips_legal_pages():
    chunks = c.build_corpus_chunks([
        page("# About\n" + " ".join(["word"] * 30)),
        page("# Terms\n" + " ".join(["legal"] * 30),
             url="https://sharpbuild.io/terms"),
    ])
    fact_chunks = [chunk for chunk in chunks if chunk["page_type"] == "facts"]
    assert fact_chunks
    assert all(chunk["url"] != "https://sharpbuild.io/terms" for chunk in chunks)