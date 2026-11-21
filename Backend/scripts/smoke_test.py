"""Post-deploy smoke test: checks a LIVE backend the way a visitor's browser and an attacker would.

    python -m scripts.smoke_test https://your-api.example.com --origin https://www.sharpbuild.io
    python -m scripts.smoke_test https://your-api.example.com --origin https://www.sharpbuild.io --chat --token "$ADMIN_TOKEN"

Without flags it sends no AI questions and creates no leads (it only sends invalid requests, which
are rejected before anything is stored). --chat asks ONE real question (one Gemini call).
--token also checks that no lead notification has given up. Standard library only; exit code 1 if
any check fails.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

EVIL_ORIGIN = "https://evil.example"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def call(method, url, headers=None, body=None, timeout=20):
    """Returns (status, lowercase-header dict, body bytes); HTTP error statuses are returned, not raised."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def run_checks(base: str, origin: str, chat: bool = False, token: str = "", timeout: float = 20) -> list[Check]:
    base = base.rstrip("/")
    checks: list[Check] = []

    def record(name, ok, detail=""):
        checks.append(Check(name, bool(ok), detail))

    def attempt(name, fn):
        try:
            fn()
        except Exception as error:                      # a network problem is a failed check, not a crash
            record(name, False, f"{type(error).__name__}: {error}")

    def health():
        status, headers, body = call("GET", f"{base}/health", timeout=timeout)
        record("health responds ok", status == 200 and b'"ok"' in body, f"status {status}")
        record("responses carry a request id", bool(headers.get("x-request-id")))
        record("nosniff header present", headers.get("x-content-type-options") == "nosniff")
    attempt("health", health)

    def docs():
        statuses = {p: call("GET", f"{base}{p}", timeout=timeout)[0] for p in ("/docs", "/redoc", "/openapi.json")}
        record("API docs are hidden", all(s == 404 for s in statuses.values()), str(statuses))
    attempt("docs", docs)

    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}

    def cors():
        status, headers, _ = call("OPTIONS", f"{base}/chat/stream", {**preflight, "Origin": origin}, timeout=timeout)
        record("CORS allows the website origin", status == 200 and headers.get("access-control-allow-origin") == origin,
               f"status {status}, allow-origin {headers.get('access-control-allow-origin')!r}")
        status, headers, _ = call("OPTIONS", f"{base}/chat/stream", {**preflight, "Origin": EVIL_ORIGIN}, timeout=timeout)
        record("CORS refuses other origins", "access-control-allow-origin" not in headers,
               f"allow-origin {headers.get('access-control-allow-origin')!r}")
    attempt("cors", cors)

    def lead():
        status, headers, _ = call("POST", f"{base}/lead", {"Content-Type": "application/json"}, b"{}", timeout)
        record("lead form rejects an empty submission (422, not 500)", status == 422, f"status {status}")
        record("lead responses are not cached", "no-store" in headers.get("cache-control", ""))
        big = json.dumps({"name": "x" * 40_000}).encode()
        status, _, _ = call("POST", f"{base}/lead", {"Content-Type": "application/json"}, big, timeout)
        record("oversized request body is refused (413)", status == 413, f"status {status}")
    attempt("lead", lead)

    def admin():
        statuses = [call("GET", f"{base}/internal/stats", timeout=timeout)[0],
                    call("POST", f"{base}/internal/retry-lead-notifications", timeout=timeout)[0]]
        record("admin endpoints are closed without a token", all(s in (401, 404) for s in statuses), str(statuses))
    attempt("admin", admin)

    if token:
        def stats():
            status, _, body = call("GET", f"{base}/internal/stats", {"Authorization": f"Bearer {token}"}, timeout=timeout)
            data = json.loads(body) if status == 200 else {}
            gave_up = data.get("notifications", {}).get("gave_up")
            record("admin stats readable with the token", status == 200, f"status {status}")
            record("no lead notification has given up", gave_up == 0, f"gave_up={gave_up}")
        attempt("stats", stats)

    if chat:
        def stream():
            request = urllib.request.Request(
                f"{base}/chat/stream", method="POST", data=json.dumps({"message": "What services does SharpBuild offer?"}).encode(),
                headers={"Content-Type": "application/json", "Origin": origin})
            started, first_delta, final = time.perf_counter(), None, None
            with urllib.request.urlopen(request, timeout=timeout) as response:
                headers = {k.lower(): v for k, v in response.headers.items()}
                record("stream is event-stream", headers.get("content-type", "").startswith("text/event-stream"))
                record("stream is not buffered or transformed",
                       "no-transform" in headers.get("cache-control", "") and headers.get("x-accel-buffering") == "no")
                for raw in response:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:])
                    if event.get("type") == "delta" and first_delta is None:
                        first_delta = time.perf_counter() - started
                    if event.get("type") in ("done", "error"):
                        final = event
                        break
            record("stream ends with a done event", bool(final) and final["type"] == "done", f"final {final and final['type']}")
            record("first words arrive within 15 s", first_delta is not None and first_delta < 15,
                   "no text streamed" if first_delta is None else f"{first_delta:.1f}s")
        attempt("chat", stream)
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url")
    parser.add_argument("--origin", required=True, help="the website origin, e.g. https://www.sharpbuild.io")
    parser.add_argument("--chat", action="store_true", help="ask one real question (uses one Gemini call)")
    parser.add_argument("--token", default="", help="ADMIN_TOKEN, to also check for stuck lead notifications")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)

    checks = run_checks(args.base_url, args.origin, args.chat, args.token, args.timeout)
    for c in checks:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.name}" + (f"  ({c.detail})" if c.detail and not c.ok else ""))
    failed = [c for c in checks if not c.ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
