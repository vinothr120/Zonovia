"""flow schema — Phase 1: configurable lifecycle engine, custody, movement

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-15

Creates flow's 5 tables, THEN adds the FK from assets.current_lifecycle_state_id that
migration 0004 deliberately left off (its target table, lifecycle_state_definitions, is
created in this migration) — see 0004's module docstring for why the ordering matters.
downgrade() reverses in the opposite order: drop the FK first, then drop flow's tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
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


# Postgres identifiers cap out at 63 bytes — the "obvious" fully-descriptive name
# (fk_assets_current_lifecycle_state_id_lifecycle_state_definitions, 67 chars) exceeds that.
_ASSETS_LIFECYCLE_FK_NAME = "fk_assets_current_lifecycle_state_id"


def upgrade() -> None:
    op.create_table(
        "lifecycle_state_definitions",
        _id_col(),
        _tenant_id_col(),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("is_initial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "key", name="uq_lifecycle_state_definitions_tenant_key"),
    )

    op.create_table(
        "lifecycle_transition_definitions",
        _id_col(),
        _tenant_id_col(),
        sa.Column(
            "from_state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lifecycle_state_definitions.id"), nullable=False, index=True
        ),
        sa.Column(
            "to_state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lifecycle_state_definitions.id"), nullable=False, index=True
        ),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "from_state_id", "to_state_id", name="uq_lifecycle_transition_definitions_tenant_edge"),
    )

    # Append-only history — same shape as audit_logs (no timestamps/soft-delete mixins).
    op.create_table(
        "asset_lifecycle_transitions",
        _id_col(),
        _tenant_id_col(),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("from_state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lifecycle_state_definitions.id"), nullable=True),
        sa.Column("to_state_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lifecycle_state_definitions.id"), nullable=False),
        sa.Column("transitioned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
    )
    op.create_index("ix_asset_lifecycle_transitions_transitioned_at", "asset_lifecycle_transitions", ["transitioned_at"])

    # Mutable history (TenantScopedBase minus soft-delete) — unassigned_at IS NULL is current
    # custody; nothing is deleted, only closed out.
    op.create_table(
        "asset_assignments",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("custodian_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
    )

    # Append-only history — same shape as audit_logs.
    op.create_table(
        "asset_movements",
        _id_col(),
        _tenant_id_col(),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("from_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True),
        sa.Column("to_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=False),
        sa.Column("moved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
    )
    op.create_index("ix_asset_movements_moved_at", "asset_movements", ["moved_at"])

    # The deferred FK left off by migration 0004 — lifecycle_state_definitions now exists.
    op.create_foreign_key(
        _ASSETS_LIFECYCLE_FK_NAME, "assets", "lifecycle_state_definitions", ["current_lifecycle_state_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(_ASSETS_LIFECYCLE_FK_NAME, "assets", type_="foreignkey")
    op.drop_table("asset_movements")
    op.drop_table("asset_assignments")
    op.drop_table("asset_lifecycle_transitions")
    op.drop_table("lifecycle_transition_definitions")
    op.drop_table("lifecycle_state_definitions")
