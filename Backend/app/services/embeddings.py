"""The ONE place that turns text into vectors.

Used by ingestion (documents) and by the chat API (questions). Both sides must
use the same model, dimensions and normalization, or similarity scores are meaningless.
"""
import math
import hashlib
import re
import threading
import time
from collections import OrderedDict
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


def make_embedding_cache(fn: EmbedFn, max_entries: int = 256) -> EmbedFn:
    """Cache successful embeddings by a privacy-safe key, for repeated chat questions."""
    cache: OrderedDict[str, list[float]] = OrderedDict()
    lock = threading.Lock()

    def key(text: str) -> str:
        canonical = re.sub(r"\s+", " ", text.strip()).casefold()
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def embed(texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        miss_texts: list[str] = []
        miss_indexes: list[int] = []

        with lock:
            for index, text in enumerate(texts):
                cache_key = key(text)
                if cache_key in cache:
                    results[index] = cache.pop(cache_key)
                    cache[cache_key] = results[index]
                else:
                    miss_indexes.append(index)
                    miss_texts.append(text)

        if miss_texts:
            misses = fn(miss_texts)
            if len(misses) != len(miss_texts):
                raise RuntimeError(
                    f"expected {len(miss_texts)} embeddings, got {len(misses)}"
                )
            with lock:
                for index, text, vector in zip(miss_indexes, miss_texts, misses):
                    cache_key = key(text)
                    results[index] = vector
                    cache[cache_key] = vector
                    cache.move_to_end(cache_key)
                    while len(cache) > max_entries:
                        cache.popitem(last=False)

        return [vector for vector in results if vector is not None]

    return embed


def with_retries(fn: Callable, attempts: int = 5, base_delay: float = 5.0,
                 sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Retry on rate-limit/temporary errors with growing waits (5s, 10s, 20s...).
    Works for any function (embedding or answering). Any other error (bad key,
    bad request) is raised immediately."""
    def wrapped(*args, **kwargs):
        for attempt in range(attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                retryable = getattr(e, "code", None) in RETRYABLE_CODES
                if not retryable or attempt == attempts - 1:
                    raise
                wait = min(base_delay * 2 ** attempt, 60)
                print(f"  API busy (code {e.code}); retrying in {wait:.0f}s")
                sleep(wait)
    return wrapped
