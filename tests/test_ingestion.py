from ingestion.clean import find_boilerplate, html_to_lines
from ingestion.crawl import normalize

SAMPLE = """
<html><head><title>Demo | SharpBuild</title></head><body>
<nav><a href="/">Home</a><a href="/services/">Services</a></nav>
<main>
  <h1>Web Development</h1>
  <p>We build with <strong>Next.js</strong> and Laravel.</p>
  <h2>Contact</h2>
  <div>Call +44 X XXXX XXXX</div>
  <div><a href="https://wa.me/44XXXXXXXXXX">WhatsApp</a></div>
  <div>Email hello@sharpbuild.io</div>
</main>
<footer>Copyright footer text</footer>
<script>var x = 1;</script>
</body></html>
"""


def test_cleaning_keeps_content_and_drops_noise():
    title, lines = html_to_lines(SAMPLE)
    joined = "\n".join(lines)
    assert title == "Demo | SharpBuild"
    assert "# Web Development" in lines
    assert "We build with Next.js and Laravel." in lines   # inline tags don't split text
    assert "Email hello@sharpbuild.io" in joined
    assert "XXXX" not in joined and "wa.me" not in joined  # placeholders removed
    assert "Copyright" not in joined and "var x" not in joined and "Services" not in joined


def test_boilerplate_detection():
    pages = [{"lines": ["Have an idea worth building?", f"unique {i}"]} for i in range(6)]
    assert find_boilerplate(pages) == {"Have an idea worth building?"}


def test_normalize():
    assert normalize("https://sharpbuild.io/services/?a=1#top") == "https://sharpbuild.io/services"
    assert normalize("https://sharpbuild.io") == "https://sharpbuild.io/"
    assert normalize("https://other.com/x") is None
    assert normalize("https://sharpbuild.io/logo.png") is None
    assert normalize("mailto:hello@sharpbuild.io") is None
