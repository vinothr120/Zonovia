import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import Base, IdMixin, TenantScopedMixin, utcnow
from app.core.db_types import JSONVariant


class TrackingEvent(Base, IdMixin, TenantScopedMixin):
    """Append-only scan log — same shape as AuditLog/AssetLifecycleTransition/AssetMovement
    (no timestamp/audit/soft-delete mixins). asset_id stays NOT NULL: Phase 2 only logs
    successfully-resolved scans here — an unresolved scan is recorded via the existing
    audit-log path instead (TrackingService.record_scan writes tracking.scan_unresolved),
    not a nullable FK design. No device_id column yet — Device/DeviceGateway don't exist
    until Phase 6 and there's no near-term caller for it; add it with its first real caller,
    the same convention already established for core/crypto.py and core/storage.py."""

    __tablename__ = "tracking_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scan", server_default="scan")
    # {"raw_value", "normalized_value", "identifier_id", "note"} — see TrackingService.record_scan.
    payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    scanned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
