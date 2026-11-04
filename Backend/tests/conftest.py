"""Runs before any test module is imported.

Tests must never touch a real database or read your real .env credentials, so the
settings get a dummy DATABASE_URL (the engine connects lazily, so nothing connects).
Database tests use their own TEST_DATABASE_URL instead.
"""
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/dummy"
os.environ["GEMINI_API_KEY"] = ""
