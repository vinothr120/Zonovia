import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import Base, IdMixin, TenantScopedBase, TenantScopedMixin, utcnow
from app.core.db_types import JSONVariant


class DeviceGateway(TenantScopedBase):
    """A physical/logical reader-fleet credential holder — tracking-engine's own shared
    infrastructure (blueprint's module table: tracking-engine owns device, device_gateway,
    tracking_event, "included wherever any track-* module is licensed"), not RFID-specific.
    api_key_hash mirrors RefreshToken.token_hash exactly (SHA-256 hex — see
    app/tracking/deps.py::_hash_gateway_key); the raw key is never stored and is returned
    exactly once, at creation (DeviceGatewayService.create_gateway's return tuple + the
    router's one-time response). api_key_last4 is non-secret and kept permanently so an admin
    can recognize which key is which without the raw value ever being re-displayed. status is
    terminal once "revoked" — same one-way convention as MaintenanceTicket/InventoryCycle's
    terminal statuses; a revoked gateway's key must stop authenticating immediately (see
    app/tracking/deps.py::get_gateway_payload)."""

    __tablename__ = "device_gateways"
    __table_args__ = (UniqueConstraint("tenant_id", "api_key_hash", name="uq_device_gateways_tenant_api_key_hash"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(TenantScopedBase):
    """Generic reader/sensor abstraction — shared tracking-engine infrastructure a future
    track-vision/track-sense module would reuse, not RFID-specific. device_type is free text
    with NO allow-list (unlike AssetIdentifier.identifier_type) — same convention as
    AssetLocation.location_type: hardcoding RFID-specific values into this generic layer would
    recreate exactly the coupling the abstraction exists to avoid. gateway_id is nullable — a
    device can be registered before being assigned to a gateway."""

    __tablename__ = "devices"

    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("device_gateways.id"), nullable=True, index=True
    )
    device_type: Mapped[str] = mapped_column(String(50), nullable=False, default="RFID_READER", server_default="RFID_READER")
    vendor: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrackingEvent(Base, IdMixin, TenantScopedMixin):
    """Append-only scan log — same shape as AuditLog/AssetLifecycleTransition/AssetMovement
    (no timestamp/audit/soft-delete mixins). asset_id stays NOT NULL: this table only ever
    logs a successfully-resolved scan/read — an unresolved human scan is recorded via the
    audit-log path instead (TrackingService.record_scan writes tracking.scan_unresolved), and
    an unresolved RFID read is recorded via app.track_rfid.models.RfidReadEvent instead (never
    audit_logs — see that model's docstring), not a nullable FK design here.

    device_id (Phase 6) is nullable — every Phase 0-5 caller (human QR/barcode scans) has no
    device, only Phase 6's RfidIngestionService populates it. Added in the same migration file
    that creates `devices` (0013), so the FK is normal, not deferred — see that migration's
    module docstring."""

    __tablename__ = "tracking_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scan", server_default="scan")
    # {"raw_value", "normalized_value", "identifier_id", "note"} — see TrackingService.record_scan.
    payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    scanned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
