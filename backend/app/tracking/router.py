import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.tracking.schemas import (
    AssetSummary,
    DeviceCreate,
    DeviceGatewayCreate,
    DeviceGatewayCreateResponse,
    DeviceGatewayRead,
    DeviceRead,
    ScanRequest,
    TrackingEventRead,
)
from app.tracking.service import DeviceGatewayService, TrackingService
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


# -- device gateways / devices (Phase 6) -------------------------------------------------------
# Ordinary user-JWT + require_permission router — entirely separate from the gateway-auth-only
# ingest_router in app/track_rfid/router.py. Tenant-Admin-only, one tier (no *.view split): see
# app/tracking/permissions.py's comment on why gateway/device management has no view-only tier.
gateways_router = APIRouter(prefix="/tracking/gateways", tags=["tracking-gateways"], dependencies=[_module_gate])


@gateways_router.post("", status_code=201)
async def create_gateway(
    body: DeviceGatewayCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("tracking.manage_gateways")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    gateway, raw_api_key = await service.create_gateway(name=body.name, location_id=body.location_id, actor_user_id=actor.id)
    return ok(DeviceGatewayCreateResponse(gateway=DeviceGatewayRead.model_validate(gateway), api_key=raw_api_key).model_dump())


@gateways_router.get("")
async def list_gateways(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tracking.manage_gateways")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    gateways = await service.list_gateways()
    return ok([DeviceGatewayRead.model_validate(g).model_dump() for g in gateways])


@gateways_router.get("/{gateway_id}")
async def get_gateway(
    gateway_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tracking.manage_gateways")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    gateway = await service.get_gateway_or_404(gateway_id)
    return ok(DeviceGatewayRead.model_validate(gateway).model_dump())


@gateways_router.post("/{gateway_id}/revoke")
async def revoke_gateway(
    gateway_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("tracking.manage_gateways")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    gateway = await service.revoke_gateway(gateway_id=gateway_id, actor_user_id=actor.id)
    return ok(DeviceGatewayRead.model_validate(gateway).model_dump())


@gateways_router.post("/{gateway_id}/devices", status_code=201)
async def register_device(
    gateway_id: uuid.UUID,
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("tracking.manage_devices")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    device = await service.register_device(
        gateway_id=gateway_id,
        device_type=body.device_type,
        vendor=body.vendor,
        model=body.model,
        serial_number=body.serial_number,
        actor_user_id=actor.id,
    )
    return ok(DeviceRead.model_validate(device).model_dump())


@gateways_router.get("/{gateway_id}/devices")
async def list_devices(
    gateway_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tracking.manage_devices")),
):
    service = DeviceGatewayService(db, payload.tenant_id)
    devices = await service.list_devices_for_gateway(gateway_id)
    return ok([DeviceRead.model_validate(d).model_dump() for d in devices])
