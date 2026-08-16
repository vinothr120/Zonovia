"""track_rfid schema — Phase 6: rfid_tags, rfid_read_events

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-16

asset_identifiers.id, assets.id (migration 0004), device_gateways.id, devices.id (migration
0013), and tracking_events.id (migration 0007) all already exist by this point, so every FK
here is a normal (non-deferred) FK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
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
    # 1:1 supplement to asset_identifiers (identifier_type="RFID_EPC") — asset_identifier_id
    # is UNIQUE. Never the sole EPC->asset lookup path; see app/track_rfid/models.py.
    op.create_table(
        "rfid_tags",
        _id_col(),
        _tenant_id_col(),
        sa.Column(
            "asset_identifier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_identifiers.id"), nullable=False, index=True
        ),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False, index=True),
        sa.Column("tag_type", sa.String(20), nullable=False, server_default="passive"),
        sa.Column("last_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("last_rssi", sa.Integer(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("asset_identifier_id", name="uq_rfid_tags_asset_identifier_id"),
    )

    # Append-only — same shape as tracking_events/audit_logs (no timestamp/audit/soft-delete
    # columns). asset_id/tracking_event_id are nullable, unlike tracking_events.asset_id —
    # every raw read is recorded here, resolved or not; see the model's docstring.
    op.create_table(
        "rfid_read_events",
        _id_col(),
        _tenant_id_col(),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("device_gateways.id"), nullable=False, index=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id"), nullable=False, index=True),
        sa.Column("tag_epc", sa.String(255), nullable=False, index=True),
        sa.Column("rssi", sa.Integer(), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=True, index=True),
        sa.Column(
            "tracking_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tracking_events.id"), nullable=True, index=True
        ),
    )
    op.create_index("ix_rfid_read_events_read_at", "rfid_read_events", ["read_at"])


def downgrade() -> None:
    op.drop_table("rfid_read_events")
    op.drop_table("rfid_tags")
