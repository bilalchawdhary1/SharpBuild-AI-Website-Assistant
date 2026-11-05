from app.services.ai_service import SYSTEM_INSTRUCTION
from app.services.chat_service import attach_sources
from app.services.knowledge_service import Hit


def hit(n):
    return Hit(f"c{n}", f"https://sharpbuild.io/p{n}", f"T{n}", "S", "services", "text", 0.9)


def test_markdown_the_model_sneaks_in_is_removed_and_citations_are_tidied():
    raw = ("Process:\n1. **Discover**: learn the goals [1], [2].\n2. **Build**: ship in steps [2], [1].\n"
           "## Heading\n* first point\n- second point")
    text, sources = attach_sources(raw, [hit(1), hit(2)])
    assert text == ("Process:\n1. Discover: learn the goals [1][2].\n2. Build: ship in steps [2][1].\n"
                    "Heading\n\u2022 first point\n\u2022 second point")
    assert [s.url for s in sources] == ["https://sharpbuild.io/p1", "https://sharpbuild.io/p2"]


def test_normal_text_is_left_alone():
    text, _ = attach_sources("We build 2-3 apps a year - mostly web [1]. A list: 1, 2, 3.", [hit(1)])
    assert text == "We build 2-3 apps a year - mostly web [1]. A list: 1, 2, 3."


def test_prompt_asks_for_plain_text():
    assert "Plain text only" in SYSTEM_INSTRUCTION
