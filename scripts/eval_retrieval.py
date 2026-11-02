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


def found_fact(hits, topics: list[str], k: int = K) -> bool:
    return any(h.page_type == "facts" and h.section in topics for h in hits[:k])


def check(hits, item: dict):
    """True/False when the item names an expected page or fact; None when it doesn't."""
    paths, topics = item.get("expect", []), item.get("expect_fact", [])
    if not paths and not topics:
        return None
    return found_expected(hits, paths) or found_fact(hits, topics)


def summarize(rows: list[dict]) -> dict:
    """rows: {"kind", "top1", "ok"}. Returns per-kind stats."""
    out = {}
    for kind in ("answerable", "unpublished", "offtopic"):
        sims = [r["top1"] for r in rows if r["kind"] == kind]
        if not sims:
            continue
        out[kind] = {"n": len(sims), "min": min(sims), "median": statistics.median(sims), "max": max(sims)}
    ans = [r for r in rows if r["kind"] == "answerable" and r["ok"] is not None]
    out["recall"] = (sum(r["ok"] for r in ans), len(ans))
    unp = [r for r in rows if r["kind"] == "unpublished" and r["ok"] is not None]
    out["fact_recall"] = (sum(r["ok"] for r in unp), len(unp))
    return out


def threshold_report(rows: list[dict], threshold: float) -> dict:
    """For each kind: (questions that would hit the 'not found' fallback, total)."""
    out = {}
    for kind in ("answerable", "unpublished", "offtopic"):
        sims = [r["top1"] for r in rows if r["kind"] == kind]
        if sims:
            out[kind] = (sum(sim < threshold for sim in sims), len(sims))
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
            ok = check(hits, item)
            rows.append({"kind": item["kind"], "top1": top1, "ok": ok})
            mark = {True: "OK  ", False: "MISS", None: "    "}[ok]
            top = "[fact] " + hits[0].section if hits[0].page_type == "facts" else path_of(hits[0].url)
            print(f"{item['kind'][:6]:<7}{mark} {top1:.3f}  {top:<48} {item['q']}")
            time.sleep(0.7)                                  # stay under free-tier rate limits

    s = summarize(rows)
    hit, total = s["recall"]
    print(f"\nRecall@{K} for answerable questions: {hit}/{total}")
    fh, ft = s["fact_recall"]
    print(f"Recall@{K} of the right 'not published' fact for unpublished questions: {fh}/{ft}")
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
    t = settings.min_similarity
    rep = threshold_report(rows, t)
    print(f"\nAt min_similarity={t} the chat would answer 'not found' (no LLM call) for:")
    wants = {"answerable": "want 0", "unpublished": "fine: answered by a fact or falls back", "offtopic": "want all"}
    for kind, (n, total) in rep.items():
        print(f"  {kind:<12} {n}/{total}   ({wants[kind]})")
    print("Note: a MISS may mean my expected page is wrong. Read those rows before trusting the number.")


if __name__ == "__main__":
    main()
