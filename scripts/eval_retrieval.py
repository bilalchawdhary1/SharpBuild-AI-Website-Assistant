"""Measure retrieval quality and see where a similarity threshold could go.

Usage:  python -m scripts.eval_retrieval
Reads eval/questions.json. Makes one embedding call per question (free tier).
"""
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlparse

QUESTIONS = Path("eval/questions.json")
K = 3


def path_of(url: str) -> str:
    return urlparse(url).path.rstrip("/") or "/"


def found_expected(hits, expected: list[str], k: int = K) -> bool:
    return any(path_of(h.url) in expected for h in hits[:k])


def summarize(rows: list[dict]) -> dict:
    """rows: {"kind", "top1", "ok"}. Returns per-kind stats."""
    out = {}
    for kind in ("answerable", "unpublished", "offtopic"):
        sims = [r["top1"] for r in rows if r["kind"] == kind]
        if not sims:
            continue
        out[kind] = {"n": len(sims), "min": min(sims), "median": statistics.median(sims), "max": max(sims)}
    ans = [r for r in rows if r["kind"] == "answerable"]
    out["recall"] = (sum(r["ok"] for r in ans), len(ans))
    return out


def main() -> None:
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.services.embeddings import make_gemini_embedder, with_retries
    from app.services.knowledge_service import retrieve

    settings = get_settings()
    embed = with_retries(make_gemini_embedder(
        settings.gemini_api_key, settings.embedding_model, "RETRIEVAL_QUERY"))
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))

    rows = []
    with SessionLocal() as db:
        for item in questions:
            hits = retrieve(db, item["q"], embed, k=K)
            top1 = hits[0].similarity
            ok = found_expected(hits, item["expect"]) if item["kind"] == "answerable" else None
            rows.append({"kind": item["kind"], "top1": top1, "ok": ok})
            mark = {True: "OK  ", False: "MISS", None: "    "}[ok]
            print(f"{item['kind'][:6]:<7}{mark} {top1:.3f}  {path_of(hits[0].url):<48} {item['q']}")
            time.sleep(0.7)                                  # stay under free-tier rate limits

    s = summarize(rows)
    hit, total = s["recall"]
    print(f"\nRecall@{K} for answerable questions: {hit}/{total}")
    for kind in ("answerable", "unpublished", "offtopic"):
        if kind in s:
            v = s[kind]
            print(f"{kind:<12} top-1 similarity: min {v['min']:.3f}  median {v['median']:.3f}  max {v['max']:.3f}  (n={v['n']})")

    lowest_good = s["answerable"]["min"]
    print()
    if "offtopic" in s:
        if s["offtopic"]["max"] < lowest_good:
            print(f"Off-topic vs answerable: a threshold between {s['offtopic']['max']:.3f} and {lowest_good:.3f} separates them.")
        else:
            print("Off-topic vs answerable: scores OVERLAP; a threshold alone is not enough.")
    if "unpublished" in s:
        if s["unpublished"]["max"] >= lowest_good:
            print("Unpublished vs answerable: scores OVERLAP, as expected. These need the prompt rules + a facts entry, not a threshold.")
        else:
            print(f"Unpublished vs answerable: separable between {s['unpublished']['max']:.3f} and {lowest_good:.3f}.")
    print("Note: a MISS may mean my expected page is wrong. Read those rows before trusting the number.")


if __name__ == "__main__":
    main()