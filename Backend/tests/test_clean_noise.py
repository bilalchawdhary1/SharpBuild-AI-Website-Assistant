from ingestion.clean import collapse_repeated_runs, html_to_lines

HOME = """<html><head><title>x</title></head><body><main>
<h1>Digital products. Built sharp.</h1>
<div><a href="/contact">Start a Project</a><a href="/portfolio">View Portfolio</a></div>
<div>Technologies We Work On</div>
<div class="marquee">
<div>OpenAI APIs</div><div>Next.js</div><div>Laravel</div>
<div>OpenAI APIs</div><div>Next.js</div><div>Laravel</div>
<div>OpenAI APIs</div><div>Next.js</div><div>Laravel</div></div>
<h2>Services</h2><div><a href="/s">Learn more</a></div>
<p>See our <a href="/process">process</a>. We ship fast.</p>
</main></body></html>
"""


def test_button_labels_and_marquee_duplicates_are_removed():
    _, lines = html_to_lines(HOME)
    joined = "\n".join(lines)
    for noise in ("Start a Project", "View Portfolio", "Learn more"):
        assert noise not in joined
    assert lines.count("Next.js") == 1 and lines.count("OpenAI APIs") == 1
    assert "# Digital products. Built sharp." in lines


def test_inline_link_keeps_sentence_whole():
    _, lines = html_to_lines(HOME)
    assert "See our process. We ship fast." in lines


def test_adjacent_buttons_are_not_glued_together():
    _, lines = html_to_lines(
        "<main><div><a>Alpha one</a><a>Beta two</a></div><p>Body text here.</p></main>")
    assert "Alpha one Beta two" in lines


def test_collapse_only_removes_back_to_back_repeats():
    assert collapse_repeated_runs(["a", "b", "a", "b", "a", "b", "c"]) == ["a", "b", "c"]
    # a label repeated with different content between is legitimate and kept
    keep = ["What you receive", "Spec", "What you receive", "Prototype"]
    assert collapse_repeated_runs(keep) == keep