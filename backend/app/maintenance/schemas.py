import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MaintenanceTicketCreate(BaseModel):
    asset_id: uuid.UUID
    service_schedule_id: uuid.UUID | None = None  # traceability only — see models.py
    title: str
    description: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None
    cost: Decimal | None = None


class MaintenanceTicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None
    cost: Decimal | None = None


class MaintenanceTicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    service_schedule_id: uuid.UUID | None
    title: str
    description: str | None
    status: str
    priority: str | None
    reported_by: uuid.UUID | None
    assigned_to: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    cost: Decimal | None
    created_at: datetime


class TicketCancelRequest(BaseModel):
    note: str | None = None


class TicketCompleteRequest(BaseModel):
    resolution_note: str | None = None


class WarrantyUpsert(BaseModel):
    vendor_id: uuid.UUID | None = None
    warranty_type: str | None = None
    start_date: date
    end_date: date
    terms: str | None = None


class WarrantyRead(BaseModel):
    """Not built via from_attributes off the Warranty ORM object directly — is_expired/
    days_remaining are computed at read time (see service.py's module-level
    `_warranty_status`) and merged in by the router, the same "computed, not stored"
    convention as InventoryService.get_cycle_report/CycleReport."""

    id: uuid.UUID
    asset_id: uuid.UUID
    vendor_id: uuid.UUID | None
    warranty_type: str | None
    start_date: date
    end_date: date
    terms: str | None
    is_expired: bool
    days_remaining: int
    updated_at: datetime


class ServiceScheduleCreate(BaseModel):
    asset_id: uuid.UUID
    name: str
    interval_days: int


class ServiceScheduleUpdate(BaseModel):
    name: str | None = None
    interval_days: int | None = None


class RecordServiceRequest(BaseModel):
    serviced_at: date | None = None  # defaults to today if omitted


class ServiceScheduleRead(BaseModel):
    """Same "computed at read time, merged in by the router" shape as WarrantyRead — see
    service.py's module-level `_schedule_due_info`."""

    id: uuid.UUID
    asset_id: uuid.UUID
    name: str
    interval_days: int
    last_serviced_at: date | None
    next_due_at: date
    is_overdue: bool
    created_at: datetime


class ScheduleDueReport(BaseModel):
    overdue: list[ServiceScheduleRead]
    upcoming: list[ServiceScheduleRead]
