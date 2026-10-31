"""Find out what the website says (and does NOT say) about topics visitors ask about.

Usage:  python -m scripts.audit_gaps
Scans data/clean/pages.json (all crawled pages, including legal ones).
A topic with zero real matches is a candidate for a "not published" answer.
Only write such an answer after reading the matches here yourself.
"""
import json
import re
from pathlib import Path

PAGES_PATH = Path("data/clean/pages.json")
MAX_SHOWN = 12

TOPICS = {
    "pricing / budget": r"\bpric(?:e|es|ing)\b|\bcosts?\b|\bquote\b|\bbudgets?\b|\brates?\b|\bhourly\b|[$£€]\s?\d|\bper (?:hour|month|week)\b",
    "timelines": r"\btimelines?\b|\bturnaround\b|\bdeadlines?\b|\b\d+\s*(?:-|–|to)?\s*(?:\d+\s*)?(?:weeks?|months?|days?)\b",
    "team size / company facts": r"\bteam of\b|\bemployees?\b|\bfounded\b|\bestablished\b|\bsince (?:19|20)\d\d\b|\b\d+\+?\s+(?:engineers|developers|people|clients|projects)\b",
    "location / office": r"\boffices?\b|\bheadquarters?\b|\bbased in\b|\blocated\b|\btime ?zones?\b|\bremote(?:ly)?\b",
    "guarantees / support / maintenance": r"\bguarantee[sd]?\b|\bwarranty\b|\brefunds?\b|\bsupport\b|\bmaintenance\b|\bSLA\b|\bretainer\b",
    "contact channels": r"[\w.+-]+@[\w-]+\.[\w.]+|\bphone\b|\bwhatsapp\b|\bcall\b|\bbook a\b|\bschedule\b",
}


def scan(pages: list[dict], patterns: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    """Return {topic: [(url, matching line), ...]}."""
    compiled = {t: re.compile(p, re.I) for t, p in patterns.items()}
    found: dict[str, list[tuple[str, str]]] = {t: [] for t in patterns}
    for page in pages:
        for line in page["text"].splitlines():
            for topic, rx in compiled.items():
                if rx.search(line):
                    found[topic].append((page["url"], line.strip()))
    return found


def main() -> None:
    pages = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
    found = scan(pages, TOPICS)
    print(f"Scanned {len(pages)} pages.\n")
    for topic, matches in found.items():
        print(f"=== {topic}: {len(matches)} matching lines ===")
        for url, line in matches[:MAX_SHOWN]:
            print(f"  {url.replace('https://sharpbuild.io', '') or '/':<45} {line[:110]}")
        if len(matches) > MAX_SHOWN:
            print(f"  ... and {len(matches) - MAX_SHOWN} more")
        print()


if __name__ == "__main__":
    main()