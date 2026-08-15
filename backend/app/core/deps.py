import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, set_tenant_session_var
from app.core.exceptions import AppError, PermissionDeniedError, UnauthorizedError
from app.core.security import TokenError, TokenType, decode_token
from app.core.tenant_context import set_current_user_id, set_is_platform_admin, set_tenant_id
from app.users.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    is_platform_admin: bool


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TokenPayload:
    """Decodes the access token and seeds the request's tenant context BEFORE any database
    session is opened — get_db (below) depends on this, guaranteeing the ordering that makes
    Postgres RLS session-variable scoping correct. See docs/multi-tenancy.md's request
    lifecycle diagram."""
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    token_payload = TokenPayload(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        is_platform_admin=bool(payload.get("platform_admin", False)),
    )
    set_tenant_id(token_payload.tenant_id)
    set_current_user_id(token_payload.user_id)
    set_is_platform_admin(token_payload.is_platform_admin)
    return token_payload


async def get_db(payload: TokenPayload = Depends(get_token_payload)) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        if not payload.is_platform_admin:
            await set_tenant_session_var(session, payload.tenant_id, local=True)
        try:
            yield session
            await session.commit()
        except AppError:
            # A business-rule rejection (wrong password, permission denied, ...) still
            # returns an error to the client, but writes made before the rejection —
            # a failed-login counter, an audit log entry — are intentional and must survive.
            # Only a genuinely unexpected exception below should discard the transaction.
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            raise


async def get_public_db() -> AsyncGenerator[AsyncSession, None]:
    """For the handful of endpoints that run BEFORE identity is established — login,
    token refresh. No access token exists yet, so there's no TokenPayload to seed tenant
    context from; the auth service resolves tenant_id itself (from the login request's
    tenant_slug, or from a verified-but-not-yet-"current" refresh token) and sets the RLS
    session variable explicitly once it knows it."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except AppError:
            await session.commit()  # see get_db's comment above — same reasoning applies here
            raise
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    payload: TokenPayload = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    from app.users.repository import UserRepository

    repo = UserRepository(db, payload.tenant_id)
    user = await repo.get_by_id(payload.user_id)
    if user is None or user.status != "active":
        raise UnauthorizedError("User account is not active.")
    return user


def require_permission(permission_key: str):
    """Dependency factory — `Depends(require_permission("users.create"))`. Checks the
    user's cached effective grants (app/users/service.py). Row-level scope checks beyond
    "does this permission exist at all" are implemented per-module, not here, once Phase 1+
    introduces location-scoped roles — see docs/authorization.md.

    Any plain (untyped-by-Body) parameter this dependency's inner `checker` declares is
    bound by FastAPI exactly like an endpoint's own parameter — from a path segment or a
    query string, sourced by name across the whole operation (dependency + endpoint share
    the same parameter namespace). Phase 0 has no location-scoped resource to bind such a
    parameter from (only `scope_type="tenant"` is valid — see the plan's naming decisions),
    so `checker` takes no extra parameters yet; this is the seam Phase 1's location-scoped
    permissions extend without changing this function's shape."""

    async def checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        payload: TokenPayload = Depends(get_token_payload),
    ) -> User:
        from app.users.service import UserService

        service = UserService(db, payload.tenant_id)
        grants = await service.get_effective_grants(user.id)
        covered = any(g.permission_key == permission_key for g in grants)
        if not covered:
            raise PermissionDeniedError(f"Missing permission: {permission_key}")
        return user

    return checker


def require_platform_admin():
    async def checker(payload: TokenPayload = Depends(get_token_payload)) -> TokenPayload:
        if not payload.is_platform_admin:
            raise PermissionDeniedError("Platform administrator access required.")
        return payload

    return checker


def require_module(module_key: str):
    """Dependency factory — `Depends(require_module("asset-core"))`. The Entitlement Check
    gate (blueprint §18, ADR-007): no-ops for `always_on` Platform Core modules (they can
    never be un-entitled), otherwise defers to app.entitlements.EntitlementService. Uses the
    same lazy-import-inside-function style as require_permission above, to avoid a
    core <-> domain circular import between app.core.deps and app.entitlements."""

    async def checker(
        db: AsyncSession = Depends(get_db),
        payload: TokenPayload = Depends(get_token_payload),
    ) -> None:
        from app.core.module_registry import get_module
        from app.entitlements.service import EntitlementService

        module = get_module(module_key)
        if module is not None and module.always_on:
            return
        service = EntitlementService(db, payload.tenant_id)
        if not await service.is_enabled(module_key):
            raise PermissionDeniedError(f"Module '{module_key}' is not licensed for this tenant.")

    return checker
