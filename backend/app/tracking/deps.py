"""Gateway (non-user) authentication — a fully separate, parallel dependency chain from
app/core/deps.py's TokenPayload/get_token_payload/get_db/require_module, never mixed with user
auth on the same endpoint. A DeviceGateway authenticates with two dedicated headers
(X-Gateway-Tenant-Slug + X-Gateway-Api-Key), never Authorization: Bearer — so an opaque API key
can never flow into the JWT decode path, and a leaked gateway key can never be exchanged for (or
mistaken for) a user's bearer token, nor vice versa. See the module's implementation plan's
"Gateway auth is a separate, parallel dependency chain" design decision.

get_gateway_payload mirrors AuthService.login's own two-step bootstrap exactly: resolve
tenant_slug against the global, non-RLS `tenants` table first, set the RLS session var, THEN
look up the gateway (now correctly scoped by hash) — the same chicken-and-egg problem login
already solves. It reuses app.core.deps.get_public_db (the existing "no identity established
yet" session-getter) rather than inventing a bespoke bootstrap session.

get_gateway_db is the second half of the parallel chain, structurally identical to
app.core.deps.get_db but scoped to GatewayPayload instead of TokenPayload. require_module_for_
gateway mirrors app.core.deps.require_module the same way. None of this modifies
app/core/deps.py itself.
"""

import hashlib
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_model import utcnow
from app.core.database import AsyncSessionLocal, set_tenant_session_var
from app.core.deps import get_public_db
from app.core.exceptions import AppError, PermissionDeniedError, UnauthorizedError
from app.tenants.repository import TenantRepository


def _hash_gateway_key(key: str) -> str:
    """Mirrors app/auth/service.py::_hash_token exactly (hashlib.sha256(...).hexdigest(),
    never the raw key stored) — deliberately not refactored into a shared utility; not worth
    touching a working, tested auth file for a one-line function. See the module's
    implementation plan."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GatewayPayload:
    gateway_id: uuid.UUID
    tenant_id: uuid.UUID


async def get_gateway_payload(
    x_gateway_tenant_slug: str | None = Header(default=None, alias="X-Gateway-Tenant-Slug"),
    x_gateway_api_key: str | None = Header(default=None, alias="X-Gateway-Api-Key"),
    db: AsyncSession = Depends(get_public_db),
) -> GatewayPayload:
    """Validates the two gateway headers and returns a GatewayPayload — the gateway-auth
    equivalent of app.core.deps.get_token_payload. Unlike a JWT, an API key isn't
    self-verifying, so (unlike get_token_payload) this dependency genuinely needs a DB round
    trip; it borrows get_public_db's session for that lookup rather than opening its own.
    Missing headers, an unknown tenant slug, an inactive tenant, an unknown key hash, or a
    revoked/inactive gateway are all folded into the same generic 401 — never reveal which
    part of the credential pair was wrong.

    Commits explicitly (rather than leaving it to get_public_db's own post-yield commit,
    which wouldn't run until the whole request — including get_gateway_db's entirely separate
    session doing the real ingest work — has finished) so this session's transaction closes
    out immediately instead of sitting open for the rest of the request. Two simultaneously
    open transactions per request is already an unusual shape (see this module's docstring);
    leaving one of them uncommitted-but-idle for the whole request needlessly holds a row
    lock on device_gateways the whole time — harmless on Postgres under light load, but a
    guaranteed 'database is locked' on file-based SQLite, verified during this phase's own
    end-to-end run against scripts/run_dev_sqlite.py."""
    from app.tracking.repository import DeviceGatewayRepository

    if not x_gateway_tenant_slug or not x_gateway_api_key:
        raise UnauthorizedError("Missing gateway credentials.")

    tenant = await TenantRepository(db).get_by_subdomain(x_gateway_tenant_slug)
    if tenant is None or tenant.status != "active":
        raise UnauthorizedError("Invalid gateway credentials.")

    await set_tenant_session_var(db, tenant.id, local=True)
    gateway = await DeviceGatewayRepository(db, tenant.id).get_by_api_key_hash(_hash_gateway_key(x_gateway_api_key))
    if gateway is None or gateway.status != "active":
        raise UnauthorizedError("Invalid gateway credentials.")

    gateway.last_seen_at = utcnow()
    await db.commit()

    return GatewayPayload(gateway_id=gateway.id, tenant_id=tenant.id)


async def get_gateway_db(payload: GatewayPayload = Depends(get_gateway_payload)) -> AsyncGenerator[AsyncSession, None]:
    """Mirrors app.core.deps.get_db's shape exactly, scoped to GatewayPayload instead of
    TokenPayload — a fresh session, deliberately not the same connection get_gateway_payload
    used (that one belongs to get_public_db's own request-scoped lifecycle)."""
    async with AsyncSessionLocal() as session:
        await set_tenant_session_var(session, payload.tenant_id, local=True)
        try:
            yield session
            await session.commit()
        except AppError:
            # Mirrors get_db's own reasoning — a rejected request's writes made before the
            # rejection (e.g. RfidReadEvent rows already inserted earlier in a batch) still
            # survive; only a genuinely unexpected exception discards the transaction.
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            raise


def require_module_for_gateway(module_key: str):
    """Gateway-auth mirror of app.core.deps.require_module — same Entitlement Check logic,
    scoped to GatewayPayload instead of TokenPayload. Deliberately duplicated rather than
    parameterized over payload type: keeping the two chains structurally independent (so a
    change to user-auth's require_module can never accidentally affect gateway auth, or vice
    versa) is the whole point of this file. No require_permission equivalent exists for
    gateways — a gateway has no user/role, only "is this key valid and active", which
    get_gateway_payload itself already establishes."""

    async def checker(
        db: AsyncSession = Depends(get_gateway_db),
        payload: GatewayPayload = Depends(get_gateway_payload),
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
