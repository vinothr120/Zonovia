"""core/rate_limit.py — IP-scoped, Redis-backed login throttling. Closes a gap a bare
RateLimitedError exception class (core/exceptions.py) can't close by itself: without
something raising it, nothing actually rate-limits repeated login attempts across accounts
from one IP (only the per-account lockout in auth/service.py exists). Uses a tiny fake Redis
client rather than a real one — the dev/test environment doesn't run Redis, and the whole
point of core/cache.py's circuit breaker is that these code paths must not depend on Redis
being up."""

from unittest.mock import AsyncMock

import pytest

from app.core import cache as cache_module
from app.core import rate_limit as rate_limit_module
from app.core.exceptions import RateLimitedError
from app.core.rate_limit import rate_limit_by_ip


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass


class _FakeRequest:
    def __init__(self, ip: str):
        self.client = type("Client", (), {"host": ip})()


@pytest.fixture(autouse=True)
def _reset_breaker():
    cache_module._breaker_open_until = 0.0
    yield
    cache_module._breaker_open_until = 0.0


async def test_rate_limit_allows_up_to_max_attempts(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake)
    request = _FakeRequest("203.0.113.1")

    for _ in range(3):
        await rate_limit_by_ip(request, bucket="test-bucket", max_attempts=3, window_seconds=60)


async def test_rate_limit_rejects_beyond_max_attempts(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake)
    request = _FakeRequest("203.0.113.2")

    for _ in range(3):
        await rate_limit_by_ip(request, bucket="test-bucket", max_attempts=3, window_seconds=60)

    with pytest.raises(RateLimitedError):
        await rate_limit_by_ip(request, bucket="test-bucket", max_attempts=3, window_seconds=60)


async def test_rate_limit_is_scoped_per_ip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake)

    request_a = _FakeRequest("203.0.113.3")
    request_b = _FakeRequest("203.0.113.4")

    for _ in range(3):
        await rate_limit_by_ip(request_a, bucket="test-bucket", max_attempts=3, window_seconds=60)

    # A different IP has its own counter — must not be affected by IP A's attempts.
    await rate_limit_by_ip(request_b, bucket="test-bucket", max_attempts=3, window_seconds=60)


async def test_rate_limit_fails_open_when_redis_is_unavailable(monkeypatch):
    broken = AsyncMock()
    broken.incr = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    broken.expire = AsyncMock()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: broken)
    request = _FakeRequest("203.0.113.5")

    # Must not raise — an unreachable Redis degrades to "not rate limited", not a 5xx.
    await rate_limit_by_ip(request, bucket="test-bucket", max_attempts=1, window_seconds=60)
