from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SharpBuild AI Website Assistant"
    database_url: str                      # required: app won't start without it
    gemini_api_key: str = ""               # free key from https://aistudio.google.com/apikey
    embedding_model: str = "gemini-embedding-001"
    # Verified working for a new free-tier key on 2026-11-02 (try_models.py). Google retires
    # models for new accounts without warning, so re-run scripts.try_models if answers fail.
    generation_model: str = "gemini-3.5-flash-lite"
    # Backups tried in order when the main model is overloaded (503), rate-limited (429),
    # retired (404) or too slow. Comma-separated. Avoid "-latest" aliases: they change silently.
    generation_fallback_models: str = "gemini-3.6-flash"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Answer quality. min_similarity comes from `python -m scripts.eval_retrieval`:
    # off-topic questions scored <= 0.536, real matches >= 0.650. Re-measure if the
    # embedding model or its settings change: the scale is model-specific.
    min_similarity: float = 0.58
    retrieval_k: int = 4

    # Abuse and quota protection (requests per minute). Check your real Gemini
    # free-tier limits in Google AI Studio and keep the global limit below them.
    rate_limit_per_minute: int = 6
    global_rate_limit_per_minute: int = 10

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.generation_fallback_models.split(",") if m.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
