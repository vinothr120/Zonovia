import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import Base, IdMixin, TenantScopedBase, TenantScopedMixin, utcnow

# Guard-clause-validated, not a generic engine — a cycle's status is a fixed,
# non-tenant-configurable workflow, unlike Flow's tenant-configurable lifecycle graph. See
# app/inventory/service.py's start_cycle/complete_cycle/cancel_cycle.
_CYCLE_STATUSES = ("draft", "in_progress", "completed", "cancelled")

# Allow-list enforced in app/inventory/service.py::record_reconciliation, mirroring
# asset_core's AssetIdentifier identifier_type allow-list convention.
_RECONCILIATION_ACTION_TYPES = ("location_corrected", "marked_lost", "acknowledged", "other")


class InventoryCycle(TenantScopedBase):
    """A periodic physical-verification exercise. `root_location_id` NULL means "every asset
    in the tenant"; otherwise it scopes to that location plus every descendant (see
    InventoryService.list_expected_assets). Status is a plain string + hand-written
    guard-clause validation, deliberately not Flow's heavier configurable state machine — see
    the module's implementation plan for the reasoning."""

    __tablename__ = "inventory_cycles"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    root_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InventoryCount(Base, IdMixin, TenantScopedMixin):
    """Append-only verification log — same shape as TrackingEvent/AssetMovement (no
    timestamp/audit/soft-delete mixins), overridden `_base_query` in
    app/inventory/repository.py. Multiple counts per (cycle_id, asset_id) are allowed — a
    re-scan corrects an earlier one; reporting always reads the LATEST count per asset (see
    InventoryService.get_cycle_report's window-function query), never any-count-ever.
    `expected_location_id` is snapshotted from the asset's current_location_id at record time
    (not read live later), so it stays accurate even if Flow moves the asset afterward.
    `tracking_event_id` links back to the TrackingEvent that
    app.tracking.service.TrackingService.record_scan produced for this verification —
    InventoryService.record_verification calls that service directly rather than
    reimplementing scan resolution."""

    __tablename__ = "inventory_counts"

    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory_cycles.id"), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expected_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True
    )
    found_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True
    )
    has_discrepancy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    condition_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tracking_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tracking_events.id"), nullable=True
    )


class ReconciliationAction(Base, IdMixin, TenantScopedMixin):
    """Append-only reconciliation-decision log, same shape as InventoryCount. Keyed by
    (cycle_id, asset_id) rather than an InventoryCount FK — a "missing" asset (never scanned
    during the cycle) has zero InventoryCount rows but must still be reconcilable. Purely a
    record of the decision: does NOT call app.flow.service.FlowService or otherwise mutate
    the asset's own current_location_id/current_lifecycle_state_id — see the module's
    implementation plan's "No dependency on flow" design decision. Actually executing a
    decision (moving the asset, changing its lifecycle state) is a separate, explicit
    follow-up call against Flow's own already-permissioned endpoints."""

    __tablename__ = "reconciliation_actions"

    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory_cycles.id"), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
