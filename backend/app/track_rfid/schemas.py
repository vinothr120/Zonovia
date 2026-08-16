import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RfidTagCreate(BaseModel):
    asset_id: uuid.UUID
    epc: str
    tag_type: str = "passive"


class RfidTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_identifier_id: uuid.UUID
    asset_id: uuid.UUID
    tag_type: str
    last_device_id: uuid.UUID | None
    last_rssi: int | None
    last_read_at: datetime | None
    created_at: datetime
    epc: str  # merged in by the router from the linked AssetIdentifier — see
    # app/track_rfid/router.py's _tag_read_dict, same "computed/joined at read time" pattern
    # as app.maintenance.router._warranty_read_dict.


class RfidReadEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    read_at: datetime
    gateway_id: uuid.UUID
    device_id: uuid.UUID
    tag_epc: str
    rssi: int | None
    asset_id: uuid.UUID | None
    tracking_event_id: uuid.UUID | None


class RfidRawRead(BaseModel):
    """One raw reader ping, as submitted in a batch to POST /rfid/ingest."""

    device_id: uuid.UUID
    tag_epc: str
    rssi: int | None = None


class RfidIngestRequest(BaseModel):
    reads: list[RfidRawRead]


class RfidIngestResponse(BaseModel):
    """Live counts, not per-read echoes — deliberately not a copy of Phase 2's audited
    scan-unresolved behavior; see RfidIngestionService.ingest_batch / RfidReadEvent's
    docstrings for why."""

    resolved: int
    unresolved: int
    invalid: int
    new_tracking_events: int
    deduped: int
