"""In-memory sliding-window rate limiting (no extra dependency).

Limits: one visitor (IP) and the whole service together, because the free Gemini
quota is shared by everyone. In-memory means each server process counts on its
own and counters reset on restart: fine for one small instance; use Redis if you
ever run several.
"""
import hashlib
import logging
import math
import random
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal

logger = logging.getLogger("sharpbuild.ratelimit")


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> float:
        """0.0 if the request is allowed (and counted); else seconds until a slot frees up."""
        now = self.clock()
        with self._lock:
            if len(self._hits) > 5000:                       # keep memory bounded
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
                    del self._hits[k]
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return self.window - (now - q[0])
            q.append(now)
            return 0.0


@lru_cache
def _limiters(per_visitor: int, overall: int) -> tuple[SlidingWindowLimiter, SlidingWindowLimiter]:
    return SlidingWindowLimiter(per_visitor), SlidingWindowLimiter(overall)


@lru_cache
def _lead_limiter(per_visitor: int, overall: int = 30) -> tuple[SlidingWindowLimiter, SlidingWindowLimiter]:
    return SlidingWindowLimiter(per_visitor), SlidingWindowLimiter(overall)


@lru_cache
def _admin_limiter(per_visitor: int) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(per_visitor)


WINDOW_SECONDS = 60


def _db_key(bucket: str, visitor: str) -> str:
    """Hashed, so no raw IP address is stored; the rows are also deleted after a few minutes."""
    return hashlib.sha256(f"{bucket}:{visitor}".encode()).hexdigest()[:32]


def db_retry_after(checks: list[tuple[str, int]], now=time.time, cleanup_chance: float = 0.02) -> float:
    """Shared fixed-window counters in Postgres. `checks` is [(key, limit), ...] checked in order;
    stops at the first exceeded limit so a blocked visitor does not use up the shared quota.
    Returns 0.0 if allowed, else seconds until the minute window ends. Raises if the DB is down."""
    window = int(now() // WINDOW_SECONDS)
    wait = 0.0
    with SessionLocal() as db:
        for key, limit in checks:
            hits = db.execute(
                text("INSERT INTO rate_limit_hits (key, window_start, hits) VALUES (:key, :window, 1) "
                     "ON CONFLICT (key, window_start) DO UPDATE SET hits = rate_limit_hits.hits + 1 "
                     "RETURNING hits"),
                {"key": key, "window": window},
            ).scalar_one()
            if hits > limit:
                wait = max(1.0, (window + 1) * WINDOW_SECONDS - now())
                break
        if random.random() < cleanup_chance:
            db.execute(text("DELETE FROM rate_limit_hits WHERE window_start < :old"), {"old": window - 5})
        db.commit()
    return wait


def _shared_wait(settings, checks: list[tuple[str, int]]) -> float | None:
    """Database-backed wait time, or None to tell the caller to use the in-memory limiter."""
    if getattr(settings, "rate_limit_backend", "memory") != "database":
        return None
    try:
        return db_retry_after(checks)
    except Exception:
        logger.exception("database rate limiter unavailable; using the in-memory limiter")
        return None


def _too_many(message: str, wait: float) -> HTTPException:
    return HTTPException(status_code=429, detail=message, headers={"Retry-After": str(math.ceil(wait))})


def visitor_ip(request: Request, trust_forwarded_for: bool) -> str:
    """The visitor's address. Behind Vercel every request arrives from Vercel's own network,
    so the real IP is in X-Forwarded-For (Vercel overwrites any value a visitor sends).
    Without a trusted proxy, that header is user-controlled and must be ignored."""
    if trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def lead_rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Per-visitor limit for POST /lead. It has no global bucket: it never calls Gemini."""
    visitor = visitor_ip(request, getattr(settings, "trust_forwarded_for", False))
    per_visitor, overall = settings.lead_rate_limit_per_minute, settings.lead_global_rate_limit_per_minute
    wait = _shared_wait(settings, [(_db_key("lead", visitor), per_visitor), ("lead:*", overall)])
    if wait is None:
        visitor_limiter, global_limiter = _lead_limiter(per_visitor, overall)
        wait = visitor_limiter.retry_after(visitor) or global_limiter.retry_after("*")
    if wait:
        raise _too_many("Too many submissions. Please wait a moment or email hello@sharpbuild.io.", wait)


def admin_rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Throttles guessing of the admin token."""
    visitor = visitor_ip(request, getattr(settings, "trust_forwarded_for", False))
    limit = settings.admin_rate_limit_per_minute
    wait = _shared_wait(settings, [(_db_key("admin", visitor), limit)])
    if wait is None:
        wait = _admin_limiter(limit).retry_after(visitor)
    if wait:
        raise _too_many("Too many requests.", wait)


def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    visitor = visitor_ip(request, getattr(settings, "trust_forwarded_for", False))
    wait = _shared_wait(settings, [(_db_key("chat", visitor), settings.rate_limit_per_minute),
                                   ("chat:*", settings.global_rate_limit_per_minute)])
    if wait is None:
        per_visitor, overall = _limiters(settings.rate_limit_per_minute, settings.global_rate_limit_per_minute)
        wait = per_visitor.retry_after(visitor) or overall.retry_after("*")
    if wait:
        raise _too_many("Too many questions right now. Please wait a moment and try again, "
                        "or email hello@sharpbuild.io.", wait)
