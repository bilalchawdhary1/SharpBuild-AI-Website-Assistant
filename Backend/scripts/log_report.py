"""Summarise exported server logs: answer outcomes, latency, errors and lead delivery.

    python -m scripts.log_report app.log [more.log ...]
    python -m scripts.log_report < exported_logs.txt

Reads both LOG_FORMAT=text and LOG_FORMAT=json lines. Standard library only; reads the files you give it
and never contacts a server. The logs contain no question text, so neither does the report.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from math import ceil

CHAT = re.compile(
    r"chat outcome=(\w+)(?: top_similarity=([\d.]+))?(?: question_chars=\d+)?"
    r"(?: retrieve_ms=(\d+) answer_ms=(\d+) ms=(\d+))?(?: first_token_ms=(\d+))?"
)
INTENT = re.compile(r"chat intent=(\w+)")
REQUEST = re.compile(r"request method=(\w+) path=(\S+) status=(\d+) ms=(\d+)")
MODEL_FAIL = re.compile(r"model (\S+) failed after \d+ ms")
NOTIFY = re.compile(r"lead notify id=\d+ (.+)$")
UNANSWERED = {"model_no_answer", "below_threshold"}      # the assistant had no grounded answer


def percentile(values: list[int], pct: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(pct / 100 * len(ordered)) - 1)]


def message_of(line: str) -> str:
    line = line.strip()
    if line.startswith("{"):
        try:
            return str(json.loads(line).get("message", line))
        except ValueError:
            pass
    return line


def summarize(lines) -> dict:
    outcomes, intents, statuses, models = Counter(), Counter(), Counter(), Counter()
    latency, first_token = [], []
    path_ms: dict[str, list[int]] = defaultdict(list)
    leads = Counter()
    for raw in lines:
        text = message_of(raw)
        if m := CHAT.search(text):
            outcomes[m.group(1)] += 1
            if m.group(1) == "answered" and m.group(5):
                latency.append(int(m.group(5)))
            if m.group(6):
                first_token.append(int(m.group(6)))
        elif m := INTENT.search(text):
            intents[m.group(1)] += 1
        elif m := REQUEST.search(text):
            statuses[f"{m.group(3)[0]}xx"] += 1
            if m.group(3) == "429":
                statuses["429"] += 1
            path_ms[f"{m.group(1)} {m.group(2)}"].append(int(m.group(4)))
        elif m := MODEL_FAIL.search(text):
            models[m.group(1)] += 1
        elif "lead saved" in text:
            leads["saved"] += 1
        elif "lead duplicate ignored" in text:
            leads["duplicate"] += 1
        elif "lead honeypot hit" in text:
            leads["honeypot"] += 1
        elif m := NOTIFY.search(text):
            leads["notify_failed" if "failed" in m.group(1) else "notify_ok"] += 1
    chats = sum(outcomes.values())
    return {
        "chats": chats,
        "outcomes": dict(outcomes),
        "unanswered_rate": sum(outcomes[o] for o in UNANSWERED) / chats if chats else 0.0,
        "error_rate": outcomes["error"] / chats if chats else 0.0,
        "intents": dict(intents),
        "latency_ms": {"p50": percentile(latency, 50), "p95": percentile(latency, 95)},
        "first_token_ms": {"p50": percentile(first_token, 50), "p95": percentile(first_token, 95)},
        "http": dict(statuses),
        "slowest_endpoints": sorted(
            ({"endpoint": k, "count": len(v), "p95_ms": percentile(v, 95)} for k, v in path_ms.items()),
            key=lambda row: row["p95_ms"], reverse=True)[:5],
        "model_failures": dict(models),
        "leads": dict(leads),
    }


def render(s: dict) -> str:
    pct = lambda x: f"{x:.1%}"
    out = [f"Chat requests: {s['chats']}"]
    for name, count in sorted(s["outcomes"].items(), key=lambda kv: -kv[1]):
        out.append(f"  {name:<16}{count:>6}  {pct(count / s['chats'])}")
    out += [f"No grounded answer: {pct(s['unanswered_rate'])}   Errors: {pct(s['error_rate'])}",
            f"Answer time ms   p50={s['latency_ms']['p50']}  p95={s['latency_ms']['p95']}",
            f"First token ms   p50={s['first_token_ms']['p50']}  p95={s['first_token_ms']['p95']}",
            f"HTTP responses   {s['http'] or '-'}",
            f"Intents          {s['intents'] or '-'}",
            f"Model failures   {s['model_failures'] or '-'}",
            f"Leads            {s['leads'] or '-'}"]
    for row in s["slowest_endpoints"]:
        out.append(f"  slowest: {row['endpoint']:<32} n={row['count']} p95={row['p95_ms']} ms")
    return "\n".join(out)


def main(argv: list[str]) -> None:
    if argv:
        lines = (line for path in argv for line in open(path, encoding="utf-8", errors="replace"))
    else:
        lines = sys.stdin
    print(render(summarize(lines)))


if __name__ == "__main__":
    main(sys.argv[1:])
