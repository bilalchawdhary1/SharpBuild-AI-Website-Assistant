from scripts.audit_gaps import TOPICS, scan


def test_scan_finds_topics_and_ignores_unrelated_lines():
    pages = [{"url": "https://sharpbuild.io/a", "text": "We build apps.\nPricing starts at $500 per month.\nEmail hello@sharpbuild.io"},
            {"url": "https://sharpbuild.io/b", "text": "We accelerate delivery.\nShopify and WooCommerce."}]
    found = scan(pages, TOPICS)
    assert [u for u, _ in found["pricing / budget"]] == ["https://sharpbuild.io/a"]
    assert any("hello@sharpbuild.io" in line for _, line in found["contact channels"])
    assert found["timelines"] == [] and found["location / office"] == []   # "accelerate" is not "rate"