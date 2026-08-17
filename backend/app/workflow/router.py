import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_permission
from app.core.response import ok
from app.users.models import User
from app.workflow.models import ApprovalInstance, ApprovalInstanceStep
from app.workflow.schemas import (
    ApprovalInstanceRead,
    ApprovalInstanceStepRead,
    ApprovalStepDefinitionAdd,
    ApprovalStepDefinitionRead,
    ApprovalStepDefinitionUpdate,
    EvaluateInstanceRequest,
    NotificationRead,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
)
from app.workflow.service import UNSET, WorkflowService

# No require_module("workflow") dependency — workflow is registered always_on=True (Platform
# Core infrastructure, not a paid module), and require_module no-ops for always_on modules
# anyway (core/deps.py:154-156). Follows the same omission as tenants/router.py and
# users/router.py, both always_on Platform Core routers.
router = APIRouter(prefix="/workflow", tags=["workflow"])


def _instance_read_dict(instance: ApprovalInstance, steps: list[ApprovalInstanceStep]) -> dict:
    """Merges ApprovalInstance's own columns with its steps in one payload — same "router
    merges nested data" convention as app.maintenance.router's _schedule_read_dict."""
    return {
        "id": instance.id,
        "workflow_definition_id": instance.workflow_definition_id,
        "entity_type": instance.entity_type,
        "entity_id": instance.entity_id,
        "status": instance.status,
        "current_sequence_order": instance.current_sequence_order,
        "context": instance.context,
        "requested_by": instance.requested_by,
        "resolved_at": instance.resolved_at,
        "created_at": instance.created_at,
        "steps": [ApprovalInstanceStepRead.model_validate(s) for s in steps],
    }


# -- definitions --------------------------------------------------------------------------------
@router.post("/definitions", status_code=201)
async def create_definition(
    body: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    definition = await service.create_definition(
        entity_type=body.entity_type,
        name=body.name,
        is_active=body.is_active,
        condition_attribute=body.condition_attribute,
        condition_operator=body.condition_operator,
        condition_value=body.condition_value,
        steps=[s.model_dump() for s in body.steps],
        actor_user_id=actor.id,
    )
    return ok(WorkflowDefinitionRead.model_validate(definition).model_dump())


@router.get("/definitions")
async def list_definitions(
    entity_type: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("workflow.view")),
):
    service = WorkflowService(db, payload.tenant_id)
    definitions = await service.list_definitions(entity_type=entity_type, is_active=is_active)
    return ok([WorkflowDefinitionRead.model_validate(d).model_dump() for d in definitions])


@router.get("/definitions/{definition_id}")
async def get_definition(
    definition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("workflow.view")),
):
    service = WorkflowService(db, payload.tenant_id)
    definition = await service.get_definition_or_404(definition_id)
    return ok(WorkflowDefinitionRead.model_validate(definition).model_dump())


