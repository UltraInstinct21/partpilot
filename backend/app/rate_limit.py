"""A small in-process rate limiter.

``POST /api/search`` may call an LLM, so it is rate limited per client IP
(plan WP6, "API rules"). The limiter is deliberately simple - a fixed window
per key - because the API runs on one machine and the limit protects the LLM
budget, not a distributed system.

The limiter can be reset and its limit can be lowered, which is what the tests
use.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    """The outcome of one rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class FixedWindowRateLimiter:
    """Fixed window limiter: at most ``limit`` calls per ``window_seconds``.

    Args:
        limit: Maximum number of calls per window. ``0`` or less blocks everything.
        window_seconds: Length of the window in seconds.
        clock: Monotonic clock, injectable for tests.
    """

    def __init__(
        self,
        limit: int = 30,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = int(limit)
        self._window = float(window_seconds)
        self._clock = clock
        self._counters: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        """The configured number of calls per window."""
        return self._limit

    def set_limit(self, limit: int) -> None:
        """Change the limit and drop the current counters."""
        with self._lock:
            self._limit = int(limit)
            self._counters.clear()

    def check(self, key: str) -> RateLimitDecision:
        """Register one call for ``key`` and report whether it is allowed."""
        now = self._clock()
        with self._lock:
            window_start, count = self._counters.get(key, (now, 0))
            if now - window_start >= self._window:
                window_start, count = now, 0
            if count >= self._limit:
                retry_after = max(1, int(round(self._window - (now - window_start))))
                self._counters[key] = (window_start, count)
                return RateLimitDecision(
                    allowed=False, limit=self._limit, remaining=0, retry_after=retry_after
                )
            count += 1
            self._counters[key] = (window_start, count)
            return RateLimitDecision(
                allowed=True,
                limit=self._limit,
                remaining=max(0, self._limit - count),
                retry_after=0,
            )

    def reset(self, key: str | None = None) -> None:
        """Forget one key, or every key when ``key`` is ``None``."""
        with self._lock:
            if key is None:
                self._counters.clear()
            else:
                self._counters.pop(key, None)


__all__ = ["FixedWindowRateLimiter", "RateLimitDecision"]
