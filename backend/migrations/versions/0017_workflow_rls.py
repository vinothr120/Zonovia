"""enable Postgres row-level security for workflow_definitions, approval_step_definitions,
approval_instances, approval_instance_steps, notifications

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-17

Own migration, not merged into 0016 — every prior phase has kept schema and RLS separate
(0001/0002, 0004-0006, 0007/0008, 0009/0010, 0011/0012, 0013-0015). Replicates the exact FORCE
ROW LEVEL SECURITY + fail-closed tenant_id policy pattern from 0002/0006/0008/0010/0012/0015.

No new grants migration is needed: migration 0003's
`ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ... TO zonovia_app` already covers these
tables too, since they were created by the same migration role.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = [
    "workflow_definitions",
    "approval_step_definitions",
    "approval_instances",
    "approval_instance_steps",
    "notifications",
]

# Same fail-closed policy as 0002/0006/0008/0010/0012/0015: current_setting(..., true) returns
# NULL rather than raising when the session variable hasn't been set, so a query that runs
# without a tenant context set sees ZERO rows rather than every tenant's rows.
_STANDARD_POLICY = "tenant_id = current_setting('app.current_tenant_id', true)::uuid"


def upgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE is required because the application's own DB role owns this table (it ran
        # the migrations) — without FORCE, Postgres exempts the owning role from its own RLS
        # policies, silently defeating the whole mechanism. See 0002_enable_rls.py.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_STANDARD_POLICY}) WITH CHECK ({_STANDARD_POLICY})")


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
