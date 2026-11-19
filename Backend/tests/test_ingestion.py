from ingestion.clean import find_boilerplate, html_to_lines
from ingestion.crawl import fetch_with_retries, normalize, sitemap_urls
import httpx

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


def test_sitemap_parser_normalizes_urls_and_reads_priority():
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://sharpbuild.io/services/?a=1#top</loc><priority>0.9</priority></url>
      <url><loc>https://sharpbuild.io/portfolio/</loc><priority>0.7</priority></url>
      <url><loc>https://other.example/x</loc><priority>1.0</priority></url>
    </urlset>
    """
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=xml, request=request)
    )
    with httpx.Client(transport=transport) as client:
        found = sitemap_urls(client)
    assert found == {
        "https://sharpbuild.io/services": 0.9,
        "https://sharpbuild.io/portfolio": 0.7,
    }


def test_fetch_retries_transient_status_then_succeeds():
    responses = [503, 503, 200]

    def handler(request):
        status = responses.pop(0)
        return httpx.Response(status, request=request)

    waits = []
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        response = fetch_with_retries(
            client,
            "https://sharpbuild.io/",
            base_delay=0.25,
            sleep=waits.append,
        )
    assert response.status_code == 200
    assert waits == [0.25, 0.5]
