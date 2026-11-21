"""Production-readiness checks for the backend settings (standard library only).

Used two ways: `python -m scripts.preflight --production` before a deploy (exit code 1 on errors),
and at startup in production, where findings are only logged: a misconfiguration should be loud,
but it must never stop the site from answering visitors.

  error   = it will break something or expose something
  warning = it works but is weaker than it should be
"""
import re
from dataclasses import dataclass

MIN_ADMIN_TOKEN_CHARS = 32
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")


@dataclass(frozen=True)
class Finding:
    level: str          # "error" | "warning"
    code: str
    message: str


def is_production(env) -> bool:
    return env.get("VERCEL_ENV") == "production" or str(env.get("ENVIRONMENT", "")).lower() in ("production", "prod")


def on_vercel(env) -> bool:
    return bool(env.get("VERCEL"))


def check(settings, env, production: bool | None = None) -> list[Finding]:
    production = is_production(env) if production is None else production
    found: list[Finding] = []
    error = lambda code, msg: found.append(Finding("error", code, msg))
    warn = lambda code, msg: found.append(Finding("warning", code, msg))

    # --- always: things that silently break features -------------------------------------------------
    if not settings.gemini_api_key:
        error("gemini-key", "GEMINI_API_KEY is empty: every answer will fail.")
    if settings.lead_webhook_url and not (settings.lead_webhook_url.startswith("https://") and settings.lead_webhook_secret):
        error("webhook", "LEAD_WEBHOOK_URL needs an https:// URL and LEAD_WEBHOOK_SECRET, otherwise it is silently skipped.")
    if settings.smtp_host and not (settings.lead_email_from and settings.lead_email_to):
        error("smtp", "SMTP_HOST is set but LEAD_EMAIL_FROM / LEAD_EMAIL_TO are missing: no email will be sent.")
    if settings.allowed_origin_regex:
        try:
            pattern = re.compile(settings.allowed_origin_regex)
            for hostile in ("https://evil.example", "http://localhost:3000", "https://evil.example/.vercel.app"):
                if pattern.fullmatch(hostile):
                    error("origin-regex", f"ALLOWED_ORIGIN_REGEX matches {hostile}: it is too broad.")
                    break
        except re.error as problem:
            error("origin-regex", f"ALLOWED_ORIGIN_REGEX is not a valid regex ({problem}).")
    if settings.admin_token and len(settings.admin_token) < MIN_ADMIN_TOKEN_CHARS:
        warn("admin-token", f"ADMIN_TOKEN is shorter than {MIN_ADMIN_TOKEN_CHARS} characters: the admin endpoints are disabled.")
    if not settings.generation_fallback_models.strip():
        warn("fallback-model", "GENERATION_FALLBACK_MODELS is empty: if the main model is overloaded, answers fail.")
    if not 0.4 <= settings.min_similarity <= 0.8:
        warn("min-similarity", f"MIN_SIMILARITY={settings.min_similarity} is unusual: re-measure with scripts.eval_retrieval.")

    if not production:
        return found

    # --- production only -------------------------------------------------------------------------------
    origins = list(settings.allowed_origins)
    if not origins and not settings.allowed_origin_regex:
        error("origins", "ALLOWED_ORIGINS is empty: browsers will be blocked.")
    development_default = origins == ["http://localhost:3000"] and not settings.allowed_origin_regex
    if development_default:
        error("origins", "ALLOWED_ORIGINS still has the development default (http://localhost:3000).")
    for origin in ([] if development_default else origins):
        if origin == "*":
            error("origins", "ALLOWED_ORIGINS contains '*': any website could use your API.")
        elif not origin.startswith("https://"):
            error("origins", f"ALLOWED_ORIGINS contains {origin}, which is not https.")
    db = settings.database_url
    if any(host in db for host in LOCAL_HOSTS):
        error("database", "DATABASE_URL points at a local database.")
    elif "sslmode=" not in db:
        warn("database-ssl", "DATABASE_URL has no sslmode: add ?sslmode=require so the connection is encrypted.")
    if on_vercel(env) and not settings.trust_forwarded_for:
        error("forwarded-for", "On Vercel, TRUST_FORWARDED_FOR must be true. Otherwise every visitor looks like "
                               "the same IP and the rate limits throttle everyone together.")
    if settings.trust_forwarded_for and not on_vercel(env):
        warn("forwarded-for", "TRUST_FORWARDED_FOR is on: make sure your proxy overwrites X-Forwarded-For, "
                              "or visitors can fake their IP to dodge the rate limit.")
    if settings.rate_limit_backend == "memory":
        warn("rate-limit", "RATE_LIMIT_BACKEND=memory: each serverless instance counts separately. Use 'database'.")
    if settings.enable_docs:
        warn("docs", "ENABLE_DOCS is true: /docs and /openapi.json are public. Set ENABLE_DOCS=false.")
    if settings.log_format != "json":
        warn("log-format", "LOG_FORMAT is not json: log tools can't parse the lines. Set LOG_FORMAT=json.")
    if not settings.admin_token:
        warn("admin-token", "ADMIN_TOKEN is empty: failed lead notifications are never retried and /internal/stats is off.")
    if not (settings.lead_webhook_url or settings.smtp_host):
        warn("lead-channel", "No lead notification channel (webhook or SMTP): leads only sit in the database.")
    return found
