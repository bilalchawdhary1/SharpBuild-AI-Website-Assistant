import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


def make(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(database_url="postgresql+psycopg://u:p@h/d")


def test_origins_accept_json_list_comma_list_and_single_url(monkeypatch):
    assert make(monkeypatch, ALLOWED_ORIGINS='["https://a.app","https://b.app"]').allowed_origins == ["https://a.app", "https://b.app"]
    assert make(monkeypatch, ALLOWED_ORIGINS="https://a.app, https://b.app ,").allowed_origins == ["https://a.app", "https://b.app"]
    assert make(monkeypatch, ALLOWED_ORIGINS="https://only.app").allowed_origins == ["https://only.app"]


def test_safe_defaults(monkeypatch):
    for var in ("ALLOWED_ORIGINS", "ALLOWED_ORIGIN_REGEX", "TRUST_FORWARDED_FOR"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(database_url="x", _env_file=None)
    assert s.allowed_origins == ["http://localhost:3000"]
    assert s.allowed_origin_regex == "" and s.trust_forwarded_for is False      # nothing trusted by default


def test_trust_flag_reads_from_environment(monkeypatch):
    assert make(monkeypatch, TRUST_FORWARDED_FOR="true").trust_forwarded_for is True


@pytest.fixture
def reloaded_main(monkeypatch):
    """Re-imports app.main with different environment settings, then restores it."""
    import app.main as main_module

    def load(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return importlib.reload(main_module)

    yield load
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(main_module)


def preflight(module, origin):
    r = TestClient(module.app).options("/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    return r.status_code, r.headers.get("access-control-allow-origin")


def test_cors_allows_only_listed_origins_and_optional_preview_regex(reloaded_main):
    main = reloaded_main(ALLOWED_ORIGINS="https://demo.vercel.app",
                         ALLOWED_ORIGIN_REGEX=r"https://demo-git-[a-z0-9-]+\.vercel\.app")
    assert preflight(main, "https://demo.vercel.app") == (200, "https://demo.vercel.app")
    assert preflight(main, "https://demo-git-feature-x.vercel.app") == (200, "https://demo-git-feature-x.vercel.app")
    assert preflight(main, "https://evil.example")[0] == 400
    assert preflight(main, "https://demo-git-x.vercel.app.evil.example")[0] == 400     # regex must match the whole origin
