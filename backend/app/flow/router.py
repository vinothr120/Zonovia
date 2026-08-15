import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.flow.schemas import (
    AssetAssignmentRead,
    AssetAssignRequest,
    AssetMovementRead,
    AssetMoveRequest,
    AssetTransitionRequest,
    AssetUnassignRequest,
    LifecycleStateDefinitionCreate,
    LifecycleStateDefinitionRead,
    LifecycleStateDefinitionUpdate,
    LifecycleTransitionDefinitionCreate,
    LifecycleTransitionDefinitionRead,
)
from app.flow.service import FlowService
from app.users.models import User

_module_gate = Depends(require_module("flow"))

router = APIRouter(prefix="/assets", tags=["asset-lifecycle"], dependencies=[_module_gate])


@router.post("/{asset_id}/transition")
async def transition_asset(
    asset_id: uuid.UUID,
    body: AssetTransitionRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.transition_lifecycle")),
):
    service = FlowService(db, payload.tenant_id)
    transition = await service.transition_asset(
        asset_id=asset_id, to_state_id=body.to_state_id, actor_user_id=actor.id, note=body.note
    )
    return ok(
        {
            "id": transition.id,
            "asset_id": transition.asset_id,
            "from_state_id": transition.from_state_id,
            "to_state_id": transition.to_state_id,
            "transitioned_at": transition.transitioned_at,
            "note": transition.note,
        }
    )


@router.post("/{asset_id}/assign", status_code=201)
async def assign_custodian(
    asset_id: uuid.UUID,
    body: AssetAssignRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.assign")),
):
    service = FlowService(db, payload.tenant_id)
    assignment = await service.assign_custodian(
        asset_id=asset_id, custodian_user_id=body.custodian_user_id, actor_user_id=actor.id, note=body.note
    )
    return ok(AssetAssignmentRead.model_validate(assignment).model_dump())


@router.post("/{asset_id}/unassign")
async def unassign_custodian(
    asset_id: uuid.UUID,
    body: AssetUnassignRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.assign")),
):
    service = FlowService(db, payload.tenant_id)
    assignment = await service.unassign_custodian(asset_id=asset_id, actor_user_id=actor.id, note=body.note)
    return ok(AssetAssignmentRead.model_validate(assignment).model_dump())


@router.post("/{asset_id}/move")
async def move_asset(
    asset_id: uuid.UUID,
    body: AssetMoveRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.move")),
):
    service = FlowService(db, payload.tenant_id)
    movement = await service.move_asset(
        asset_id=asset_id, to_location_id=body.to_location_id, actor_user_id=actor.id, note=body.note
    )
    return ok(AssetMovementRead.model_validate(movement).model_dump())


@router.get("/{asset_id}/history")
async def get_asset_history(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_lifecycle.view")),
):
    service = FlowService(db, payload.tenant_id)
    history = await service.get_asset_history(asset_id)
    return ok(history)


lifecycle_config_router = APIRouter(prefix="/asset-lifecycle", tags=["asset-lifecycle-config"], dependencies=[_module_gate])


@lifecycle_config_router.get("/states")
async def list_states(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_lifecycle.view")),
):
    service = FlowService(db, payload.tenant_id)
    states = await service.list_states()
    return ok([LifecycleStateDefinitionRead.model_validate(s).model_dump() for s in states])


@lifecycle_config_router.post("/states", status_code=201)
async def create_state(
    body: LifecycleStateDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_lifecycle.configure")),
):
    service = FlowService(db, payload.tenant_id)
    state = await service.create_state(
        key=body.key,
        label=body.label,
        is_initial=body.is_initial,
        is_terminal=body.is_terminal,
        sort_order=body.sort_order,
        actor_user_id=actor.id,
    )
    return ok(LifecycleStateDefinitionRead.model_validate(state).model_dump())


@lifecycle_config_router.patch("/states/{state_id}")
async def update_state(
    state_id: uuid.UUID,
    body: LifecycleStateDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_lifecycle.configure")),
):
    service = FlowService(db, payload.tenant_id)
    state = await service.update_state(
        state_id=state_id,
        label=body.label,
        is_initial=body.is_initial,
        is_terminal=body.is_terminal,
        sort_order=body.sort_order,
        actor_user_id=actor.id,
    )
    return ok(LifecycleStateDefinitionRead.model_validate(state).model_dump())


@lifecycle_config_router.delete("/states/{state_id}", status_code=204)
async def delete_state(
    state_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_lifecycle.configure")),
):
    service = FlowService(db, payload.tenant_id)
    await service.delete_state(state_id=state_id, actor_user_id=actor.id)


@lifecycle_config_router.get("/transitions")
async def list_transition_definitions(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_lifecycle.view")),
):
    service = FlowService(db, payload.tenant_id)
    transitions = await service.list_transition_definitions()
    return ok([LifecycleTransitionDefinitionRead.model_validate(t).model_dump() for t in transitions])


@lifecycle_config_router.post("/transitions", status_code=201)
async def create_transition_definition(
    body: LifecycleTransitionDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_lifecycle.configure")),
):
    service = FlowService(db, payload.tenant_id)
    transition_def = await service.create_transition_definition(
        from_state_id=body.from_state_id, to_state_id=body.to_state_id, actor_user_id=actor.id
    )
    return ok(LifecycleTransitionDefinitionRead.model_validate(transition_def).model_dump())


@lifecycle_config_router.delete("/transitions/{transition_def_id}", status_code=204)
async def delete_transition_definition(
    transition_def_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_lifecycle.configure")),
):
    service = FlowService(db, payload.tenant_id)
    await service.delete_transition_definition(transition_def_id=transition_def_id, actor_user_id=actor.id)
