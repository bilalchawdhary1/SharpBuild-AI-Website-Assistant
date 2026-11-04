"""List the Gemini models your API key can use to write answers.

Usage:  python -m scripts.list_models
Pick a STABLE Flash-Lite/Flash model (not "preview"/"exp"): previews get retired.
Check its free-tier limits in Google AI Studio before relying on it.
"""


def usable_chat_models(models) -> list[tuple[str, bool]]:
    """Return [(model_id, is_preview)] for models that can generate text."""
    out = []
    for m in models:
        actions = getattr(m, "supported_actions", None) or []
        name = (getattr(m, "name", "") or "").removeprefix("models/")
        if "generateContent" in actions and "flash" in name.lower():
            out.append((name, any(w in name.lower() for w in ("preview", "exp"))))
    return sorted(out)


def main() -> None:
    from google import genai
    from app.core.config import get_settings

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    found = usable_chat_models(client.models.list())
    if not found:
        print("No Flash models found for this key. Check GEMINI_API_KEY.")
    for name, preview in found:
        print(f"{name}{'   (preview/experimental - avoid)' if preview else ''}")


if __name__ == "__main__":
    main()
