"""Entrypoint for Vercel. It exposes the FastAPI app from the project root so that
`from app...` imports resolve. Locally you still run:  uvicorn app.main:app --reload"""
from app.main import app  # noqa: F401
