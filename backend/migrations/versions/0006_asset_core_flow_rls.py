"""enable Postgres row-level security for the 12 asset-core/flow tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-15

Own migration, not an edit to 0002 (already-applied history). Replicates the exact
FORCE ROW LEVEL SECURITY + fail-closed tenant_id policy pattern from migrations/versions/0002
for every table created by 0004 and 0005 — all 12 are standard tenant-scoped tables (no
nullable tenant_id like `roles`), so the single _STANDARD_POLICY covers all of them.

No new grants migration is needed: migration 0003's
`ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ... TO zonovia_app` already covers every
future table created by the same migration role, which 0004/0005 are — see docs/database.md
and this phase's verification step against a real Postgres (`\\dp` showing zonovia_app's
grants with no manual grant statement here).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = [
    "asset_categories",
    "asset_types",
    "vendors",
    "asset_locations",
    "assets",
    "asset_identifiers",
    "asset_documents",
    "lifecycle_state_definitions",
    "lifecycle_transition_definitions",
    "asset_lifecycle_transitions",
    "asset_assignments",
    "asset_movements",
]

# Same fail-closed policy as 0002_enable_rls.py: current_setting(..., true) returns NULL
# rather than raising when the session variable hasn't been set, so a query that runs
# without a tenant context set sees ZERO rows rather than every tenant's rows.
_STANDARD_POLICY = "tenant_id = current_setting('app.current_tenant_id', true)::uuid"


def upgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE is required because the application's own DB role owns these tables (it ran
        # the migrations) — without FORCE, Postgres exempts the owning role from its own RLS
        # policies, silently defeating the whole mechanism. See 0002_enable_rls.py.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_STANDARD_POLICY}) WITH CHECK ({_STANDARD_POLICY})")


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
