import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApprovalStepDefinitionCreate(BaseModel):
    sequence_order: int
    approver_user_id: uuid.UUID | None = None
    approver_role_key: str | None = None


class WorkflowDefinitionCreate(BaseModel):
    entity_type: str
    name: str
    is_active: bool = True
    condition_attribute: str | None = None
    condition_operator: str | None = None
    condition_value: Any | None = None
    steps: list[ApprovalStepDefinitionCreate]


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    condition_attribute: str | None = None
    condition_operator: str | None = None
    condition_value: Any | None = None


class WorkflowDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    name: str
    is_active: bool
    condition_attribute: str | None
    condition_operator: str | None
    condition_value: Any | None
    created_at: datetime


class ApprovalStepDefinitionAdd(BaseModel):
    sequence_order: int
    approver_user_id: uuid.UUID | None = None
    approver_role_key: str | None = None


class ApprovalStepDefinitionUpdate(BaseModel):
    """approver_user_id/approver_role_key deliberately deviate from the ambient "None = don't
    touch" convention — the router reads `model_fields_set` to tell "omitted" from "sent as
    null" and passes WorkflowService.UNSET for an omitted field. See
    WorkflowService.update_step's docstring."""

    sequence_order: int | None = None
    approver_user_id: uuid.UUID | None = None
    approver_role_key: str | None = None


class ApprovalStepDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_definition_id: uuid.UUID
    sequence_order: int
    approver_user_id: uuid.UUID | None
    approver_role_key: str | None
    created_at: datetime


class EvaluateInstanceRequest(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    context: dict[str, Any] = {}


class ApprovalInstanceStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    approval_instance_id: uuid.UUID
    step_definition_id: uuid.UUID | None
    sequence_order: int
    approver_user_id: uuid.UUID | None
    approver_role_key: str | None
    status: str
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime


class ApprovalInstanceRead(BaseModel):
    """Nested Read — the instance plus its steps in one payload, the same "router merges
    nested data" convention as app.maintenance.router's ScheduleDueReport/_schedule_read_dict."""

    id: uuid.UUID
    workflow_definition_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    status: str
    current_sequence_order: int | None
    context: dict[str, Any] | None
    requested_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    steps: list[ApprovalInstanceStepRead]


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_user_id: uuid.UUID
    type: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime
