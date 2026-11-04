from ingestion.chunk import build_chunks
from ingestion.clean import html_to_lines


def test_see_how_we_work_button_is_noise():
    _, lines = html_to_lines("<main><div><a>Start a Project</a> <a>See How We Work</a></div><p>Real content here.</p></main>")
    assert lines == ["Real content here."]


def test_section_uses_first_heading_even_after_an_eyebrow_line():
    page = {"url": "https://sharpbuild.io/services/x", "title": "X | SharpBuild",
            "text": "WordPress & Shopify\n# WordPress done right\n" + " ".join(["word"] * 30)}
    chunk = build_chunks(page)[0]
    assert chunk["section"] == "WordPress done right"
    assert "Section: WordPress done right" in chunk["content"]