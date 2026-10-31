from ingestion.chunk import build_chunks, page_type


def test_page_types():
    assert page_type("https://sharpbuild.io/") == "home"
    assert page_type("https://sharpbuild.io/services/web-development") == "services"
    assert page_type("https://sharpbuild.io/portfolio/x") == "portfolio"
    assert page_type("https://sharpbuild.io/white-label") == "white-label"
    for legal in ("privacy", "cookies", "terms"):
        assert page_type(f"https://sharpbuild.io/{legal}") == "legal"


def test_chunks_carry_page_type():
    page = {"url": "https://sharpbuild.io/process", "title": "Process | SharpBuild",
            "text": "# Process\n" + " ".join(["word"] * 30)}
    assert build_chunks(page)[0]["page_type"] == "process"