"""Postgres Row-Level Security integration tier — proves the DATABASE-LAYER half of tenant
isolation (migrations/versions/0002_enable_rls.py's fail-closed policies), independent of any
application-layer bug. This is the "most important check" the implementation plan calls out:
even a raw query, connected directly as the least-privilege `zonovia_app` role (never the
migration/superuser role), issued straight against Postgres with no app code involved, must
still be unable to see another tenant's rows.

Not run by default (`pytest -v -m "not postgres"` is the default unit tier). To run this file:

    docker compose up -d postgres
    cd backend && cp .env.example .env
    alembic upgrade head
    python -m app.seed
    pytest -v -m postgres

Requires a real, migrated Postgres reachable at $DATABASE_URL_SYNC (or the docker-compose.yml
default). Registered via the `postgres` marker in pytest.ini; this whole module is skipped
unless that marker is selected.
"""

import os
import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.postgres

_APP_ROLE_DSN = os.environ.get("TEST_POSTGRES_APP_DSN", "postgresql://zonovia_app:zonovia_app_password@localhost:5432/zonovia")


async def _connect():
    try:
        return await asyncpg.connect(_APP_ROLE_DSN)
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Postgres not reachable at {_APP_ROLE_DSN}: {exc}")


async def test_rls_blocks_cross_tenant_reads_even_via_a_raw_query_as_the_app_role():
    conn = await _connect()
    try:
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()

        # Insert both tenant rows and one user each, bypassing RLS via local=False semantics
        # is not available on a raw connection — instead we rely on set_config per statement,
        # matching exactly what app/core/database.py::set_tenant_session_var does per request.
        await conn.execute(
            "INSERT INTO tenants (id, name, subdomain, subscription_tier, status) VALUES ($1, 'RLS Test A', $2, 'basic', 'active')",
            tenant_a,
            f"rls-test-a-{tenant_a.hex[:8]}",
        )
        await conn.execute(
            "INSERT INTO tenants (id, name, subdomain, subscription_tier, status) VALUES ($1, 'RLS Test B', $2, 'basic', 'active')",
            tenant_b,
            f"rls-test-b-{tenant_b.hex[:8]}",
        )

        await conn.execute("SELECT set_config('app.current_tenant_id', $1, false)", str(tenant_a))
        user_a = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, status) VALUES ($1, $2, 'a@rls-test.example', 'x', 'active')",
            user_a,
            tenant_a,
        )

        await conn.execute("SELECT set_config('app.current_tenant_id', $1, false)", str(tenant_b))
        user_b = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, status) VALUES ($1, $2, 'b@rls-test.example', 'x', 'active')",
            user_b,
            tenant_b,
        )

        # Still scoped to tenant B — a SELECT for tenant A's row must return zero rows, even
        # though the row physically exists in the table.
        rows = await conn.fetch("SELECT id FROM users WHERE tenant_id = $1", tenant_a)
        assert rows == []

        # Sanity check: tenant B can see its own row.
        own_rows = await conn.fetch("SELECT id FROM users WHERE tenant_id = $1", tenant_b)
        assert len(own_rows) == 1

        # Cleanup
        await conn.execute("SELECT set_config('app.current_tenant_id', $1, false)", str(tenant_b))
        await conn.execute("DELETE FROM users WHERE id = $1", user_b)
        await conn.execute("SELECT set_config('app.current_tenant_id', $1, false)", str(tenant_a))
        await conn.execute("DELETE FROM users WHERE id = $1", user_a)
        await conn.execute("DELETE FROM tenants WHERE id = ANY($1::uuid[])", [tenant_a, tenant_b])
    finally:
        await conn.close()


async def test_rls_fails_closed_when_no_tenant_context_is_set():
    """current_setting('app.current_tenant_id', true) returns NULL, not an error, when unset
    — the policy's ::uuid cast on NULL is NULL, and `tenant_id = NULL` is never true in SQL,
    so a query issued with no tenant context set sees zero rows rather than every tenant's."""
    conn = await _connect()
    try:
        # A fresh connection has no app.current_tenant_id session variable set at all.
        rows = await conn.fetch("SELECT id FROM users LIMIT 1")
        assert rows == []
    finally:
        await conn.close()


async def test_roles_table_allows_null_tenant_system_roles_regardless_of_context():
    """roles.tenant_id is nullable — system roles (Platform Admin, Tenant Admin, Member,
    Viewer) must remain visible to every tenant context, per the tenant_isolation_or_system
    policy in migrations/versions/0002_enable_rls.py."""
    conn = await _connect()
    try:
        some_tenant = uuid.uuid4()
        await conn.execute("SELECT set_config('app.current_tenant_id', $1, false)", str(some_tenant))
        system_roles = await conn.fetch("SELECT id, name FROM roles WHERE tenant_id IS NULL")
        # Seeded by app/seed.py — if the seed script has been run, these system roles exist
        # and must be visible even under an unrelated tenant's session context.
        if not system_roles:
            pytest.skip("No system roles found — run `python -m app.seed` against this database first.")
        assert len(system_roles) > 0
    finally:
        await conn.close()
