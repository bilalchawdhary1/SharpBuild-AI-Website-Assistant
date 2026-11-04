from ingestion.clean import find_boilerplate, html_to_lines


def test_digit_only_step_counters_are_dropped():
    _, lines = html_to_lines("<main><div>01</div><h3>Discover</h3><div>06</div><p>Real text here.</p><p>2026 roadmap</p></main>")
    assert "01" not in lines and "06" not in lines
    assert "### Discover" in lines and "2026 roadmap" in lines     # real content with digits survives


def test_repeated_headings_are_kept_but_repeated_chrome_is_removed():
    pages = [{"lines": ["## Related solutions", "Have an idea worth building?", f"unique {i}"]} for i in range(6)]
    assert find_boilerplate(pages) == {"Have an idea worth building?"}