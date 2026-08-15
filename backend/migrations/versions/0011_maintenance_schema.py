"""maintenance schema — Phase 4: warranties, service_schedules, maintenance_tickets

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-16

assets.id, vendors.id, and users.id all already exist by this point, so every FK here is a
normal (non-deferred) FK — no lifecycle_state_id-style dance. Order matters only for
maintenance_tickets, which FKs service_schedules.id: warranties -> service_schedules ->
maintenance_tickets. app.maintenance never imports app.flow, so there is no FK to any flow
table here either.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
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
    # 1:1 per asset (blueprint §11's ER diagram) — asset_id is UNIQUE.
    op.create_table(
        "warranties",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("warranty_type", sa.String(100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("terms", sa.String(2000), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("asset_id", name="uq_warranties_asset_id"),
    )

    # Pure per-asset configuration, no uniqueness on asset_id — multiple schedules per asset
    # are allowed.
    op.create_table(
        "service_schedules",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("last_serviced_at", sa.Date(), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "maintenance_tickets",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column(
            "service_schedule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("service_schedules.id"), nullable=True, index=True
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.String(2000), nullable=True),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )


def downgrade() -> None:
    op.drop_table("maintenance_tickets")
    op.drop_table("service_schedules")
    op.drop_table("warranties")
