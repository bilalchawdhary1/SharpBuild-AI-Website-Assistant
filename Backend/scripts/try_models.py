"""Find which Gemini model really works for YOUR key by making one tiny real call to each.

Why: a model can show up in list_models and still fail with
"404: no longer available to new users". Only a real call proves it works.

Usage:  python -m scripts.try_models                       (tests every stable Flash text model)
        python -m scripts.try_models gemini-3.8-flash      (tests only the names you give)
"""
import sys
import time

EXCLUDE = ("image", "tts", "preview", "exp", "live", "audio", "robotics", "computer")
# Named in Google's own 404 message as the replacement for gemini-2.5-flash.
EXTRA_CANDIDATES = ["gemini-3.8-flash"]


def candidate_models(models) -> list[str]:
    """Stable, text-generating Flash models from the API's model list."""
    names = set()
    for m in models:
        actions = getattr(m, "supported_actions", None) or []
        name = (getattr(m, "name", "") or "").removeprefix("models/")
        low = name.lower()
        if "generateContent" in actions and "flash" in low and not any(w in low for w in EXCLUDE):
            names.add(name)
    return sorted(names)


def pick_best(working: list[str]) -> str | None:
    """Prefer a Lite model (free quotas are usually higher), then alphabetical."""
    return sorted(working, key=lambda n: ("lite" not in n.lower(), n))[0] if working else None


def short_error(e: Exception) -> str:
    code = getattr(e, "code", "?")
    message = str(getattr(e, "message", None) or e).replace("\n", " ")
    return f"{code}: {message[:110]}"


def main() -> None:
    from google import genai
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is empty. Put your key in .env first.")
    client = genai.Client(api_key=settings.gemini_api_key)

    names = sys.argv[1:] or sorted(set(candidate_models(client.models.list())) | set(EXTRA_CANDIDATES))
    print(f"Testing {len(names)} models with one tiny request each...\n")
    working = []
    for name in names:
        started = time.perf_counter()
        try:
            reply = client.models.generate_content(model=name, contents="Reply with the single word: ready")
            ms = int((time.perf_counter() - started) * 1000)
            print(f"OK      {name:<34}{ms:>6} ms   replied: {(reply.text or '').strip()[:30]!r}")
            working.append(name)
        except Exception as e:
            print(f"FAILED  {name:<34}{short_error(e)}")
        time.sleep(2)                       # be gentle with free-tier rate limits

    best = pick_best(working)
    print()
    if best:
        print(f"Put this line in your .env file, then restart the server:\n\n    GENERATION_MODEL={best}\n")
    else:
        print("No model worked. Check the errors above (key problem? quota? region?).")


if __name__ == "__main__":
    main()
