"""Stage 4a: split cleaned pages into retrieval-sized chunks.

Run from the backend root:  python -m ingestion.chunk
Input : data/clean/pages.json   (from ingestion.clean)
Output: data/chunks.json
"""
import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

CLEAN_PATH = Path("data/clean/pages.json")
CHUNKS_PATH = Path("data/chunks.json")

# Sizes are in WORDS (roughly 1 word ~ 1.3 tokens). Tune after reading real output.
TARGET_WORDS = 200      # aim for chunks about this big
MAX_WORDS = 300         # a single section bigger than this gets split
MIN_WORDS = 50          # smaller fragments get merged forward
DROP_BELOW_WORDS = 8    # chunks with less real content than this are noise

HEADING = re.compile(r"^(#{1,4})\s+(.*)$")

# Legal pages are not indexed for answers: the privacy page was a placeholder when
# inspected, and a chatbot must not paraphrase legal text. Link to them instead.
LEGAL_PATHS = {"/privacy", "/cookies", "/terms"}


def build_corpus_chunks(pages: list[dict]) -> list[dict]:
    from ingestion.facts import load_facts

    page_chunks = [
        chunk
        for page in pages
        if page_type(page["url"]) != "legal"
        for chunk in build_chunks(page)
    ]
    return page_chunks + load_facts()


def page_type(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if not path:
        return "home"
    if path in LEGAL_PATHS:
        return "legal"
    return path.split("/")[1]          # services, solutions, portfolio, about, process, ...


@dataclass
class Block:
    """One heading plus the lines under it."""
    path: list[str]     # e.g. ["Services", "Web Development"]
    level: int          # 0 = text before any heading, 1-4 = heading depth
    lines: list[str]    # includes the heading line itself as the first line

    @property
    def words(self) -> int:
        return sum(len(line.split()) for line in self.lines)


def parse_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    stack: list[tuple[int, str]] = []          # the current heading "breadcrumb"
    cur = Block(path=[], level=0, lines=[])
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            if cur.lines:
                blocks.append(cur)
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            cur = Block(path=[t for _, t in stack], level=level, lines=[line])
        else:
            cur.lines.append(line)
    if cur.lines:
        blocks.append(cur)
    return blocks


def split_oversize(block: Block) -> list[Block]:
    """Split a long section on line boundaries, repeating its heading and
    overlapping one line so a fact on a boundary isn't cut off from its context."""
    if block.words <= MAX_WORDS:
        return [block]
    has_heading = bool(HEADING.match(block.lines[0]))
    head = block.lines[:1] if has_heading else []
    body = block.lines[len(head):]
    pieces: list[Block] = []
    group: list[str] = []
    count = 0
    for line in body:
        w = len(line.split())
        if group and count + w > TARGET_WORDS:
            pieces.append(Block(block.path, block.level, head + group))
            group = group[-1:]                          # one-line overlap
            count = len(group[0].split())
        group.append(line)
        count += w
    if group:
        pieces.append(Block(block.path, block.level, head + group))
    return pieces


def pack(blocks: list[Block]) -> list[list[Block]]:
    """Greedily group blocks into chunks. Tiny fragments (e.g. a heading with one
    line) merge forward; once a chunk is big enough, a new H1/H2 starts a new one."""
    chunks: list[list[Block]] = []
    cur: list[Block] = []
    words = 0
    for b in blocks:
        big_enough = words >= MIN_WORDS
        new_topic = b.level in (1, 2)
        if cur and big_enough and (new_topic or words + b.words > TARGET_WORDS):
            chunks.append(cur)
            cur, words = [], 0
        cur.append(b)
        words += b.words
    if cur:
        chunks.append(cur)
    return chunks


def build_chunks(page: dict) -> list[dict]:
    title = page["title"].split("|")[0].strip() or page["url"]
    blocks = [p for b in parse_blocks(page["text"]) for p in split_oversize(b)]
    out: list[dict] = []
    for group in pack(blocks):
        body = "\n".join(line for b in group for line in b.lines)
        word_count = len(body.split())
        if word_count < DROP_BELOW_WORDS:
            continue
        # Text before the first heading has no path; use the first block that has one.
        section = " > ".join(next((b.path for b in group if b.path), []))
        # Context header: embedded together with the text, so a chunk that says
        # only "From $X per month" still carries its page and section name.
        header = f"Page: {title}" + (f"\nSection: {section}" if section else "")
        content = f"{header}\n\n{body}"
        out.append({
            "chunk_id": hashlib.sha1(f"{page['url']}\n{content}".encode()).hexdigest()[:16],
            "url": page["url"],
            "title": title,
            "page_type": page_type(page["url"]),
            "section": section,
            "chunk_index": len(out),
            "word_count": word_count,
            "content": content,
        })
    return out


def main() -> None:
    pages = json.loads(CLEAN_PATH.read_text(encoding="utf-8"))
    skipped = [p["url"] for p in pages if page_type(p["url"]) == "legal"]
    pages = [p for p in pages if page_type(p["url"]) != "legal"]
    if skipped:
        print("Not indexed (legal pages):", ", ".join(skipped))
    chunks = build_corpus_chunks(pages)
    CHUNKS_PATH.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    sizes = [c["word_count"] for c in chunks]
    print(f"{len(pages)} pages -> {len(chunks)} chunks")
    if sizes:
        print(f"words per chunk: min {min(sizes)}, median {int(statistics.median(sizes))}, max {max(sizes)}")
    print(f"\n{'chunks':>6}  url")
    per_page: dict[str, int] = {}
    for c in chunks:
        per_page[c["url"]] = per_page.get(c["url"], 0) + 1
    for url in sorted(per_page):
        print(f"{per_page[url]:>6}  {url}")
    print("\n--- first 3 chunks ---")
    for c in chunks[:3]:
        print(f"\n[{c['chunk_id']}] {c['url']} ({c['word_count']} words)\n{c['content']}")


if __name__ == "__main__":
    main()