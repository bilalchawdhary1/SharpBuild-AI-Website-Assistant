"""Answer-level evaluation of the real pipeline: your database, embeddings and Gemini.

    python -m scripts.eval_answers --dry-run                 # check the golden file only (no network)
    python -m scripts.eval_answers                           # run every case
    python -m scripts.eval_answers --only inj-key,oos-code   # run some cases
    python -m scripts.eval_answers --min-pass 0.9 --json report.json

It complements scripts.eval_retrieval (which scores retrieval alone): this checks what a visitor
actually sees: grounded answers with sources, fallbacks for out-of-scope questions, handoff,
resistance to prompt injection, no leaked instructions or keys, no invented prices.

Exit code: 0 good, 1 a safety failure or pass rate below --min-pass, 2 could not evaluate (e.g. no
API key, or most calls failed). It calls Gemini once per case plus embeddings; the default pause
keeps it inside the free-tier rate limit.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from scripts.eval_scoring import decide_exit, evaluate, load_cases, render, summarize

DEFAULT_CASES = Path(__file__).resolve().parent.parent / "evals" / "golden_answers.jsonl"


def run_live(cases: list[dict], delay: float):
    from app.api.routes.chat import _answerer, _embedder
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.schemas.chat import ChatTurn
    from app.services.chat_service import answer_question

    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set: cannot run the live evaluation (use --dry-run to check the file).")
    embed = _embedder(settings.gemini_api_key, settings.embedding_model)
    answer = _answerer(settings.gemini_api_key, settings.generation_model, tuple(settings.fallback_models))

    results = []
    with SessionLocal() as db:
        for number, case in enumerate(cases):
            if number:
                time.sleep(delay)
            history = [ChatTurn(role=t["role"], text=t["text"]) for t in case.get("history", [])]
            started = time.perf_counter()
            response = answer_question(db, case["question"], embed, answer,
                                       min_similarity=settings.min_similarity, k=settings.retrieval_k, history=history)
            ms = int((time.perf_counter() - started) * 1000)
            result = evaluate(case, response.answer, response.fallback, response.intent,
                              [s.url for s in response.sources], ms)
            results.append(result)
            print(f"{result.status.upper():<5} {case['id']:<28} {ms:>6} ms", flush=True)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--min-pass", type=float, default=0.9, help="required pass rate (default 0.9)")
    parser.add_argument("--delay", type=float, default=6.5, help="seconds between cases (free-tier rate limit)")
    parser.add_argument("--dry-run", action="store_true", help="validate the golden file; call nothing")
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.cases.read_text(encoding="utf-8").splitlines())
    except (OSError, ValueError) as error:
        print(f"golden file problem: {error}", file=sys.stderr)
        return 2
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {c["id"] for c in cases}
        if unknown:
            print(f"unknown case ids: {sorted(unknown)}", file=sys.stderr)
            return 2
        cases = [c for c in cases if c["id"] in wanted]

    if args.dry_run:
        by_category = Counter(c["category"] for c in cases)
        print(f"{len(cases)} valid cases: " + ", ".join(f"{k}={v}" for k, v in sorted(by_category.items())))
        return 0

    results = run_live(cases, args.delay)
    summary = summarize(results)
    print("\n" + render(summary, results))
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "results": [
            {"id": r.id, "category": r.category, "status": r.status, "behavior": r.behavior, "ms": r.ms,
             "failures": [{"kind": f.kind, "message": f.message} for f in r.failures]} for r in results]},
            indent=2), encoding="utf-8")
    return decide_exit(summary, args.min_pass)


if __name__ == "__main__":
    sys.exit(main())
