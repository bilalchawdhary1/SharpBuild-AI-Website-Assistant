"""Hand-written, source-linked facts that become searchable chunks.

Why: some visitor questions have NO answer on the site (pricing, team size...).
A verified "not published" fact lets the bot say so confidently, and outranks
unrelated text that merely looks relevant.
Edit content/facts.json, then re-run: ingestion.chunk -> ingestion.embed.
"""
import hashlib
import json
from pathlib import Path

FACTS_PATH = Path("content/facts.json")
REQUIRED = ("id", "topic", "text", "source_url", "verified_on")
SITE = "https://sharpbuild.io"


def load_facts(path: Path = FACTS_PATH) -> list[dict]:
    if not path.exists():
        return []
    facts = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    chunks = []
    for i, f in enumerate(facts):
        missing = [k for k in REQUIRED if not f.get(k)]
        if missing:
            raise ValueError(f"fact #{i} is missing {missing}")
        if f["id"] in seen:
            raise ValueError(f"duplicate fact id: {f['id']}")
        if not f["source_url"].startswith(SITE):
            raise ValueError(f"fact {f['id']}: source_url must be on {SITE}")
        seen.add(f["id"])
        content = f"Page: SharpBuild FAQ\nSection: {f['topic']}\n\n{f['text']}"
        chunks.append({
            "chunk_id": hashlib.sha1(f"fact:{f['id']}\n{content}".encode()).hexdigest()[:16],
            "url": f["source_url"],
            "title": "SharpBuild FAQ",
            "page_type": "facts",
            "section": f["topic"],
            "chunk_index": i,
            "word_count": len(f["text"].split()),
            "content": content,
        })
    return chunks