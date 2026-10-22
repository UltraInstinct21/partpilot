"""Shared infrastructure for every PartPilot collector (owned by agent A).

Everything that the distributor clients have in common lives here:

* :class:`RateLimiter` - enforces a per-minute *and* a per-day budget. The
  budget is always below the limit published by the distributor
  (DigiKey 120/min + 1000/day, Mouser 30/min + 1000/day).
* :class:`DiskCache` - stores every raw response as a JSON file *with the
  date* (``<raw_dir>/<namespace>/<YYYY-MM-DD>/<sha256>.json``). A cache hit
  never touches the network, which is what keeps DigiKey under 1000
  requests/day.
* :func:`make_async_client` / :func:`make_client` - one httpx client factory
  with the configured timeout and the clear ``User-Agent``.
* :class:`RetryPolicy` - tenacity based retry with exponential back-off for
  HTTP 429, HTTP 5xx and network errors. A 4xx other than 429 is never
  retried.
* :class:`TokenCache` - OAuth access token with an expiry margin so a token is
  refreshed before it expires.

No network call is made at import time and no secret is ever logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from shared.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

__all__ = [
    "CacheStats",
    "CollectorError",
    "DiskCache",
    "HttpStatusError",
    "InvalidPdfError",
    "MissingCredentialsError",
    "RateLimitExceededError",
    "RateLimiter",
    "RetryableStatusError",
    "RetryPolicy",
    "RobotsDisallowedError",
    "TokenCache",
    "make_async_client",
    "make_client",
    "request_with_retry",
    "run_sync",
    "status_to_error",
    "user_agent",
]


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class CollectorError(Exception):
    """Base class for every error raised by the collection layer."""


class MissingCredentialsError(CollectorError):
    """Raised when a distributor client is used without its credentials."""


class RateLimitExceededError(CollectorError):
    """Raised when a request would exceed the per-minute or per-day budget."""


class RetryableStatusError(CollectorError):
    """Raised for HTTP 429 and HTTP 5xx - these responses are retried."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}{f': {detail}' if detail else ''}")


class HttpStatusError(CollectorError):
    """Raised for a non-retryable HTTP error (4xx other than 429)."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}{f': {detail}' if detail else ''}")


class RobotsDisallowedError(CollectorError):
    """Raised when ``robots.txt`` disallows the requested path."""


class InvalidPdfError(CollectorError):
    """Raised when a downloaded body is not a real PDF."""


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def user_agent(settings: Settings | None = None) -> str:
    """Return the clear ``User-Agent`` that every request must send."""
    return (settings or get_settings()).user_agent


def run_sync(coro: Awaitable[T]) -> T:
    """Run an awaitable from synchronous code.

    The :class:`shared.interfaces.Collector` protocol is synchronous, but the
    HTTP stack is asynchronous. This helper runs the coroutine in a fresh event
    loop and also works when the caller is already inside a running loop (the
    coroutine is then executed in a dedicated worker thread).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()  # type: ignore[arg-type]


def make_client(settings: Settings | None = None, **overrides: Any) -> httpx.Client:
    """Return a synchronous httpx client with the PartPilot defaults."""
    settings = settings or get_settings()
    headers = {"User-Agent": user_agent(settings), "Accept": "application/json"}
    timeout = overrides.pop("timeout", settings.request_timeout_seconds)
    headers.update(overrides.pop("headers", {}) or {})
    return httpx.Client(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        **overrides,
    )


def make_async_client(settings: Settings | None = None, **overrides: Any) -> httpx.AsyncClient:
    """Return an asynchronous httpx client with the PartPilot defaults."""
    settings = settings or get_settings()
    headers = {"User-Agent": user_agent(settings), "Accept": "application/json"}
    timeout = overrides.pop("timeout", settings.request_timeout_seconds)
    headers.update(overrides.pop("headers", {}) or {})
    return httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        **overrides,
    )


# --------------------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------------------


