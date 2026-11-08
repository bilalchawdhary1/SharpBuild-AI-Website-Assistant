import pytest

from app.services.knowledge_service import Hit
from app.services.streaming import CitationStripper, NoAnswerGate, sources_from_citations, stream_events


def hit(n):
    return Hit(f"c{n}", f"https://sharpbuild.io/p{n}", f"T{n}", "S", "services", "text", 0.9)


def run(chunks):
    s = CitationStripper()
    return "".join(s.feed(c) for c in chunks) + s.finish(), s.cited


# ---------- citation stripping, however the text is cut into pieces ----------
@pytest.mark.parametrize("pieces", [
    ["We build apps [1]. Also web [2]."],
    ["We build apps ", "[1", "]", ". Also web [", "2", "]."],
    list("We build apps [1]. Also web [2]."),                          # one character at a time
    ["We build apps", " [1]", ". Also web", " [2]."],
])
def test_markers_are_removed_with_their_leading_space_whatever_the_chunking(pieces):
    text, cited = run(pieces)
    assert text == "We build apps. Also web."
    assert cited == [1, 2]


def test_multi_citations_and_spacing_cases():
    assert run(["Shopify [1][2] and more [3, 4] here."]) == ("Shopify and more here.", [1, 2, 3, 4])
    assert run(["End of line [1]\nNext line"]) == ("End of line\nNext line", [1])     # newline survives
    assert run(["- item one [1]\n- item two [2]"]) == ("- item one\n- item two", [1, 2])


@pytest.mark.parametrize("pieces", [
    ["goals [1], [2]."],
    ["goals [1],", " [2]."],
    ["goals [1]", ", ", "[2", "]."],
    list("goals [1], [2]."),
])
def test_commas_between_citations_are_removed_too(pieces):
    assert run(pieces) == ("goals.", [1, 2])


def test_a_comma_after_a_citation_is_kept_when_no_other_marker_follows():
    assert run(["goals [1], and more"]) == ("goals, and more", [1])
    assert run(["goals [1],", " and more"]) == ("goals, and more", [1])
    assert run(["goals [1] [2] end"]) == ("goals end", [1, 2])
    assert run(["see [1],"]) == ("see,", [1])                          # stream ended right after the comma


def test_ordinary_brackets_and_unfinished_markers_are_not_eaten():
    assert run(["See [docs] now"]) == ("See [docs] now", [])
    assert run(["array[12345] ok"]) == ("array[12345] ok", [])
    assert run(["price [1"]) == ("price [1", [])                       # stream ended mid-marker: shown as typed
    assert run(["a [x", "y] b"]) == ("a [xy] b", [])


def test_trailing_space_is_held_until_the_next_piece_decides_its_fate():
    s = CitationStripper()
    assert s.feed("word ") == "word"          # space held back: a marker might follow
    assert s.feed("next") == " next"


# ---------- [[NO_ANSWER]] gate ----------
def test_gate_detects_the_marker_even_when_split_and_releases_ordinary_text():
    gate = NoAnswerGate()
    assert gate.feed("[[NO_") == ("", False)
    assert gate.feed("ANSWER]]") == ("", True)

    gate = NoAnswerGate()
    assert gate.feed("  Yes") == ("  Yes", False)                       # diverges from the marker: released at once
    assert gate.feed(", we do") == (", we do", False)

    gate = NoAnswerGate()
    assert gate.feed("[[N") == ("", False)
    assert gate.flush() == "[[N"                                       # stream ended while holding a prefix


# ---------- whole streams ----------
def test_stream_events_emit_clean_deltas_then_done_with_sources_in_citation_order():
    hits = [hit(1), hit(2), hit(3)]
    events = list(stream_events(["Yes, we do [3]", ". Also [", "1]."], hits))
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert deltas == "Yes, we do. Also."
    done = events[-1]
    assert done["type"] == "done" and done["answer"] == "Yes, we do. Also." and done["fallback"] is False
    assert [s["url"] for s in done["sources"]] == ["https://sharpbuild.io/p3", "https://sharpbuild.io/p1"]


def test_stream_never_starts_with_blank_space_and_done_matches_the_streamed_text():
    events = list(stream_events(["\n\n  ", "Hello", " there\n"], [hit(1)]))
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert deltas.startswith("Hello") and events[-1]["answer"] == "Hello there"


def test_model_saying_no_answer_ends_the_stream_before_any_text():
    events = list(stream_events(["[[NO_ANSWER]]"], [hit(1)]))
    assert events == [{"type": "no_answer"}]


def test_an_empty_stream_is_an_error():
    with pytest.raises(RuntimeError):
        list(stream_events(["", "   "], [hit(1)]))


def test_sources_ignore_invalid_numbers_and_duplicate_pages():
    hits = [hit(1), hit(2)]
    assert [s.url for s in sources_from_citations([2, 9, 2, 1, 0], hits)] == ["https://sharpbuild.io/p2", "https://sharpbuild.io/p1"]
