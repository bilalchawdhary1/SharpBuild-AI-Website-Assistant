"""Stage 3b: turn raw HTML into clean, heading-aware text.

Run from the backend root:  python -m ingestion.clean
"""
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")

# Tags that never contain answer-worthy content.
DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "template"]
# Tags that should start/end a new line of text.
BLOCK_TAGS = ["p", "div", "section", "article", "li", "ul", "ol", "tr", "br", "main",
              "aside", "header", "blockquote", "figure", "table",
              "h1", "h2", "h3", "h4", "h5", "h6"]
# Placeholder contact details seen on the site, e.g. "+44 X XXXX XXXX", "wa.me/44XXXXXXXXXX".
PLACEHOLDER = re.compile(r"X{3,}")
# Decorative step counters ("01", "02") carry no meaning once the text is separated from the layout.
DIGITS_ONLY = re.compile(r"\d{1,2}")
# Lines made only of button/link labels, e.g. "Learn more" or "Start a Project View Portfolio".
UI_NOISE = re.compile(
    r"(?:(?:start a project|view portfolio|see how we work|learn more|read more|view all \w+|explore all \w+)\s*)+",
    re.I,
)


def collapse_repeated_runs(lines: list[str], max_run: int = 60) -> list[str]:
    """Collapse a block of lines that is immediately repeated (carousels/marquees
    duplicate their content for the scrolling effect). Only back-to-back repeats are
    removed, so legitimate repeated labels (e.g. "What you receive" in each process
    stage, separated by different content) are kept."""
    lines = list(lines)
    out: list[str] = []
    i = 0
    while i < len(lines):
        for k in range(min(max_run, (len(lines) - i) // 2), 0, -1):
            if lines[i:i + k] == lines[i + k:i + 2 * k]:
                lines = lines[:i + k] + lines[i + 2 * k:]
                break
        else:
            out.append(lines[i])
            i += 1
    return out


def html_to_lines(html: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    # Turn <h1>-<h4> into markdown-style markers so chunking can use them later.
    for level in range(1, 5):
        for h in root.find_all(f"h{level}"):
            text = " ".join(h.get_text(" ", strip=True).split())
            h.replace_with(NavigableString(f"\n{'#' * level} {text}\n" if text else ""))

    # Adjacent links/buttons would otherwise be glued together ("Start a ProjectView Portfolio").
    for tag in root.find_all(["a", "button"]):
        nxt = tag.next_sibling
        if isinstance(nxt, NavigableString) and nxt[:1] in ".,;:!?)":
            continue
        tag.insert_after(" ")

    # Put line breaks around block elements only, so inline tags
    # (<strong>, <a>) don't split a sentence in half.
    for tag in root.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")

    lines = []
    for raw in root.get_text("").splitlines():
        line = " ".join(raw.split())
        if not line or PLACEHOLDER.search(line) or "wa.me/" in line or UI_NOISE.fullmatch(line) \
                or DIGITS_ONLY.fullmatch(line):
            continue
        lines.append(line)
    return title, collapse_repeated_runs(lines)


def find_boilerplate(pages: list[dict], threshold: float = 0.4) -> set[str]:
    """Lines that appear on more than `threshold` of all pages are site chrome
    (repeated banners, CTAs), not page content."""
    if len(pages) < 5:          # too few pages to judge "repeated"
        return set()
    counts: Counter = Counter()
    for p in pages:
        counts.update(set(p["lines"]))
    # Headings are page structure, not chrome: a heading that repeats across pages
    # (e.g. "## Related solutions") must keep its place in each page.
    return {line for line, c in counts.items()
            if c / len(pages) > threshold and not line.startswith("#")}


def main() -> None:
    index = json.loads((RAW_DIR / "index.json").read_text(encoding="utf-8"))
    pages = []
    for url, meta in index.items():
        html = (RAW_DIR / meta["file"]).read_text(encoding="utf-8")
        title, lines = html_to_lines(html)
        pages.append({"url": url, "title": title, "lines": lines})

    boiler = find_boilerplate(pages)
    print(f"Removed {len(boiler)} repeated boilerplate lines (REVIEW THESE):")
    for line in sorted(boiler):
        print("   -", line[:90])

    out = []
    for p in pages:
        text = "\n".join(l for l in p["lines"] if l not in boiler)
        out.append({"url": p["url"], "title": p["title"], "text": text,
                    "word_count": len(text.split())})

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    (CLEAN_DIR / "pages.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'words':>6}  url")
    for o in sorted(out, key=lambda x: x["url"]):
        flag = "   <-- LOW: JS-rendered or empty?" if o["word_count"] < 60 else ""
        print(f"{o['word_count']:>6}  {o['url']}{flag}")
    print(f"\nSaved {len(out)} pages to {CLEAN_DIR}/pages.json")


if __name__ == "__main__":
    main()