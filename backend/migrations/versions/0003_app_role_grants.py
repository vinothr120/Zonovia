"""grant least-privilege table access to the runtime app role

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-15

The `zonovia_app` role (created by infrastructure/docker/postgres-init.sql before this
migration ever runs) is what the application actually connects as at runtime — never the
migration/superuser role. It does NOT own these tables, so Postgres RLS applies to it
unconditionally: FORCE ROW LEVEL SECURITY (migration 0002) additionally covers the owning
role, but this role was never the owner in the first place. Skipping this role-separation
step would mean the app connects as the table owner/superuser and RLS silently does nothing —
see docs/multi-tenancy.md.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO zonovia_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO zonovia_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM zonovia_app")
