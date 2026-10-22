"""Tests of the shared collector infrastructure (rate limit, cache, retry)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from collectors.base import (
    DiskCache,
    HttpStatusError,
    RateLimiter,
    RateLimitExceededError,
    RetryableStatusError,
    RetryPolicy,
    make_async_client,
)


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


# --------------------------------------------------------------------------------------
# Rate limiter
# --------------------------------------------------------------------------------------


def test_rate_limiter_allows_the_configured_number_of_calls() -> None:
    limiter = RateLimiter("digikey", per_minute=3, per_day=10)
    for _ in range(3):
        limiter.acquire()
    assert limiter.used_minute == 3
    assert limiter.used_day == 3


def test_rate_limiter_refuses_to_exceed_the_minute_budget() -> None:
    limiter = RateLimiter("digikey", per_minute=2, per_day=100)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceededError) as excinfo:
        limiter.acquire()
    assert "per-minute" in str(excinfo.value)
    assert limiter.blocked == 1


def test_rate_limiter_refuses_to_exceed_the_day_budget() -> None:
    limiter = RateLimiter("mouser", per_minute=100, per_day=2)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceededError) as excinfo:
        limiter.acquire()
    assert "daily" in str(excinfo.value)
    assert limiter.used_day == 2


def test_rate_limiter_frees_the_budget_after_a_minute() -> None:
    clock = FakeClock()
    limiter = RateLimiter("digikey", per_minute=1, per_day=10, clock=clock, sleep=clock.sleep)
    limiter.acquire()
    with pytest.raises(RateLimitExceededError):
        limiter.acquire()
    clock.now += 61.0
    limiter.acquire()
    assert limiter.used_minute == 1


def test_rate_limiter_blocking_waits_for_the_next_slot() -> None:
    clock = FakeClock()
    limiter = RateLimiter("digikey", per_minute=1, per_day=10, clock=clock, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire(block=True)
    assert clock.slept
    assert clock.slept[0] > 0


def test_rate_limiter_resets_the_daily_budget_on_a_new_day() -> None:
    class FakeDay:
        def __init__(self) -> None:
            self.day = datetime(2026, 10, 1, tzinfo=UTC).date()

        def __call__(self) -> datetime.date:
            return self.day

    day = FakeDay()
    limiter = RateLimiter("digikey", per_minute=100, per_day=1, today=day)
    limiter.acquire()
    with pytest.raises(RateLimitExceededError):
        limiter.acquire()
    day.day = datetime(2026, 10, 2, tzinfo=UTC).date()
    limiter.acquire()
    assert limiter.used_day == 1


# --------------------------------------------------------------------------------------
# Disk cache
# --------------------------------------------------------------------------------------


def test_disk_cache_stores_the_payload_with_the_date(tmp_path: Path) -> None:
    moment = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    cache = DiskCache(tmp_path, "digikey", clock=lambda: moment)
    path = cache.put("digikey|GET|/products", {"Products": []})
    assert path.parent.name == "2026-10-01"
    assert path.parent.parent.name == "digikey"
    assert path.suffix == ".json"
    assert cache.get("digikey|GET|/products") == {"Products": []}


def test_disk_cache_reports_hits_and_misses(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path, "digikey")
    assert cache.get("missing") is None
    cache.put("key", {"a": 1})
    assert cache.get("key") == {"a": 1}
    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.puts == 1
    assert stats.as_dict()["hit_rate"] == 0.5


def test_disk_cache_finds_a_payload_of_an_earlier_day(tmp_path: Path) -> None:
    days = iter(
        [
            datetime(2026, 10, 1, tzinfo=UTC),
            datetime(2026, 10, 2, tzinfo=UTC),
        ]
    )
    cache = DiskCache(tmp_path, "digikey", clock=lambda: next(days))
    cache.put("key", {"a": 1})
    assert cache.get("key") == {"a": 1}
    assert cache.stats().hits == 1


def test_disk_cache_uses_the_sha256_of_the_key(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path, "digikey")
    digest = cache.hash_key("key")
    assert len(digest) == 64
    assert digest == cache.hash_key("key")
    assert digest != cache.hash_key("other key")


# --------------------------------------------------------------------------------------
# Retry
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_429_is_retried_and_then_succeeds() -> None:
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    policy = RetryPolicy(max_attempts=3, backoff=0.01, sleep=sleep)
    with respx.mock:
        route = respx.get("https://example.invalid/data").mock(
            side_effect=[
                httpx.Response(429, json={"error": "slow down"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with make_async_client() as client:

            async def call() -> httpx.Response:
                response = await client.get("https://example.invalid/data")
                if response.status_code == 429 or response.status_code >= 500:
                    raise RetryableStatusError(response.status_code)
                if response.status_code >= 400:
                    raise HttpStatusError(response.status_code)
                return response

            response = await policy.run_async(call)
    assert response.status_code == 200
    assert route.call_count == 2
    assert delays and delays[0] > 0


@pytest.mark.asyncio
async def test_a_500_is_retried() -> None:
    policy = RetryPolicy(max_attempts=3, backoff=0.001)
    with respx.mock:
        route = respx.get("https://example.invalid/data").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        async with make_async_client() as client:

            async def call() -> httpx.Response:
                response = await client.get("https://example.invalid/data")
                if response.status_code >= 500:
                    raise RetryableStatusError(response.status_code)
                return response

            response = await policy.run_async(call)
    assert response.status_code == 200
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_a_400_is_not_retried() -> None:
    policy = RetryPolicy(max_attempts=3, backoff=0.001)
    with respx.mock:
        route = respx.get("https://example.invalid/data").mock(
            return_value=httpx.Response(400, json={"error": "bad request"})
        )
        async with make_async_client() as client:

            async def call() -> httpx.Response:
                response = await client.get("https://example.invalid/data")
                if response.status_code >= 500:
                    raise RetryableStatusError(response.status_code)
                if response.status_code >= 400:
                    raise HttpStatusError(response.status_code)
                return response

            with pytest.raises(HttpStatusError):
                await policy.run_async(call)
    assert route.call_count == 1
