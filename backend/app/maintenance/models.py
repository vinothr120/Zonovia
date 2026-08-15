import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import TenantScopedBase

# Guard-clause-validated, not a generic engine — same fixed, non-tenant-configurable workflow
# convention as app.inventory.models.InventoryCycle's _CYCLE_STATUSES, deliberately not Flow's
# heavier tenant-configurable lifecycle graph. See MaintenanceService.start_ticket/
# complete_ticket/cancel_ticket.
_TICKET_STATUSES = ("open", "in_progress", "completed", "cancelled")

# Allow-list enforced in app/maintenance/service.py::create_ticket/update_ticket.
_TICKET_PRIORITIES = ("low", "medium", "high", "urgent")


class MaintenanceTicket(TenantScopedBase):
    """A single maintenance/repair request against an asset. `service_schedule_id` is
    optional traceability only — linking a ticket to the ServiceSchedule it happened to
    relate to does NOT mean completing it records a service; see
    MaintenanceService.complete_ticket and the module's implementation plan's
    "ServiceSchedule and MaintenanceTicket stay uncoupled" design decision.
    `cost` is a single nullable field, not separate estimated/actual — a deliberate
    simplification, no approval gate by design (real budget sign-off is a future
    workflow-engine concern, not a permission-bundle hack now)."""

    __tablename__ = "maintenance_tickets"

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    service_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_schedules.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class Warranty(TenantScopedBase):
    """1:1 per asset (blueprint §11's ER diagram) — asset_id is UNIQUE. Lives in
    app.maintenance, not app.asset_core, despite the blueprint's §6/§7 listing it under Asset
    Core — resolved in favor of §29's packaging table and §30's roadmap grouping, both of
    which place Warranty alongside Maintenance under the same licensed module; see the
    module's implementation plan for the full reasoning. Follows TenantService.upsert_setting's
    get-or-create-then-mutate shape (GET+PUT, no DELETE) rather than InventoryCycle's status
    lifecycle. `is_expired`/`days_remaining` are computed at read time in service.py, never
    stored."""

    __tablename__ = "warranties"
    __table_args__ = (UniqueConstraint("asset_id", name="uq_warranties_asset_id"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True)
    warranty_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    terms: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class ServiceSchedule(TenantScopedBase):
    """Pure per-asset configuration — no status column, no uniqueness on asset_id (multiple
    schedules per asset are allowed, e.g. "quarterly filter change" and "annual inspection" on
    the same asset). Structurally closer to Vendor/AssetCategory (standard soft-delete) than to
    an event-log entity. `next_due_at`/`is_overdue` are never stored — computed in service.py
    as last_serviced_at + interval_days, or created_at + interval_days if never serviced (see
    MaintenanceService's module-level `_schedule_due_info` helper)."""

    __tablename__ = "service_schedules"

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    last_serviced_at: Mapped[date | None] = mapped_column(Date, nullable=True)
