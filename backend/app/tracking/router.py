import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.tracking.schemas import AssetSummary, ScanRequest, TrackingEventRead
from app.tracking.service import TrackingService
from app.users.models import User

_module_gate = Depends(require_module("tracking-engine"))

router = APIRouter(prefix="/tracking", tags=["tracking"], dependencies=[_module_gate])


@router.post("/scan", status_code=201)
async def scan(
    body: ScanRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("tracking.scan")),
):
    service = TrackingService(db, payload.tenant_id)
    asset, event = await service.record_scan(
        identifier_type=body.identifier_type, raw_value=body.value, note=body.note, actor_user_id=actor.id
    )
    return ok(
        {
            "asset": AssetSummary.model_validate(asset).model_dump(),
            "tracking_event": TrackingEventRead.model_validate(event).model_dump(),
        }
    )


events_router = APIRouter(prefix="/assets", tags=["tracking"], dependencies=[_module_gate])


@events_router.get("/{asset_id}/tracking-events")
async def list_tracking_events(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tracking.view")),
):
    service = TrackingService(db, payload.tenant_id)
    events = await service.list_events_for_asset(asset_id)
    return ok([TrackingEventRead.model_validate(e).model_dump() for e in events])
