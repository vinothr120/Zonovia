"""asset core schema — Phase 1: categories, types, vendors, locations, assets, identifiers, documents

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-15

`assets.current_lifecycle_state_id` is created here as a plain nullable indexed UUID column
WITHOUT an FK constraint — its target table (lifecycle_state_definitions) doesn't exist until
migration 0005, per the blueprint's module dependency direction (core -> asset-core -> flow):
asset-core must never depend on flow. Migration 0005 creates flow's tables and then adds the
deferred FK via `op.create_foreign_key`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
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
        "asset_categories",
        _id_col(),
        _tenant_id_col(),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_asset_categories_tenant_name"),
    )

    op.create_table(
        "asset_types",
        _id_col(),
        _tenant_id_col(),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_categories.id"), nullable=False, index=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_asset_types_tenant_name"),
    )

    op.create_table(
        "vendors",
        _id_col(),
        _tenant_id_col(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "asset_locations",
        _id_col(),
        _tenant_id_col(),
        sa.Column("parent_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_type", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "parent_location_id", "name", name="uq_asset_locations_tenant_parent_name"),
    )

    op.create_table(
        "assets",
        _id_col(),
        _tenant_id_col(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_types.id"), nullable=False, index=True),
        sa.Column(
            "current_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_locations.id"), nullable=True, index=True
        ),
        sa.Column("current_custodian_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True, index=True),
        # No FK yet — see this migration's module docstring. Added by migration 0005.
        sa.Column("current_lifecycle_state_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendors.id"), nullable=True, index=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("purchase_order_ref", sa.String(150), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "asset_identifiers",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("identifier_type", sa.String(30), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "identifier_type", "value", name="uq_asset_identifiers_tenant_type_value"),
    )

    op.create_table(
        "asset_documents",
        _id_col(),
        _tenant_id_col(),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("storage_provider", sa.String(30), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )


def downgrade() -> None:
    op.drop_table("asset_documents")
    op.drop_table("asset_identifiers")
    op.drop_table("assets")
    op.drop_table("asset_locations")
    op.drop_table("vendors")
    op.drop_table("asset_types")
    op.drop_table("asset_categories")
