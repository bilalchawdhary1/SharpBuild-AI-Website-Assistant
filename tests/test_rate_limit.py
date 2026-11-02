from app.core.rate_limit import SlidingWindowLimiter


def test_blocks_after_limit_then_recovers_when_window_passes():
    now = [0.0]
    limiter = SlidingWindowLimiter(limit=2, window=60, clock=lambda: now[0])
    assert limiter.retry_after("a") == 0 and limiter.retry_after("a") == 0
    now[0] = 10
    assert limiter.retry_after("a") == pytest_approx(50)       # oldest hit expires at t=60
    now[0] = 61
    assert limiter.retry_after("a") == 0


def test_visitors_are_counted_separately():
    limiter = SlidingWindowLimiter(limit=1, window=60, clock=lambda: 0.0)
    assert limiter.retry_after("a") == 0
    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0


def test_blocked_requests_do_not_extend_the_block():
    now = [0.0]
    limiter = SlidingWindowLimiter(limit=1, window=60, clock=lambda: now[0])
    limiter.retry_after("a")
    for t in (10, 20, 30, 40):          # hammering while blocked
        now[0] = t
        assert limiter.retry_after("a") > 0
    now[0] = 61
    assert limiter.retry_after("a") == 0


def pytest_approx(value):
    import pytest
    return pytest.approx(value)
