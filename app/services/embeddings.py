"""The ONE place that turns text into vectors.

Used by ingestion (documents) and by the chat API (questions). Both sides must
use the same model, dimensions and normalization, or similarity scores are meaningless.
"""
import math
import time
from typing import Callable

from app.models.chunk import EMBEDDING_DIMS

EmbedFn = Callable[[list[str]], list[list[float]]]
RETRYABLE_CODES = {429, 500, 503}        # rate limit / temporary server trouble


def normalize(vec: list[float]) -> list[float]:
    """Scale a vector to length 1. Google only pre-normalizes the 3072-dim output,
    and we request 1536, so we do it ourselves."""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def make_gemini_embedder(api_key: str, model: str, task_type: str, client=None) -> EmbedFn:
    """task_type: "RETRIEVAL_DOCUMENT" for site content, "RETRIEVAL_QUERY" for questions.
    Google trains the model to place the two kinds of text so they match each other."""
    from google import genai
    from google.genai import types

    client = client or genai.Client(api_key=api_key)
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMS)

    def embed(texts: list[str]) -> list[list[float]]:
        result = client.models.embed_content(model=model, contents=texts, config=config)
        vectors = [normalize(list(e.values)) for e in result.embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError(f"expected {len(texts)} embeddings, got {len(vectors)}")
        return vectors

    return embed


def with_retries(fn: EmbedFn, attempts: int = 5, base_delay: float = 5.0,
                 sleep: Callable[[float], None] = time.sleep) -> EmbedFn:
    """Retry on rate-limit/temporary errors with growing waits (5s, 10s, 20s...).
    Any other error (bad key, bad request) is raised immediately."""
    def wrapped(texts: list[str]) -> list[list[float]]:
        for attempt in range(attempts):
            try:
                return fn(texts)
            except Exception as e:
                retryable = getattr(e, "code", None) in RETRYABLE_CODES
                if not retryable or attempt == attempts - 1:
                    raise
                wait = min(base_delay * 2 ** attempt, 60)
                print(f"  API busy (code {e.code}); retrying in {wait:.0f}s")
                sleep(wait)
    return wrapped