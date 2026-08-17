import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import TenantScopedBase
from app.core.db_types import JSONVariant

# Allow-lists enforced in app/workflow/service.py — not DB CHECK constraints, same
# fixed-vocabulary-in-service convention as app.maintenance.models._TICKET_STATUSES/
# _TICKET_PRIORITIES.
_CONDITION_OPERATORS = ("eq", "ne", "gt", "gte", "lt", "lte")
_INSTANCE_STATUSES = ("pending", "approved", "rejected", "cancelled")
_STEP_STATUSES = ("pending", "approved", "rejected", "skipped")
_NOTIFICATION_TYPES = ("approval_pending", "approval_resolved")


class WorkflowDefinition(TenantScopedBase):
    """The tenant-configured "when does entity_type X need approval" rule. `entity_type` is a
    free-text tag (e.g. "maintenance_ticket") — no FK, since this is a standalone engine not
    wired into any other module's write path this increment (see the module's implementation
    plan). The condition is three nullable columns rather than a JSON rule blob — genuinely
    simple, not a DSL — all-three-or-none enforced in WorkflowService.create_definition/
    update_definition, condition_operator restricted to _CONDITION_OPERATORS."""

    __tablename__ = "workflow_definitions"

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    condition_attribute: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition_operator: Mapped[str | None] = mapped_column(String(10), nullable=True)
    condition_value: Mapped[Any | None] = mapped_column(JSONVariant, nullable=True)


class ApprovalStepDefinition(TenantScopedBase):
    """Belongs to a WorkflowDefinition. `sequence_order` groups: steps sharing a value run in
    parallel, groups resolve in ascending order — reuses SQL's own ORDER BY/GROUP BY idea, no
    extra join table, no DAG/cycle-detection infra needed. `approver_user_id` XOR
    `approver_role_key` (a Role.name), enforced in WorkflowService."""

    __tablename__ = "approval_step_definitions"

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approver_role_key: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ApprovalInstance(TenantScopedBase):
    """One open-or-resolved approval process against (entity_type, entity_id) — indexed, no FK
    on entity_id (same standalone-engine reasoning as WorkflowDefinition.entity_type).
    `current_sequence_order` is the live "which group is actionable now" pointer, None once
    resolved. `context` is the caller-supplied dict passed to
    WorkflowService.evaluate_and_maybe_open, stored for traceability and condition matching."""

    __tablename__ = "approval_instances"

    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    current_sequence_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalInstanceStep(TenantScopedBase):
    """One step's live state, snapshotted from its ApprovalStepDefinition at instance-open
    time (own copies of sequence_order/approver_user_id/approver_role_key) — so editing or
    soft-deleting a WorkflowDefinition later never mutates an already-running instance.
    `step_definition_id` is traceability only, nullable (the source row may later be deleted)."""

    __tablename__ = "approval_instance_steps"

    approval_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_instances.id"), nullable=False, index=True
    )
    step_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_step_definitions.id"), nullable=True
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approver_role_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(TenantScopedBase):
    """In-app only — no email/SMS delivery, that's a deferred provider decision (same category
    as the AI-provider question). `entity_type`/`entity_id` mirror the triggering entity's
    identity (no FK), same reasoning as ApprovalInstance's own columns. Today's only writer is
    WorkflowService — see the module's implementation plan's "Package layout" decision for why
    this lives here rather than in a separate app.notifications package."""

    __tablename__ = "notifications"

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
