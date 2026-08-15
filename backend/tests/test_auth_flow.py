from app.core import cache as cache_module
from app.core import rate_limit as rate_limit_module
from app.core.security import hash_password
from app.users.models import User
from tests.conftest import make_tenant


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass


async def _create_login_user(db, *, tenant, email: str, password: str) -> User:
    user = User(tenant_id=tenant.id, email=email, password_hash=hash_password(password), status="active")
    db.add(user)
    await db.flush()
    return user


async def test_login_then_access_protected_route_then_refresh_then_logout(client, db):
    tenant = await make_tenant(db, subdomain="login-flow")
    await _create_login_user(db, tenant=tenant, email="member@login-flow.example.com", password="Passw0rd!2026")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "login-flow", "email": "member@login-flow.example.com", "password": "Passw0rd!2026"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()["data"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()["data"]
    assert new_tokens["access_token"] != tokens["access_token"]

    # the old refresh token was rotated out and is now single-use
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
    assert logout.status_code == 204


async def test_login_with_wrong_password_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="wrong-pass")
    await _create_login_user(db, tenant=tenant, email="user@wrong-pass.example.com", password="CorrectHorse1!")
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "wrong-pass", "email": "user@wrong-pass.example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    # deliberately generic — must not reveal whether the email or the password was wrong
    assert response.json()["error"]["message"] == "Invalid email or password."


async def test_login_locks_account_after_repeated_failures(client, db):
    tenant = await make_tenant(db, subdomain="lockout-test")
    await _create_login_user(db, tenant=tenant, email="user@lockout-test.example.com", password="RightPassword1!")
    await db.commit()

    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": "lockout-test", "email": "user@lockout-test.example.com", "password": "wrong"},
        )

    response = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "lockout-test", "email": "user@lockout-test.example.com", "password": "RightPassword1!"},
    )
    assert response.status_code == 423


async def test_login_with_unknown_tenant_slug_is_rejected(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "does-not-exist", "email": "nobody@nowhere.example.com", "password": "whatever"},
    )
    assert response.status_code == 401


async def test_login_is_rate_limited_per_ip_independent_of_account_lockout(client, db, monkeypatch):
    """IP-scoped rate limiting (core/rate_limit.py) is a second, independent layer on top of
    the per-account lockout above — it trips even across DIFFERENT accounts/tenants from the
    same IP, before any single account's failure count reaches its own threshold."""
    cache_module._breaker_open_until = 0.0
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.config.settings.login_rate_limit_per_ip", 2)

    tenant = await make_tenant(db, subdomain="rate-limit-login")
    await _create_login_user(db, tenant=tenant, email="user@rate-limit-login.example.com", password="RightPassword1!")
    await db.commit()

    body = {"tenant_slug": "rate-limit-login", "email": "user@rate-limit-login.example.com", "password": "wrong"}
    for _ in range(2):
        resp = await client.post("/api/v1/auth/login", json=body)
        assert resp.status_code == 401  # ordinary wrong-password rejections, not yet limited

    limited = await client.post("/api/v1/auth/login", json=body)
    assert limited.status_code == 429
    cache_module._breaker_open_until = 0.0
