import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InventoryCycleCreate(BaseModel):
    name: str
    description: str | None = None
    root_location_id: uuid.UUID | None = None  # None = every asset in the tenant


class InventoryCycleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    root_location_id: uuid.UUID | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None


class InventoryVerificationRequest(BaseModel):
    """Body of POST .../counts — reuses app.tracking.service.TrackingService.record_scan for
    scan resolution, so identifier_type/value match ScanRequest's shape exactly."""

    identifier_type: str
    value: str
    found_location_id: uuid.UUID | None = None  # defaults to the asset's expected location if omitted
    note: str | None = None


class InventoryCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cycle_id: uuid.UUID
    asset_id: uuid.UUID
    verified_by: uuid.UUID | None
    verified_at: datetime
    expected_location_id: uuid.UUID | None
    found_location_id: uuid.UUID | None
    has_discrepancy: bool
    condition_note: str | None
    tracking_event_id: uuid.UUID | None


class ReconciliationRequest(BaseModel):
    asset_id: uuid.UUID
    action_type: str
    note: str | None = None


class ReconciliationActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cycle_id: uuid.UUID
    asset_id: uuid.UUID
    action_type: str
    note: str | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime


class CycleReport(BaseModel):
    """InventoryService.get_cycle_report's return shape — computed on demand, not stored,
    same convention as FlowService.get_asset_history."""

    cycle_id: uuid.UUID
    expected_asset_ids: list[uuid.UUID]
    verified_asset_ids: list[uuid.UUID]
    missing_asset_ids: list[uuid.UUID]
    discrepancies: list[InventoryCountRead]
