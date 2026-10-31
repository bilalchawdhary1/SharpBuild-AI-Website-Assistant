import math
from types import SimpleNamespace

import pytest

from app.models.chunk import EMBEDDING_DIMS
from app.services.embeddings import make_gemini_embedder, normalize, with_retries


def test_normalize_gives_unit_length_and_handles_zero():
    v = normalize([3.0, 4.0])
    assert v == pytest.approx([0.6, 0.8])
    assert normalize([0.0, 0.0]) == [0.0, 0.0]
    assert math.isclose(math.sqrt(sum(x * x for x in normalize([1, 2, 3]))), 1.0)


class FakeModels:
    def __init__(self, n_returned=None):
        self.calls, self.n_returned = [], n_returned

    def embed_content(self, *, model, contents, config):
        self.calls.append((model, contents, config))
        n = len(contents) if self.n_returned is None else self.n_returned
        return SimpleNamespace(embeddings=[
            SimpleNamespace(values=[3.0, 4.0] + [0.0] * (EMBEDDING_DIMS - 2)) for _ in range(n)])


def test_gemini_embedder_requests_right_config_and_normalizes():
    client = SimpleNamespace(models=FakeModels())
    embed = make_gemini_embedder("key", "gemini-embedding-001", "RETRIEVAL_DOCUMENT", client=client)
    vectors = embed(["a", "b"])
    model, contents, config = client.models.calls[0]
    assert model == "gemini-embedding-001" and contents == ["a", "b"]
    assert config.output_dimensionality == EMBEDDING_DIMS and config.task_type == "RETRIEVAL_DOCUMENT"
    assert len(vectors) == 2 and len(vectors[0]) == EMBEDDING_DIMS
    assert vectors[0][0] == pytest.approx(0.6)


def test_gemini_embedder_rejects_wrong_number_of_embeddings():
    client = SimpleNamespace(models=FakeModels(n_returned=1))
    embed = make_gemini_embedder("key", "m", "RETRIEVAL_QUERY", client=client)
    with pytest.raises(RuntimeError):
        embed(["a", "b"])


class ApiError(Exception):
    def __init__(self, code):
        self.code = code


def test_retries_on_rate_limit_then_succeeds():
    attempts, waits = [], []

    def flaky(texts):
        attempts.append(1)
        if len(attempts) < 3:
            raise ApiError(429)
        return [[1.0]]

    assert with_retries(flaky, sleep=waits.append)(["x"]) == [[1.0]]
    assert len(attempts) == 3 and waits == [5.0, 10.0]


def test_no_retry_on_bad_request_or_after_max_attempts():
    calls = []

    def bad_key(texts):
        calls.append(1)
        raise ApiError(400)

    with pytest.raises(ApiError):
        with_retries(bad_key, sleep=lambda s: None)(["x"])
    assert len(calls) == 1

    def always_busy(texts):
        raise ApiError(503)

    with pytest.raises(ApiError):
        with_retries(always_busy, attempts=3, sleep=lambda s: None)(["x"])