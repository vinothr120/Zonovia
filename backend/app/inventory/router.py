import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.inventory.schemas import (
    CycleReport,
    InventoryCountRead,
    InventoryCycleCreate,
    InventoryCycleRead,
    InventoryVerificationRequest,
    ReconciliationActionRead,
    ReconciliationRequest,
)
from app.inventory.service import InventoryService
from app.users.models import User

_module_gate = Depends(require_module("inventory"))

router = APIRouter(prefix="/inventory", tags=["inventory"], dependencies=[_module_gate])


@router.post("/cycles", status_code=201)
async def create_cycle(
    body: InventoryCycleCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.manage_cycles")),
):
    service = InventoryService(db, payload.tenant_id)
    cycle = await service.create_cycle(
        name=body.name, description=body.description, root_location_id=body.root_location_id, actor_user_id=actor.id
    )
    return ok(InventoryCycleRead.model_validate(cycle).model_dump())


@router.get("/cycles")
async def list_cycles(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("inventory.view")),
):
    service = InventoryService(db, payload.tenant_id)
    cycles = await service.list_cycles()
    return ok([InventoryCycleRead.model_validate(c).model_dump() for c in cycles])


@router.get("/cycles/{cycle_id}")
async def get_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("inventory.view")),
):
    service = InventoryService(db, payload.tenant_id)
    cycle = await service.get_cycle_or_404(cycle_id)
    return ok(InventoryCycleRead.model_validate(cycle).model_dump())


@router.post("/cycles/{cycle_id}/start")
async def start_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.manage_cycles")),
):
    service = InventoryService(db, payload.tenant_id)
    cycle = await service.start_cycle(cycle_id=cycle_id, actor_user_id=actor.id)
    return ok(InventoryCycleRead.model_validate(cycle).model_dump())


@router.post("/cycles/{cycle_id}/complete")
async def complete_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.manage_cycles")),
):
    service = InventoryService(db, payload.tenant_id)
    cycle = await service.complete_cycle(cycle_id=cycle_id, actor_user_id=actor.id)
    return ok(InventoryCycleRead.model_validate(cycle).model_dump())


@router.post("/cycles/{cycle_id}/cancel")
async def cancel_cycle(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.manage_cycles")),
):
    service = InventoryService(db, payload.tenant_id)
    cycle = await service.cancel_cycle(cycle_id=cycle_id, actor_user_id=actor.id)
    return ok(InventoryCycleRead.model_validate(cycle).model_dump())


@router.post("/cycles/{cycle_id}/counts", status_code=201)
async def record_verification(
    cycle_id: uuid.UUID,
    body: InventoryVerificationRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.verify")),
):
    service = InventoryService(db, payload.tenant_id)
    count = await service.record_verification(
        cycle_id=cycle_id,
        identifier_type=body.identifier_type,
        raw_value=body.value,
        found_location_id=body.found_location_id,
        note=body.note,
        actor_user_id=actor.id,
    )
    return ok(InventoryCountRead.model_validate(count).model_dump())


@router.get("/cycles/{cycle_id}/counts")
async def list_counts(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("inventory.view")),
):
    service = InventoryService(db, payload.tenant_id)
    counts = await service.list_counts_for_cycle(cycle_id)
    return ok([InventoryCountRead.model_validate(c).model_dump() for c in counts])


@router.get("/cycles/{cycle_id}/report")
async def get_cycle_report(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("inventory.view")),
):
    service = InventoryService(db, payload.tenant_id)
    report = await service.get_cycle_report(cycle_id)
    return ok(CycleReport.model_validate(report).model_dump())


@router.post("/cycles/{cycle_id}/reconciliations", status_code=201)
async def record_reconciliation(
    cycle_id: uuid.UUID,
    body: ReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("inventory.reconcile")),
):
    service = InventoryService(db, payload.tenant_id)
    action = await service.record_reconciliation(
        cycle_id=cycle_id, asset_id=body.asset_id, action_type=body.action_type, note=body.note, actor_user_id=actor.id
    )
    return ok(ReconciliationActionRead.model_validate(action).model_dump())


@router.get("/cycles/{cycle_id}/reconciliations")
async def list_reconciliations(
    cycle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("inventory.view")),
):
    service = InventoryService(db, payload.tenant_id)
    actions = await service.list_reconciliations_for_cycle(cycle_id)
    return ok([ReconciliationActionRead.model_validate(a).model_dump() for a in actions])