class RateLimiter:
    """Enforce a per-minute and a per-day request budget.

    The limiter counts the calls it allowed. :meth:`acquire` raises
    :class:`RateLimitExceededError` when the next call would exceed a budget -
    the collection run then stops instead of hammering the distributor.

    The clock and the sleep function are injectable so the tests can run
    without waiting.
    """

    def __init__(
        self,
        name: str,
        per_minute: int,
        per_day: int,
        *,
        clock: Callable[[], float] | None = None,
        today: Callable[[], date] | None = None,
        sleep: Callable[[float], Any] | None = None,
    ) -> None:
        if per_minute <= 0 or per_day <= 0:
            raise ValueError("rate limit budgets must be positive")
        self.name = name
        self.per_minute = per_minute
        self.per_day = per_day
        self._clock = clock or time.monotonic
        self._today = today or (lambda: datetime.now(UTC).date())
        self._sleep = sleep or time.sleep
        self._minute_calls: deque[float] = deque()
        self._day = self._today()
        self._day_calls = 0
        self._blocked = 0

    # -- introspection ---------------------------------------------------------------
    @property
    def used_minute(self) -> int:
        """Number of calls in the current minute window."""
        self._prune()
        return len(self._minute_calls)

    @property
    def used_day(self) -> int:
        """Number of calls since the start of the current day."""
        self._prune()
        return self._day_calls

    @property
    def blocked(self) -> int:
        """Number of calls that were refused because a budget was exhausted."""
        return self._blocked

    # -- behaviour -------------------------------------------------------------------
    def _prune(self) -> None:
        now = self._clock()
        cutoff = now - 60.0
        while self._minute_calls and self._minute_calls[0] <= cutoff:
            self._minute_calls.popleft()
        today = self._today()
        if today != self._day:
            self._day = today
            self._day_calls = 0
            self._minute_calls.clear()

    def try_acquire(self) -> bool:
        """Take one slot from the budget. Return ``False`` when it is exhausted."""
        self._prune()
        if self._day_calls >= self.per_day or len(self._minute_calls) >= self.per_minute:
            self._blocked += 1
            return False
        self._minute_calls.append(self._clock())
        self._day_calls += 1
        return True

    def acquire(self, *, block: bool = False) -> None:
        """Take one slot from the budget or raise :class:`RateLimitExceededError`.

        With ``block=True`` the call waits until the minute window frees a slot.
        The daily budget is never waited for - it is a hard stop.
        """
        if self.try_acquire():
            return
        self._prune()
        if self._day_calls >= self.per_day:
            raise RateLimitExceededError(
                f"{self.name}: daily budget of {self.per_day} requests is exhausted"
            )
        if not block:
            raise RateLimitExceededError(
                f"{self.name}: per-minute budget of {self.per_minute} requests is exhausted"
            )
        while not self.try_acquire():
            self._prune()
            if self._day_calls >= self.per_day:
                raise RateLimitExceededError(
                    f"{self.name}: daily budget of {self.per_day} requests is exhausted"
                )
            oldest = self._minute_calls[0] if self._minute_calls else self._clock()
            wait = max(0.0, 60.0 - (self._clock() - oldest))
            self._sleep(wait)

    def reset(self) -> None:
        """Forget every counted call (used by the tests)."""
        self._minute_calls.clear()
        self._day_calls = 0
        self._day = self._today()
        self._blocked = 0


# --------------------------------------------------------------------------------------
# Disk cache
# --------------------------------------------------------------------------------------


@dataclass
class CacheStats:
    """Hit/miss counters of a :class:`DiskCache`."""

    hits: int = 0
    misses: int = 0
    puts: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "puts": self.puts,
            "hit_rate": round(self.hit_rate, 4),
        }


