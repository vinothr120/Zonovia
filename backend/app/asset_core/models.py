import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import TenantScopedBase


class AssetCategory(TenantScopedBase):
    """Top-level classification (e.g. 'IT Equipment', 'Furniture') — a tenant's own catalog,
    unrelated across tenants."""

    __tablename__ = "asset_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_asset_categories_tenant_name"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AssetType(TenantScopedBase):
    """A category's finer-grained type (e.g. 'Laptop' under 'IT Equipment')."""

    __tablename__ = "asset_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_asset_types_tenant_name"),)

    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_categories.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class Vendor(TenantScopedBase):
    """A tenant's own vendor/supplier catalog — referenced by Asset.vendor_id for purchase
    provenance."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AssetLocation(TenantScopedBase):
    """Adjacency-list location hierarchy — parent_location_id (nullable self-FK) + sort_order
    for stable sibling display. Descendant/ancestor queries use recursive CTEs
    (app/asset_core/repository.py), portable to both SQLite-in-tests and Postgres. No
    materialized path, no ltree, no denormalized depth column — locations are written rarely.
    location_type is free text with no allow-list (a hospital's 'Ward/Bed' and a warehouse's
    'Rack/Bin' share no vocabulary)."""

    __tablename__ = "asset_locations"
    __table_args__ = (UniqueConstraint("tenant_id", "parent_location_id", "name", name="uq_asset_locations_tenant_parent_name"),)

    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Asset(TenantScopedBase):
    """The core tracked entity. Purchase fields live directly here, not a separate 1:1
    PurchaseInfo table. `current_lifecycle_state_id` is a plain nullable UUID column with NO
    FK constraint — the target table (flow.LifecycleStateDefinition) doesn't exist until
    migration 0005 adds the deferred FK (per the blueprint's module dependency direction,
    core -> asset-core -> flow: asset-core must never import flow's code).
    AssetService.create_asset always leaves this NULL; only app.flow.service.FlowService
    ever sets it."""

    __tablename__ = "assets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("asset_types.id"), nullable=False, index=True)
    current_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True, index=True
    )
    current_custodian_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    current_lifecycle_state_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_order_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)


class AssetIdentifier(TenantScopedBase):
    """QR/barcode/serial baseline. `identifier_type` is an open string column with an
    app-level allow-list ("QR", "BARCODE", "SERIAL") today — later phases add
    RFID_EPC/BLE_MAC with no migration, per the plan."""

    __tablename__ = "asset_identifiers"
    __table_args__ = (UniqueConstraint("tenant_id", "identifier_type", "value", name="uq_asset_identifiers_tenant_type_value"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifier_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)


class AssetDocument(TenantScopedBase):
    """File attachment on an asset, via the ported storage abstraction (app/core/storage.py) —
    mirrors SchoolAssist's File model exactly plus asset_id/document_type."""

    __tablename__ = "asset_documents"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_provider: Mapped[str] = mapped_column(String(30), nullable=False, default="local")
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
