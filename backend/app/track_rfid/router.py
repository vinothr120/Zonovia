import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.track_rfid.models import RfidTag
from app.track_rfid.schemas import (
    RfidIngestRequest,
    RfidIngestResponse,
    RfidReadEventRead,
    RfidTagCreate,
    RfidTagRead,
)
from app.track_rfid.service import RfidIngestionService, RfidTagService
from app.tracking.deps import GatewayPayload, get_gateway_db, get_gateway_payload, require_module_for_gateway
from app.users.models import User

_module_gate = Depends(require_module("track-rfid"))


def _tag_read_dict(tag: RfidTag, epc: str) -> dict:
    """Merges RfidTag's own columns with epc, which lives on the linked AssetIdentifier, not
    on RfidTag itself — same "computed/joined at read time, merged in by the router"
    convention as app.maintenance.router._warranty_read_dict."""
    return {
        "id": tag.id,
        "asset_identifier_id": tag.asset_identifier_id,
        "asset_id": tag.asset_id,
        "tag_type": tag.tag_type,
        "last_device_id": tag.last_device_id,
        "last_rssi": tag.last_rssi,
        "last_read_at": tag.last_read_at,
        "created_at": tag.created_at,
        "epc": epc,
    }


# -- tags -----------------------------------------------------------------------------------
tags_router = APIRouter(prefix="/rfid/tags", tags=["track-rfid"], dependencies=[_module_gate])


@tags_router.post("", status_code=201)
async def register_tag(
    body: RfidTagCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("track_rfid.manage_tags")),
):
    service = RfidTagService(db, payload.tenant_id)
    tag, normalized_epc = await service.register_tag(
        asset_id=body.asset_id, epc=body.epc, tag_type=body.tag_type, actor_user_id=actor.id
    )
    return ok(RfidTagRead.model_validate(_tag_read_dict(tag, normalized_epc)).model_dump())


@tags_router.get("/{asset_id}")
async def get_tag_for_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("track_rfid.view")),
):
    service = RfidTagService(db, payload.tenant_id)
    tag = await service.get_tag_for_asset(asset_id)
    epc = await service.get_tag_epc(tag)
    return ok(RfidTagRead.model_validate(_tag_read_dict(tag, epc)).model_dump())


@tags_router.get("")
async def list_tags(
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("track_rfid.view")),
):
    service = RfidTagService(db, payload.tenant_id)
    tags = await service.list_tags(offset=offset, limit=limit)
    result = []
    for tag in tags:
        epc = await service.get_tag_epc(tag)
        result.append(RfidTagRead.model_validate(_tag_read_dict(tag, epc)).model_dump())
    return ok(result)


# -- raw read-event history ------------------------------------------------------------------
read_events_router = APIRouter(prefix="/rfid/read-events", tags=["track-rfid"], dependencies=[_module_gate])


@read_events_router.get("")
async def list_read_events(
    resolved: bool | None = None,
    device_id: uuid.UUID | None = None,
    tag_epc: str | None = None,
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("track_rfid.view")),
):
    service = RfidIngestionService(db, payload.tenant_id)
    events = await service.list_read_events(resolved=resolved, device_id=device_id, tag_epc=tag_epc, offset=offset, limit=limit)
    return ok([RfidReadEventRead.model_validate(e).model_dump() for e in events])


# -- gateway-auth-only batch ingest -----------------------------------------------------------
# NO require_permission — a gateway has no user/role, only "is this key valid and active",
# which get_gateway_payload itself already establishes. NO user-JWT dependency anywhere in
# this router — see app/tracking/deps.py's module docstring for why the two auth chains must
# never mix on the same endpoint.
_gateway_module_gate = Depends(require_module_for_gateway("track-rfid"))

ingest_router = APIRouter(prefix="/rfid", tags=["track-rfid-ingest"], dependencies=[_gateway_module_gate])


@ingest_router.post("/ingest", status_code=201)
async def ingest_reads(
    body: RfidIngestRequest,
    db: AsyncSession = Depends(get_gateway_db),
    payload: GatewayPayload = Depends(get_gateway_payload),
):
    service = RfidIngestionService(db, payload.tenant_id)
    counts = await service.ingest_batch(gateway_id=payload.gateway_id, reads=body.reads)
    return ok(RfidIngestResponse(**counts).model_dump())
