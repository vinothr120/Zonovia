"""tracking schema — Phase 2: tracking_events

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15

assets.id already exists (migration 0004), so tracking_events.asset_id gets a normal FK with
no deferred-FK problem, unlike migration 0004/0005's lifecycle_state_id dance.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id_col():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _tenant_id_col():
    return sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    # Append-only history — same shape as audit_logs/asset_lifecycle_transitions/asset_movements
    # (no timestamp/audit/soft-delete columns).
    op.create_table(
        "tracking_events",
        _id_col(),
        _tenant_id_col(),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("provider_type", sa.String(30), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False, server_default="scan"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("scanned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_tracking_events_occurred_at", "tracking_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("tracking_events")
