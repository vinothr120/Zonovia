"""inventory schema — Phase 3: inventory_cycles, inventory_counts, reconciliation_actions

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-15

assets.id, asset_locations.id, tracking_events.id, and users.id all already exist by this
point, so every FK here is a normal (non-deferred) FK — no lifecycle_state_id-style dance.
inventory_cycles is created first, then inventory_counts + reconciliation_actions, both of
which reference it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id_col():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _timestamp_cols():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _audit_cols():
    return [
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def _soft_delete_col():
    return sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)


def _tenant_id_col():
    return sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "inventory_cycles",
        _id_col(),
        _tenant_id_col(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("root_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    # Append-only history — same shape as audit_logs/asset_lifecycle_transitions/
    # tracking_events (no timestamp/audit/soft-delete columns).
    op.create_table(
        "inventory_counts",
        _id_col(),
        _tenant_id_col(),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inventory_cycles.id"), nullable=False, index=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expected_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True),
        sa.Column("found_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True),
        sa.Column("has_discrepancy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("condition_note", sa.String(1000), nullable=True),
        sa.Column("tracking_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tracking_events.id"), nullable=True),
    )
    op.create_index("ix_inventory_counts_verified_at", "inventory_counts", ["verified_at"])

    # Append-only history, same shape as inventory_counts. Keyed by (cycle_id, asset_id), NOT
    # an inventory_counts FK — a "missing" asset (never scanned) has zero counts but must
    # still be reconcilable. See app/inventory/models.py::ReconciliationAction's docstring.
    op.create_table(
        "reconciliation_actions",
        _id_col(),
        _tenant_id_col(),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inventory_cycles.id"), nullable=False, index=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_reconciliation_actions_resolved_at", "reconciliation_actions", ["resolved_at"])


def downgrade() -> None:
    op.drop_table("reconciliation_actions")
    op.drop_table("inventory_counts")
    op.drop_table("inventory_cycles")
