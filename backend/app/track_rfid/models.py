import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import Base, IdMixin, TenantScopedBase, TenantScopedMixin, utcnow

# Allow-list enforced in app/track_rfid/service.py::RfidTagService.register_tag, mirroring
# maintenance's _TICKET_PRIORITIES / inventory's _RECONCILIATION_ACTION_TYPES convention.
_TAG_TYPES = ("passive", "active")


class RfidTag(TenantScopedBase):
    """Supplements AssetIdentifier(identifier_type="RFID_EPC") — never replaces its
    resolution role. asset_identifier_id is the sole EPC->asset lookup path
    (AssetIdentifierRepository.get_by_type_value, reused verbatim by RfidIngestionService);
    this table is a 1:1 side table (asset_identifier_id UNIQUE) holding only genuinely
    RFID-specific metadata that QR/Barcode identifiers have no use for. asset_id is
    denormalized (matches the direct-FK convention every other module uses, e.g.
    MaintenanceTicket.asset_id) rather than requiring a join through asset_identifiers for
    every read. asset_core's generic POST /assets/{id}/identifiers can still add a bare
    RFID_EPC identifier with no RfidTag row here — same non-exclusive relationship QR/Barcode
    identifiers already have; RfidTag is opt-in enrichment, not a requirement.
    last_device_id/last_rssi/last_read_at are a live snapshot, updated by
    RfidIngestionService.ingest_batch on every resolved read of this tag — NOT a historical
    log (RfidReadEvent below is the append-only log)."""

    __tablename__ = "rfid_tags"
    __table_args__ = (UniqueConstraint("asset_identifier_id", name="uq_rfid_tags_asset_identifier_id"),)

    asset_identifier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_identifiers.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    tag_type: Mapped[str] = mapped_column(String(20), nullable=False, default="passive", server_default="passive")
    last_device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    last_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RfidReadEvent(Base, IdMixin, TenantScopedMixin):
    """Every raw RFID read, resolved or not — append-only, same shape as TrackingEvent/
    AuditLog (no timestamp/audit/soft-delete mixins). Unlike TrackingEvent.asset_id (NOT
    NULL), asset_id here is nullable: an unresolved read (an EPC with no matching
    AssetIdentifier) still gets a row, with asset_id=None and tracking_event_id=None — this
    table itself IS the durable forensic record for unresolved reads; nothing else is written
    for them (deliberately NOT an audit_logs row — Phase 2's tracking.scan_unresolved makes
    sense at human-scan volume, but at reader volume a misconfigured reader alone could
    produce dozens of unresolved pings/second, which would flood a table meant for curated,
    reviewable history; see the module's implementation plan).

    tracking_event_id (nullable FK) is both the resolution flag AND full forensic
    traceability: a resolved-and-deduped read links to the existing TrackingEvent it matched;
    a resolved-and-new read links to the TrackingEvent it just created; an unresolved read
    leaves it NULL. gateway_id comes directly from the authenticated GatewayPayload, not
    derived via device.gateway_id — avoids staleness if a device is ever reassigned to a
    different gateway after this read was captured."""

    __tablename__ = "rfid_read_events"

    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("device_gateways.id"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=False, index=True)
    tag_epc: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=True, index=True)
    tracking_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tracking_events.id"), nullable=True, index=True
    )
