"""Resolves which database session factory a given tenant's requests should use.

Per the architecture blueprint §9/ADR-003: the SaaS shared tier uses one shared Postgres
database (RLS-isolated); Private Cloud/Enterprise/On-Prem tenants get a dedicated database
each, addressed via `TenantConnectionRoute.dedicated_dsn_secret_ref`. Every Phase 0 tenant's
route row is `connection_mode='shared_pool'`, so this module is a real, tested, standalone
seam rather than a live feature yet — Phase 9 changes `resolve_session_factory`'s internals
(actually building/caching a per-tenant engine from the secret reference) without any caller
of this function changing. See ADR-003's consequence: "cheaper to build the seam now than
retrofit it later."
"""

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import AsyncSessionLocal


async def resolve_session_factory(tenant_id: uuid.UUID) -> async_sessionmaker:
    """Returns the session factory a tenant's requests should use. Phase 0: always the
    single shared `AsyncSessionLocal`, regardless of the tenant's `TenantConnectionRoute`
    row (every Phase 0 row is `shared_pool` — see migrations/versions/0001). Phase 9 adds a
    branch here that resolves `dedicated_dsn_secret_ref` for `connection_mode='dedicated'`
    tenants, builds (and caches) a dedicated engine/sessionmaker for it, and returns that
    instead — no caller of `resolve_session_factory` needs to change when that lands."""
    del tenant_id  # unused in Phase 0 — every tenant resolves to the shared pool
    return AsyncSessionLocal