class DiskCache:
    """Store every raw response as a dated JSON file.

    Layout::

        <raw_dir>/<namespace>/<YYYY-MM-DD>/<sha256-of-key>.json

    A lookup first checks today's directory and then the older ones, so a part
    that was already collected yesterday is *not* requested again. That is what
    keeps the DigiKey request count below 1000/day.
    """

    def __init__(
        self,
        root: Path | str,
        namespace: str = "default",
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root)
        self.namespace = namespace
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stats = CacheStats()

    # -- paths -----------------------------------------------------------------------
    @property
    def namespace_dir(self) -> Path:
        return self.root / self.namespace

    @staticmethod
    def hash_key(key: str) -> str:
        """Return the sha256 of the cache key (the file name)."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def path_for(self, key: str, when: datetime | None = None) -> Path:
        """Return the path the payload of ``key`` is (or would be) stored at."""
        moment = when or self._clock()
        return self.namespace_dir / moment.strftime("%Y-%m-%d") / f"{self.hash_key(key)}.json"

    def dated_dirs(self) -> list[Path]:
        """Return the dated directories of this namespace, newest first."""
        if not self.namespace_dir.exists():
            return []
        return sorted(
            (p for p in self.namespace_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )

    # -- api -------------------------------------------------------------------------
    def get(self, key: str) -> Any | None:
        """Return the cached payload of ``key`` or ``None`` when it is missing."""
        digest = self.hash_key(key)
        candidates = [self.path_for(key)]
        candidates.extend(d / f"{digest}.json" for d in self.dated_dirs())
        for candidate in candidates:
            if candidate.is_file():
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    logger.warning("cache file %s is unreadable, ignoring it", candidate)
                    continue
                self._stats.hits += 1
                return payload
        self._stats.misses += 1
        return None

    def put(self, key: str, payload: Any) -> Path:
        """Store ``payload`` for ``key`` and return the file it was written to."""
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        self._stats.puts += 1
        return path

    def stats(self) -> CacheStats:
        """Return the hit/miss counters."""
        return self._stats

    def clear(self) -> None:
        """Delete every cached file of this namespace (used by the tests)."""
        if not self.namespace_dir.exists():
            return
        for path in sorted(self.namespace_dir.rglob("*.json")):
            path.unlink()


# --------------------------------------------------------------------------------------
# Retry
# --------------------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Retry 429 / 5xx / network errors with an exponential back-off.

    A 4xx other than 429 is never retried - it is a client error and retrying
    it would only waste the request budget.
    """

    max_attempts: int = 4
    backoff: float = 0.5
    max_backoff: float = 30.0
    sleep: Callable[[float], Any] | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        sleep: Callable[[float], Any] | None = None,
    ) -> RetryPolicy:
        settings = settings or get_settings()
        return cls(
            max_attempts=max(1, settings.max_retries),
            backoff=max(0.0, settings.retry_backoff_seconds),
            sleep=sleep,
        )

    def _wait(self) -> Any:
        return wait_exponential(
            multiplier=max(self.backoff, 1e-6),
            min=max(self.backoff, 1e-6),
            max=self.max_backoff,
        )

    def _retry_predicate(self) -> Any:
        return retry_if_exception_type((RetryableStatusError, httpx.TransportError))

    def run(self, func: Callable[[], T]) -> T:
        """Run ``func`` synchronously with the retry policy."""
        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=self._wait(),
            retry=self._retry_predicate(),
            reraise=True,
            sleep=self._sleep_sync,
        )
        return retrying(func)

    async def run_async(self, func: Callable[[], Awaitable[T]]) -> T:
        """Run the awaitable ``func`` with the retry policy."""

        async def _call() -> T:
            # ``func`` may be a plain function that returns a coroutine.
            result = func()
            if inspect.isawaitable(result):
                result = await result
            return result  # type: ignore[return-value]

        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=self._wait(),
            retry=self._retry_predicate(),
            reraise=True,
            sleep=self._sleep_async,
        )
        return await retrying(_call)

    def _sleep_sync(self, seconds: float) -> None:
        """Sleep between two attempts (sync)."""
        if self.sleep is None:
            time.sleep(seconds)
            return
        result = self.sleep(seconds)
        if inspect.isawaitable(result):
            # A coroutine function was injected - run it in its own loop.
            asyncio.run(result)  # type: ignore[arg-type]

    async def _sleep_async(self, seconds: float) -> None:
        """Sleep between two attempts (async)."""
        if self.sleep is None:
            await asyncio.sleep(seconds)
            return
        result = self.sleep(seconds)
        if inspect.isawaitable(result):
            await result


# --------------------------------------------------------------------------------------
# OAuth token cache
# --------------------------------------------------------------------------------------


class TokenCache:
    """Hold one OAuth access token and know when it has to be refreshed."""

    def __init__(
        self,
        *,
        refresh_margin: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.refresh_margin = refresh_margin
        self._clock = clock or time.monotonic
        self._token: str | None = None
        self._expires_at: float = 0.0

    @property
    def token(self) -> str | None:
        """Return the token when it is still valid, otherwise ``None``."""
        if self._token is None:
            return None
        if self._clock() >= self._expires_at - self.refresh_margin:
            return None
        return self._token

    def set(self, token: str, expires_in: float) -> None:
        """Store a token that is valid for ``expires_in`` seconds."""
        self._token = token
        self._expires_at = self._clock() + float(expires_in)

    def clear(self) -> None:
        """Forget the token."""
        self._token = None
        self._expires_at = 0.0


# --------------------------------------------------------------------------------------
# HTTP helpers shared by the clients
# --------------------------------------------------------------------------------------


def status_to_error(response: httpx.Response) -> None:
    """Raise the matching error for a failed HTTP response.

    * 429 and 5xx raise :class:`RetryableStatusError` (the caller retries).
    * every other 4xx raises :class:`HttpStatusError` (never retried).
    """
    if response.status_code < 400:
        return
    detail = response.text[:300] if response.status_code != 429 else ""
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableStatusError(response.status_code, detail)
    raise HttpStatusError(response.status_code, detail)


@asynccontextmanager
async def http_client(
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """Yield ``client`` or a freshly built one with the PartPilot defaults."""
    if client is not None:
        yield client
        return
    async with make_async_client(settings) as owned:
        yield owned


async def request_with_retry(
    policy: RetryPolicy,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Send one request and retry the answers that may be temporary.

    The status check happens *inside* the retried call, so an HTTP 429 or an
    HTTP 5xx leads to a new attempt with an exponential back-off. Every other
    4xx is raised at once.
    """

    async def _call() -> httpx.Response:
        response = await client.request(method, url, **kwargs)
        status_to_error(response)
        return response

    return await policy.run_async(_call)


def cache_key(*parts: Any) -> str:
    """Build a stable cache key out of the given parts."""
    return "|".join(str(part) for part in parts)