@router.patch("/definitions/{definition_id}")
async def update_definition(
    definition_id: uuid.UUID,
    body: WorkflowDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    definition = await service.update_definition(
        definition_id=definition_id,
        name=body.name,
        is_active=body.is_active,
        condition_attribute=body.condition_attribute,
        condition_operator=body.condition_operator,
        condition_value=body.condition_value,
        actor_user_id=actor.id,
    )
    return ok(WorkflowDefinitionRead.model_validate(definition).model_dump())


@router.delete("/definitions/{definition_id}", status_code=204)
async def delete_definition(
    definition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    await service.delete_definition(definition_id=definition_id, actor_user_id=actor.id)


# -- steps ------------------------------------------------------------------------------------
@router.get("/definitions/{definition_id}/steps")
async def list_steps(
    definition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("workflow.view")),
):
    service = WorkflowService(db, payload.tenant_id)
    steps = await service.list_steps(definition_id)
    return ok([ApprovalStepDefinitionRead.model_validate(s).model_dump() for s in steps])


@router.post("/definitions/{definition_id}/steps", status_code=201)
async def add_step(
    definition_id: uuid.UUID,
    body: ApprovalStepDefinitionAdd,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    step = await service.add_step(
        definition_id=definition_id,
        sequence_order=body.sequence_order,
        approver_user_id=body.approver_user_id,
        approver_role_key=body.approver_role_key,
        actor_user_id=actor.id,
    )
    return ok(ApprovalStepDefinitionRead.model_validate(step).model_dump())


@router.patch("/definitions/{definition_id}/steps/{step_id}")
async def update_step(
    definition_id: uuid.UUID,  # noqa: ARG001 — path-scoping only, the step itself is looked up by step_id
    step_id: uuid.UUID,
    body: ApprovalStepDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    fields_set = body.model_fields_set
    step = await service.update_step(
        step_id=step_id,
        sequence_order=body.sequence_order,
        approver_user_id=body.approver_user_id if "approver_user_id" in fields_set else UNSET,
        approver_role_key=body.approver_role_key if "approver_role_key" in fields_set else UNSET,
        actor_user_id=actor.id,
    )
    return ok(ApprovalStepDefinitionRead.model_validate(step).model_dump())


@router.delete("/definitions/{definition_id}/steps/{step_id}", status_code=204)
async def delete_step(
    definition_id: uuid.UUID,  # noqa: ARG001 — path-scoping only, the step itself is looked up by step_id
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    await service.delete_step(step_id=step_id, actor_user_id=actor.id)


# -- instances --------------------------------------------------------------------------------
@router.post("/instances/evaluate")
async def evaluate_instance(
    body: EvaluateInstanceRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    # Deliberately conservative — a manual/administrative trigger (for testing, or a future
    # external connector), not the primary integration path. The primary path for a future
    # module wiring is the in-process WorkflowService.evaluate_and_maybe_open(...) call.
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    instance = await service.evaluate_and_maybe_open(
        entity_type=body.entity_type, entity_id=body.entity_id, context=body.context, actor_user_id=actor.id
    )
    if instance is None:
        return ok(None)
    steps = await service.list_instance_steps(instance.id)
    return ok(ApprovalInstanceRead.model_validate(_instance_read_dict(instance, steps)).model_dump())


@router.get("/instances")
async def list_instances(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("workflow.view")),
):
    service = WorkflowService(db, payload.tenant_id)
    instances = await service.list_instances(entity_type=entity_type, entity_id=entity_id, status=status)
    results = []
    for instance in instances:
        steps = await service.list_instance_steps(instance.id)
        results.append(ApprovalInstanceRead.model_validate(_instance_read_dict(instance, steps)).model_dump())
    return ok(results)


@router.get("/instances/{instance_id}")
async def get_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("workflow.view")),
):
    service = WorkflowService(db, payload.tenant_id)
    instance = await service.get_instance_or_404(instance_id)
    steps = await service.list_instance_steps(instance.id)
    return ok(ApprovalInstanceRead.model_validate(_instance_read_dict(instance, steps)).model_dump())


@router.post("/instances/{instance_id}/cancel")
async def cancel_instance(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    # Admin-reserved — no self-service cancel-your-own-request path this round.
    _=Depends(require_permission("workflow.manage_definitions")),
):
    service = WorkflowService(db, payload.tenant_id)
    instance = await service.cancel_instance(instance_id=instance_id, actor_user_id=actor.id)
    steps = await service.list_instance_steps(instance.id)
    return ok(ApprovalInstanceRead.model_validate(_instance_read_dict(instance, steps)).model_dump())


# -- instance-step decisions --------------------------------------------------------------------
@router.post("/instance-steps/{instance_step_id}/approve")
async def approve_step(
    instance_step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    # Broad router gate — the service independently checks the actor is the step's actual
    # assignee (by user id, or by membership in the assigned role) and raises
    # PermissionDeniedError if not. See WorkflowService._is_assignee.
    _=Depends(require_permission("workflow.decide")),
):
    service = WorkflowService(db, payload.tenant_id)
    step = await service.approve_step(instance_step_id=instance_step_id, actor_user_id=actor.id)
    return ok(ApprovalInstanceStepRead.model_validate(step).model_dump())


@router.post("/instance-steps/{instance_step_id}/reject")
async def reject_step(
    instance_step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("workflow.decide")),
):
    service = WorkflowService(db, payload.tenant_id)
    step = await service.reject_step(instance_step_id=instance_step_id, actor_user_id=actor.id)
    return ok(ApprovalInstanceStepRead.model_validate(step).model_dump())


# -- notifications ------------------------------------------------------------------------------
# Gated only by authentication, no permission key — every user manages their own inbox.
@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
):
    service = WorkflowService(db, payload.tenant_id)
    notifications = await service.list_for_user(actor.id, unread_only=unread_only)
    return ok([NotificationRead.model_validate(n).model_dump() for n in notifications])


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
):
    service = WorkflowService(db, payload.tenant_id)
    notification = await service.mark_read(notification_id=notification_id, actor_user_id=actor.id)
    return ok(NotificationRead.model_validate(notification).model_dump())
