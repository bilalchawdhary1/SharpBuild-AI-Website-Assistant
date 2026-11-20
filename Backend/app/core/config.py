from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # Browser origins allowed to call the API. In .env or Vercel use either a JSON list
    # ["https://a.app","https://b.app"] or simply: https://a.app,https://b.app
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Optional regex for preview deployments whose URL changes, e.g. https://myapp-.*\.vercel\.app
    allowed_origin_regex: str = ""

    # Answer quality. min_similarity comes from `python -m scripts.eval_retrieval`:
    # off-topic questions scored <= 0.536, real matches >= 0.650. Re-measure if the
    # embedding model or its settings change: the scale is model-specific.
    min_similarity: float = 0.58
    retrieval_k: int = 4

    # Abuse and quota protection (requests per minute). Check your real Gemini
    # free-tier limits in Google AI Studio and keep the global limit below them.
    rate_limit_per_minute: int = 6
    global_rate_limit_per_minute: int = 10
    # Lead form submissions per visitor per minute. Separate from the chat limits so leads
    # never use up the shared Gemini quota (and vice versa).
    lead_rate_limit_per_minute: int = 3
    lead_global_rate_limit_per_minute: int = 30    # all visitors together: caps junk leads if one IP is rotated
    admin_rate_limit_per_minute: int = 30          # guessing the admin token is throttled per visitor
    # "memory": counters live in each server process (fine for ONE instance). "database": counters
    # live in Postgres so every serverless instance shares them (use this on Vercel). If the
    # database counter fails, the in-memory limiter is used instead (it never blocks the chat).
    rate_limit_backend: Literal["memory", "database"] = "memory"

    # Logs: "text" is readable; "json" writes one JSON object per line (for log tools / drains).
    log_format: Literal["text", "json"] = "text"
    log_level: str = "INFO"

    # Requests larger than this are rejected with 413 before they are parsed.
    max_body_bytes: int = 32768
    # Set ENABLE_DOCS=false in production to hide /docs, /redoc and /openapi.json.
    enable_docs: bool = True

    # Where saved leads are sent. All optional: with nothing set, leads stay in the database.
    # Webhook (CRM, Zapier, Make...): needs an https:// URL AND a secret used to sign each request.
    lead_webhook_url: str = ""
    lead_webhook_secret: str = ""
    # Email alert: SMTP host plus sender and recipient. Port 587 uses STARTTLS, 465 uses SSL.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    lead_email_from: str = ""
    lead_email_to: str = ""
    notify_timeout_seconds: float = 4.0
    # Protects /internal/retry-lead-notifications. Empty = the endpoint does not exist (404).
    admin_token: str = ""

    # Read the visitor IP from X-Forwarded-For. ONLY enable behind a proxy that overwrites the
    # header (Vercel does). Anywhere else a visitor could forge it to dodge the rate limit.
    trust_forwarded_for: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.generation_fallback_models.split(",") if m.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
