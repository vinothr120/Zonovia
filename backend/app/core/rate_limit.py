from fastapi import Request

from app.config import settings
from app.core.cache import get_redis, redis_breaker_is_open, trip_redis_breaker
from app.core.exceptions import RateLimitedError


async def rate_limit_by_ip(request: Request, *, bucket: str, max_attempts: int, window_seconds: int) -> None:
    """Fixed-window counter keyed by client IP + bucket name, e.g. `auth-login:203.0.113.4`.
    This is IP-scoped and independent of the per-account lockout in auth/service.py — that
    stops an attacker from grinding through one account's password, this stops an attacker
    from grinding through many accounts (or many tenants) from one IP before any single
    account's lockout threshold trips. Same fail-open philosophy as core/cache.py (and the
    same circuit breaker — see there): a Redis outage must not take down login entirely, so
    a cache error is treated as "not limited" rather than propagated."""
    if redis_breaker_is_open():
        return
    ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:{bucket}:{ip}"
    try:
        redis_client = get_redis()
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds)
    except Exception:
        trip_redis_breaker()
        return

    if count > max_attempts:
        raise RateLimitedError("Too many attempts. Try again in a few minutes.")


async def rate_limit_login(request: Request) -> None:
    await rate_limit_by_ip(
        request,
        bucket="auth-login",
        max_attempts=settings.login_rate_limit_per_ip,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
