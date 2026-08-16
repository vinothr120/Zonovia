import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScanRequest(BaseModel):
    identifier_type: str
    value: str
    note: str | None = None


class AssetSummary(BaseModel):
    """Just enough for the frontend to show what was scanned without a second round trip —
    not the full AssetRead (asset_core owns that shape)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    asset_type_id: uuid.UUID
    current_location_id: uuid.UUID | None
    current_lifecycle_state_id: uuid.UUID | None
    current_custodian_id: uuid.UUID | None


class TrackingEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    provider_type: str
    event_type: str
    payload: dict[str, Any]
    scanned_by: uuid.UUID | None
    occurred_at: datetime


class ScanResponse(BaseModel):
    """The shape of POST /tracking/scan's 201 `data` field."""

    asset: AssetSummary
    tracking_event: TrackingEventRead


# -- device gateways / devices (Phase 6) -----------------------------------------------------


class DeviceGatewayCreate(BaseModel):
    name: str
    location_id: uuid.UUID | None = None


class DeviceGatewayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location_id: uuid.UUID | None
    status: str
    api_key_last4: str
    last_seen_at: datetime | None
    created_at: datetime


class DeviceGatewayCreateResponse(BaseModel):
    """The shape of POST /tracking/gateways's 201 `data` field — the ONLY response that ever
    carries the raw api_key. Every later read (GET, list) returns DeviceGatewayRead alone,
    which has api_key_last4 only."""

    gateway: DeviceGatewayRead
    api_key: str


class DeviceCreate(BaseModel):
    device_type: str = "RFID_READER"
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gateway_id: uuid.UUID | None
    device_type: str
    vendor: str | None
    model: str | None
    serial_number: str | None
    status: str
    last_seen_at: datetime | None
    created_at: datetime
