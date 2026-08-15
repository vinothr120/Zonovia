"""enable Postgres row-level security for tenant isolation

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Standard tenant-scoped tables: tenant_id is NOT NULL, one flat policy applies.
# See docs/multi-tenancy.md — this is the database-layer half of the two-layer isolation
# guarantee (the other half is TenantScopedRepository's explicit app-layer filtering).
_STANDARD_RLS_TABLES = [
    "users",
    "user_roles",
    "tenant_settings",
    "refresh_tokens",
    "audit_logs",
    "tenant_module_entitlements",
]

# `current_setting(..., true)` returns NULL rather than raising when the session variable
# hasn't been set — meaning a query that runs without a tenant context set (a bug) sees
# ZERO rows rather than erroring or, worse, seeing every tenant's rows. Fail closed.
_STANDARD_POLICY = "tenant_id = current_setting('app.current_tenant_id', true)::uuid"

# roles.tenant_id is nullable — NULL means "system role, visible to every tenant".
_ROLES_POLICY = (
    "tenant_id = current_setting('app.current_tenant_id', true)::uuid OR tenant_id IS NULL"
)


def upgrade() -> None:
    for table in _STANDARD_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE is required because the application's own DB role owns these tables
        # (it ran the migrations) — without FORCE, Postgres exempts the owning role from
        # its own RLS policies, silently defeating the whole mechanism.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_STANDARD_POLICY}) WITH CHECK ({_STANDARD_POLICY})")

    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation_or_system ON roles USING ({_ROLES_POLICY}) WITH CHECK ({_ROLES_POLICY})")

    # tenants, tenant_connection_routes, permissions, role_permissions are intentionally NOT
    # RLS-protected: tenants IS the isolation boundary; tenant_connection_routes is part of
    # the platform-global routing/control plane (see app/tenants/models.py); permissions is
    # a global read-only catalog; role_permissions is never queried without joining through
    # roles, whose policy already governs visibility. See docs/database.md and
    # app/users/models.py.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_or_system ON roles")
    op.execute("ALTER TABLE roles NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles DISABLE ROW LEVEL SECURITY")

    for table in _STANDARD_RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
