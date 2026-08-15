import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LifecycleStateDefinitionCreate(BaseModel):
    key: str
    label: str
    is_initial: bool = False
    is_terminal: bool = False
    sort_order: int = 0


class LifecycleStateDefinitionUpdate(BaseModel):
    label: str | None = None
    is_initial: bool | None = None
    is_terminal: bool | None = None
    sort_order: int | None = None


class LifecycleStateDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str
    is_initial: bool
    is_terminal: bool
    sort_order: int


class LifecycleTransitionDefinitionCreate(BaseModel):
    from_state_id: uuid.UUID
    to_state_id: uuid.UUID


class LifecycleTransitionDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_state_id: uuid.UUID
    to_state_id: uuid.UUID


class AssetTransitionRequest(BaseModel):
    to_state_id: uuid.UUID
    note: str | None = None


class AssetLifecycleTransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    from_state_id: uuid.UUID | None
    to_state_id: uuid.UUID
    transitioned_by: uuid.UUID | None
    transitioned_at: datetime
    note: str | None


class AssetAssignRequest(BaseModel):
    custodian_user_id: uuid.UUID
    note: str | None = None


class AssetUnassignRequest(BaseModel):
    note: str | None = None


class AssetAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    custodian_user_id: uuid.UUID
    assigned_at: datetime
    unassigned_at: datetime | None
    assigned_by: uuid.UUID | None
    note: str | None


class AssetMoveRequest(BaseModel):
    to_location_id: uuid.UUID
    note: str | None = None


class AssetMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    from_location_id: uuid.UUID | None
    to_location_id: uuid.UUID
    moved_at: datetime
    moved_by: uuid.UUID | None
    note: str | None


class AssetHistoryEntry(BaseModel):
    """One chronological feed merging lifecycle transitions, assignments, and movements —
    FlowService.get_asset_history's return shape."""

    entry_type: str  # "lifecycle_transition" | "assignment" | "movement"
    occurred_at: datetime
    data: dict[str, Any]
