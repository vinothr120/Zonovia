import json
import time
from functools import lru_cache
from typing import Any

import redis.asyncio as redis

from app.config import settings

# A failed Redis call skips subsequent attempts for this long — bounds an outage to one
# slow call per window instead of one slow call per request. Every caller here already
# treats a Redis error as "cache miss" / "not rate limited" (permissions/rate-limiting are
# a performance optimization on top of Postgres as the source of truth, not load-bearing),
# so skipping the attempt entirely during an outage is strictly better than repeating it.
_BREAKER_COOLDOWN_SECONDS = 5.0
_breaker_open_until: float = 0.0


def redis_breaker_is_open() -> bool:
    """True while a recent Redis failure means callers should skip the attempt entirely
    (see module docstring above). Shared across cache.py and rate_limit.py so a Redis
    outage trips one breaker, not two independent ones."""
    return time.monotonic() < _breaker_open_until


def trip_redis_breaker() -> None:
    global _breaker_open_until
    _breaker_open_until = time.monotonic() + _BREAKER_COOLDOWN_SECONDS


_breaker_is_open = redis_breaker_is_open
_trip_breaker = trip_redis_breaker


@lru_cache
def get_redis() -> redis.Redis:
    # Explicit short timeouts so an unreachable Redis fails fast instead of hanging on the
    # OS-level TCP timeout (which can be tens of seconds).
    return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


async def get_cached_json(key: str) -> Any | None:
    """Best-effort cache read — a Redis outage degrades to always-hit-the-database rather
    than failing requests, since the permission cache is a performance optimization, not
    the source of truth (that's always Postgres)."""
    if _breaker_is_open():
        return None
    try:
        raw = await get_redis().get(key)
    except Exception:
        _trip_breaker()
        return None
    return json.loads(raw) if raw is not None else None


async def set_cached_json(key: str, value: Any, *, ttl_seconds: int = 300) -> None:
    if _breaker_is_open():
        return
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        _trip_breaker()


async def invalidate(key: str) -> None:
    if _breaker_is_open():
        return
    try:
        await get_redis().delete(key)
    except Exception:
        _trip_breaker()


def permission_cache_key(user_id: str) -> str:
    return f"permissions:{user_id}"
