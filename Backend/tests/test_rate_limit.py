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


# ---------- visitor IP (matters on Vercel, where every request comes from Vercel's network) ----------
from types import SimpleNamespace  # noqa: E402

from app.core.rate_limit import visitor_ip  # noqa: E402


def fake_request(forwarded=None, host="10.0.0.9"):
    headers = {} if forwarded is None else {"x-forwarded-for": forwarded}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_forwarded_header_is_ignored_unless_explicitly_trusted():
    assert visitor_ip(fake_request("203.0.113.7"), trust_forwarded_for=False) == "10.0.0.9"   # forgeable, so ignored


def test_trusted_forwarded_header_gives_the_first_address():
    assert visitor_ip(fake_request("203.0.113.7"), True) == "203.0.113.7"
    assert visitor_ip(fake_request(" 203.0.113.7 , 10.0.0.1"), True) == "203.0.113.7"


def test_missing_or_empty_forwarded_header_falls_back_to_the_socket_address():
    assert visitor_ip(fake_request(None), True) == "10.0.0.9"
    assert visitor_ip(fake_request("  "), True) == "10.0.0.9"
    assert visitor_ip(SimpleNamespace(headers={}, client=None), True) == "unknown"
