# Multi-Tenant Strategy

## Decision: shared schema, `tenant_id` column, PostgreSQL Row-Level Security (Phase 0)

One database, one schema, every tenant-scoped table carries a `tenant_id` (UUID, FK to `tenants.id`). Isolation is enforced at **two independent layers** so a bug in one doesn't leak data:

1. **Database layer — Postgres RLS.** Every tenant-scoped table has a `USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)` policy (`backend/migrations/versions/0002_enable_rls.py`). `current_setting(..., true)` returns `NULL` instead of raising when the session variable hasn't been set, and `tenant_id = NULL` is never true — so a query that runs with no tenant context set (a bug) sees **zero rows**, not every tenant's. `app.core.deps.get_db` sets `app.current_tenant_id` via `SET LOCAL` (`app.core.database.set_tenant_session_var`) at the start of every authenticated request, scoped to that request's transaction.
2. **Application layer — `TenantScopedRepository`.** Every module's repository (`app.core.base_repository.TenantScopedRepository`) automatically injects `tenant_id` into every `SELECT`/`INSERT`/`UPDATE`/`DELETE`. This isn't redundant with RLS — it's defense in depth, and it's what makes cross-tenant queries impossible to write by accident in application code (RLS alone would let a bug through if a raw connection skipped `SET LOCAL`, or if the app connected as a superuser — see the role-separation note below).

This is the architecture blueprint's §9/ADR-003 SaaS-shared-tier strategy. Private Cloud/Enterprise/On-Prem tenants get a dedicated database each instead — same schema, same Alembic migration history, only the connection-resolution layer changes (see "Tenant Routing Table" below). Schema-per-tenant is explicitly not built (ADR-003's reasoning: no customer segment needs it over the two strategies above, and it adds real migration-fan-out complexity).

## Role separation: why RLS actually holds

`migrations/versions/0003_app_role_grants.py` grants `SELECT, INSERT, UPDATE, DELETE` (no ownership) to a dedicated `zonovia_app` Postgres role — created by `infrastructure/docker/postgres-init.sql` before migrations ever run. The application always connects as `zonovia_app`, never as the migration/superuser role that ran `alembic upgrade head` and therefore *owns* every table. This matters because Postgres exempts a table's owning role from its own RLS policies unless `FORCE ROW LEVEL SECURITY` is set — migration `0002` sets `FORCE` on every RLS-protected table, but that alone isn't sufficient if the app connects as the owner. Role separation is what makes `FORCE ROW LEVEL SECURITY` meaningful rather than a no-op.

## Tenant vs. any future location concept

A **tenant** is the billing/isolation boundary — a SaaS account (`app.tenants.models.Tenant`). Phase 0 builds `Tenant` alone; there is deliberately no `School`/`Site`/`AssetLocation` concept yet. Per the architecture blueprint's bounded-context table (§6), `AssetLocation` belongs to **Asset Core**, which is Phase 1 — building a location hierarchy now would pre-empt that phase's actual data model with the wrong shape. `UserRole.scope_type`/`scope_id` keep the column shape a future location-scoped role needs (`tenant`/`school`/`campus` are valid column values), but Phase 0 only implements and validates `scope_type="tenant"` — see `docs/authorization.md`.

## What every tenant-scoped table looks like

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    -- ... domain columns ...
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID REFERENCES users(id),
    updated_by      UUID REFERENCES users(id),
    deleted_at      TIMESTAMPTZ  -- soft delete
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```

Non-tenant-scoped tables in Phase 0: `tenants` itself (it IS the isolation boundary), `tenant_connection_routes` (platform-global routing/control plane, see below), `permissions` (a global read-only catalog), and `role_permissions` (never queried without joining through `roles`, whose own policy already governs visibility). `roles` gets a variant policy — `tenant_id = current_setting(...)::uuid OR tenant_id IS NULL` — because system roles (Platform Admin, Tenant Admin, Member, Viewer) are shared catalog rows with `tenant_id IS NULL`, visible to every tenant.

## The Tenant Routing Table (ADR-003)

`app.tenants.models.TenantConnectionRoute` — one row per tenant, `connection_mode` (`shared_pool` | `dedicated`) + `dedicated_dsn_secret_ref`. Every Phase 0 tenant is `shared_pool`. `app.core.connection_router.resolve_session_factory(tenant_id)` is a real, tested, standalone function that always returns the single shared `AsyncSessionLocal` today — Phase 9 (dedicated per-tenant databases for Private Cloud/Enterprise/On-Prem) changes its internals to resolve `dedicated_dsn_secret_ref` and build/cache a dedicated engine, without any caller of `resolve_session_factory` changing. Building this seam now, per ADR-003's own reasoning, is cheaper than retrofitting it once real dedicated-DB tenants exist.

## Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant D as core.deps (get_token_payload -> get_db)
    participant DB as Postgres

    C->>D: Request + JWT (contains user_id, tenant_id)
    D->>D: decode_token() — verify signature + expiry
    D->>D: set_tenant_id()/set_current_user_id() ContextVars (tenant_context.py)
    D->>DB: AsyncSessionLocal() opened; SET LOCAL app.current_tenant_id = <tenant_id from token>
    D->>D: require_permission(key) dependency checks cached effective grants
    D->>DB: Execute query (RLS auto-filters by tenant_id; TenantScopedRepository also filters)
    DB-->>D: Rows (only this tenant's)
    D-->>C: Response
    D->>DB: COMMIT
```

**Ordering matters**: `get_token_payload` (which calls `set_tenant_id`) is a dependency of `get_db` — this guarantees tenant context is seeded *before* any database session opens, which is what makes the `SET LOCAL` sequencing correct. See `app.core.deps`'s docstrings.

The `tenant_id` used for `SET LOCAL` always comes from the **verified JWT**, never from a client-supplied header/query param.

## Platform Admin (cross-tenant)

A Platform Admin's JWT carries `platform_admin: true` (set at login when the user's effective grants include `platform.manage_tenants`). `get_db` skips setting `app.current_tenant_id` for platform-admin requests — `/api/v1/platform/*` endpoints operate across tenants deliberately (creating a new tenant, for instance, has no single tenant to scope to) and are gated by `require_platform_admin()` *and* an explicit permission check, not by RLS. Every platform-level write still goes through `write_audit_log`.

## Testing tenant isolation

Two tiers, deliberately independent:

- **`backend/tests/test_tenant_isolation.py`** — SQLite-backed, runs in the default `pytest -m "not postgres"` tier. Validates the **application-layer** half only (SQLite has no RLS/`set_config`; `set_tenant_session_var` is a documented no-op against any non-Postgres engine).
- **`backend/tests/test_tenant_isolation_postgres.py`** — marked `@pytest.mark.postgres`, requires a real, migrated Postgres. Connects directly as the `zonovia_app` role with `asyncpg` (no application code involved at all), sets the wrong tenant's `app.current_tenant_id`, and asserts a raw `SELECT` against another tenant's row returns zero rows — proving the database-layer guarantee independent of any app-layer bug. This is a required, non-optional CI gate (`.github/workflows/ci.yml`'s `postgres-integration` job) — a deliberate deviation from SchoolAssist's own CI, per the architecture blueprint's risk R-9 ("RLS policies missing on a newly added table" is the single most severe class of bug this product can ship).
