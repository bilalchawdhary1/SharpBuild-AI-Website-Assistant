from types import SimpleNamespace

from scripts.try_models import candidate_models, pick_best, short_error


def model(name, actions=("generateContent",)):
    return SimpleNamespace(name=f"models/{name}", supported_actions=list(actions))


def test_candidates_are_stable_text_flash_models_only():
    models = [model("gemini-3.1-flash-lite"), model("gemini-2.5-flash"), model("gemini-3-flash-preview"),
              model("gemini-3.1-flash-image"), model("gemini-3.1-flash-tts-preview"),
              model("gemini-3.1-pro"), model("gemini-embedding-001", ["embedContent"]),
              model("gemini-2.5-flash")]                      # duplicate
    assert candidate_models(models) == ["gemini-2.5-flash", "gemini-3.1-flash-lite"]


def test_pick_best_prefers_lite_then_alphabetical():
    assert pick_best(["gemini-3.8-flash", "gemini-3.1-flash-lite"]) == "gemini-3.1-flash-lite"
    assert pick_best(["gemini-3.8-flash", "gemini-2.5-flash"]) == "gemini-2.5-flash"
    assert pick_best([]) is None


def test_short_error_is_readable_and_bounded():
    class Err(Exception):
        code = 404
        message = "This model is no longer available\nto new users. " + "x" * 300
    out = short_error(Err())
    assert out.startswith("404: This model is no longer available to new users.") and len(out) < 130
