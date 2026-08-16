"""tracking engine devices schema — Phase 6: device_gateways, devices, tracking_events.device_id

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-16

device_gateways and devices are new tenant-scoped tables. tracking_events.device_id (deferred
since Phase 2 — see app/tracking/models.py::TrackingEvent's prior docstring) is added by THIS
same migration file, AFTER devices is created above it — so, unlike migration 0004's
assets.current_lifecycle_state_id (a genuine forward reference spanning two migration files,
resolved by migration 0005), the FK here is a normal (non-deferred) op.create_foreign_key call.
See the module's implementation plan's "same-migration addition, not a cross-migration deferred
FK" design decision.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
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


_TRACKING_EVENTS_DEVICE_FK_NAME = "fk_tracking_events_device_id"


def upgrade() -> None:
    op.create_table(
        "device_gateways",
        _id_col(),
        _tenant_id_col(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("api_key_last4", sa.String(4), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "api_key_hash", name="uq_device_gateways_tenant_api_key_hash"),
    )

    op.create_table(
        "devices",
        _id_col(),
        _tenant_id_col(),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("device_gateways.id"), nullable=True, index=True),
        sa.Column("device_type", sa.String(50), nullable=False, server_default="RFID_READER"),
        sa.Column("vendor", sa.String(150), nullable=True),
        sa.Column("model", sa.String(150), nullable=True),
        sa.Column("serial_number", sa.String(150), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    # The deferred column left off since migration 0007 — devices now exists (created above,
    # in this same migration file), so this is a normal FK, not a cross-migration deferred one.
    op.add_column("tracking_events", sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_tracking_events_device_id", "tracking_events", ["device_id"])
    op.create_foreign_key(_TRACKING_EVENTS_DEVICE_FK_NAME, "tracking_events", "devices", ["device_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(_TRACKING_EVENTS_DEVICE_FK_NAME, "tracking_events", type_="foreignkey")
    op.drop_index("ix_tracking_events_device_id", "tracking_events")
    op.drop_column("tracking_events", "device_id")
    op.drop_table("devices")
    op.drop_table("device_gateways")
