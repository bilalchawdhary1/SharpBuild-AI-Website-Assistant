"""In-memory sliding-window rate limiting (no extra dependency).

Limits: one visitor (IP) and the whole service together, because the free Gemini
quota is shared by everyone. In-memory means each server process counts on its
own and counters reset on restart: fine for one small instance; use Redis if you
ever run several.
"""
import math
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Callable

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings


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


def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    per_visitor, overall = _limiters(settings.rate_limit_per_minute, settings.global_rate_limit_per_minute)
    visitor = visitor_ip(request, getattr(settings, "trust_forwarded_for", False))
    wait = per_visitor.retry_after(visitor) or overall.retry_after("*")
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many questions right now. Please wait a moment and try again, "
                   "or email hello@sharpbuild.io.",
            headers={"Retry-After": str(math.ceil(wait))},
        )
