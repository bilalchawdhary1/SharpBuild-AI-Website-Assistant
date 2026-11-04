import os
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import app.main
import index
from app.db import session

ROOT = Path(__file__).resolve().parent.parent


def lines(name):
    return [l.strip() for l in (ROOT / name).read_text(encoding="utf-8").splitlines()]


def test_vercel_entrypoint_exposes_the_same_app():
    assert index.app is app.main.app


def test_python_version_is_pinned_to_a_vercel_supported_version():
    assert (ROOT / ".python-version").read_text().strip() in {"3.12", "3.13", "3.14"}


def test_requirements_are_plain_utf8_and_pinned():
    raw = (ROOT / "requirements.txt").read_bytes()
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")) and b"\x00" not in raw   # Windows redirects create UTF-16
    packages = [l for l in lines("requirements.txt") if l and not l.startswith("#")]
    assert packages and all("==" in l for l in packages)


def test_production_requirements_exclude_dev_tools_and_dev_file_extends_them():
    prod = " ".join(lines("requirements.txt")).lower()
    for dev_only in ("pytest", "uvicorn", "beautifulsoup4", "httpx"):
        assert dev_only not in prod
    assert "-r requirements.txt" in lines("requirements-dev.txt")


def test_every_third_party_import_in_app_is_covered_by_production_requirements():
    provided = {"fastapi": "fastapi", "pydantic": "fastapi", "pydantic_settings": "pydantic-settings",
                "sqlalchemy": "sqlalchemy", "pgvector": "pgvector", "google": "google-genai",
                "psycopg": "psycopg", "starlette": "fastapi"}
    prod = " ".join(lines("requirements.txt")).lower()
    imported = set()
    for path in (ROOT / "app").rglob("*.py"):
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", path.read_text(encoding="utf-8"), re.M):
            imported.add(m.group(1))
    third_party = {m for m in imported if m not in sys.stdlib_module_names and m not in {"app", "index"}}
    assert third_party <= set(provided), f"unmapped imports: {third_party - set(provided)}"
    for module in third_party:
        assert provided[module] in prod, f"{module} needs {provided[module]} in requirements.txt"


def test_app_never_imports_code_that_the_deploy_bundle_excludes():
    for path in (ROOT / "app").rglob("*.py"):
        assert not re.search(r"^\s*(?:from|import)\s+(?:ingestion|scripts|tests)\b", path.read_text(encoding="utf-8"), re.M), path


def test_vercelignore_hides_secrets_data_and_dev_files_but_keeps_the_app():
    rules = set(lines(".vercelignore"))
    for needed in (".env", ".env.*", ".venv/", "tests/", "data/", "ingestion/", "scripts/"):
        assert needed in rules, needed
    for must_ship in ("app/", "app", "requirements.txt", "index.py"):
        assert must_ship not in rules


def test_database_pool_is_small_for_serverless():
    assert session.engine.pool.size() == 3 and session.engine.pool._max_overflow == 2


URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to a test database")
def test_no_server_side_prepared_statements_with_the_production_connect_args():
    engine = create_engine(URL, connect_args=session.CONNECT_ARGS)
    with engine.connect() as conn:
        for i in range(12):                                 # psycopg would normally prepare after 5 repeats
            conn.execute(text("SELECT :n"), {"n": i})
        assert conn.execute(text("SELECT count(*) FROM pg_prepared_statements")).scalar() == 0
