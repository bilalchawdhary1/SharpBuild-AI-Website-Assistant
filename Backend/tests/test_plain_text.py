from app.services.ai_service import SYSTEM_INSTRUCTION
from app.services.chat_service import attach_sources
from app.services.knowledge_service import Hit


def hit(n):
    return Hit(f"c{n}", f"https://sharpbuild.io/p{n}", f"T{n}", "S", "services", "text", 0.9)


def test_visible_text_has_no_citation_markers_but_keeps_formatting_the_widget_renders():
    raw = ("Process:\n1. **Discover**: learn the goals [1], [2].\n2. **Build**: ship in steps [2], [1].\n"
           "\u2022 **Fast** [1]")
    text, sources = attach_sources(raw, [hit(1), hit(2)])
    assert text == ("Process:\n1. **Discover**: learn the goals.\n2. **Build**: ship in steps.\n\u2022 **Fast**")
    assert [s.url for s in sources] == ["https://sharpbuild.io/p1", "https://sharpbuild.io/p2"]


def test_normal_text_and_brackets_are_left_alone():
    text, _ = attach_sources("We build 2-3 apps a year - mostly web [1]. See [docs] and arr[12345].", [hit(1)])
    assert text == "We build 2-3 apps a year - mostly web. See [docs] and arr[12345]."


def test_prompt_asks_for_steps_bold_terms_typo_tolerance_and_no_markup_beyond_that():
    for phrase in ("one-sentence direct answer", "numbered list", "**bold**", "typos", "ONE short clarifying question",
                   "No headings, tables"):
        assert phrase in SYSTEM_INSTRUCTION
