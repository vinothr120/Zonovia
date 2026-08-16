import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.models import Asset
from app.asset_core.repository import AssetIdentifierRepository, AssetLocationRepository, AssetRepository
from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.tracking.deps import _hash_gateway_key
from app.tracking.models import Device, DeviceGateway, TrackingEvent
from app.tracking.providers.registry import get_provider
from app.tracking.repository import DeviceGatewayRepository, DeviceRepository, TrackingEventRepository


class TrackingService:
    """Scan resolution + per-asset scan history. Depends on asset_core
    (AssetRepository, AssetIdentifierRepository.get_by_type_value — reused directly, not
    reimplemented), never the reverse."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.events = TrackingEventRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)
        self.identifiers = AssetIdentifierRepository(session, tenant_id)

    async def record_scan(
        self, *, identifier_type: str, raw_value: str, note: str | None, actor_user_id: uuid.UUID | None
    ) -> tuple[Asset, TrackingEvent]:
        provider = get_provider(identifier_type)
        if provider is None:
            # Covers both a genuinely unknown identifier_type and asset_core's own SERIAL
            # type, which tracking-engine deliberately has no provider for — a serial number
            # isn't something a camera scans. asset_core's allow-list stays untouched.
            raise ValidationAppError(f"No tracking provider is registered for identifier_type '{identifier_type}'.")

        normalized_value = provider.normalize(raw_value)
        if normalized_value is None:
            raise ValidationAppError(f"'{raw_value}' is not a valid {identifier_type} value.")

        identifier = await self.identifiers.get_by_type_value(identifier_type=identifier_type, value=normalized_value)
        if identifier is None:
            # The rejected request's audit trail still survives — see core/deps.py::get_db's
            # comment: an AppError raised below still lets this write commit.
            await write_audit_log(
                self.session,
                tenant_id=self.tenant_id,
                actor_user_id=actor_user_id,
                action="tracking.scan_unresolved",
                entity_type="tracking_event",
                entity_id=None,
                new_value={"provider_type": identifier_type, "raw_value": raw_value, "normalized_value": normalized_value},
            )
            raise NotFoundError(f"No asset is identified by {identifier_type} value '{normalized_value}'.")

        asset = await self.assets.get_by_id(identifier.asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")

        event = self.events.add(
            TrackingEvent(
                asset_id=asset.id,
                provider_type=identifier_type,
                event_type="scan",
                payload={
                    "raw_value": raw_value,
                    "normalized_value": normalized_value,
                    "identifier_id": str(identifier.id),
                    "note": note,
                },
                scanned_by=actor_user_id,
            )
        )
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.scanned",
            entity_type="asset",
            entity_id=asset.id,
            new_value={"provider_type": identifier_type, "tracking_event_id": str(event.id)},
        )
        return asset, event

    async def list_events_for_asset(self, asset_id: uuid.UUID, *, limit: int = 50) -> list[TrackingEvent]:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return await self.events.list_for_asset(asset_id, limit=limit)


def _generate_api_key() -> str:
    """URL-safe, high-entropy — no format assumptions baked in anywhere else, unlike a JWT."""
    return secrets.token_urlsafe(32)


class DeviceGatewayService:
    """Gateway/device management — Tenant-Admin-only (tracking.manage_gateways/manage_devices,
    see app/tracking/permissions.py), reached only through the ordinary user-JWT router
    (app/tracking/router.py's gateways_router), never through the gateway-auth chain itself.
    Depends on asset-core (AssetLocationRepository) only for an optional location FK check,
    same shallow-dependency shape as every other module's service."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.gateways = DeviceGatewayRepository(session, tenant_id)
        self.devices = DeviceRepository(session, tenant_id)
        self.locations = AssetLocationRepository(session, tenant_id)

    async def create_gateway(
        self, *, name: str, location_id: uuid.UUID | None, actor_user_id: uuid.UUID | None
    ) -> tuple[DeviceGateway, str]:
        """Returns (gateway, raw_api_key). The raw key exists ONLY in this return value and
        the router's one-time 201 response — never logged, never audited, never stored;
        api_key_hash (hashlib.sha256, mirroring RefreshToken.token_hash) is what persists."""
        if location_id is not None and await self.locations.get_by_id(location_id) is None:
            raise NotFoundError("Asset location not found.")

        raw_key = _generate_api_key()
        gateway = self.gateways.add(
            DeviceGateway(
                name=name,
                location_id=location_id,
                status="active",
                api_key_hash=_hash_gateway_key(raw_key),
                api_key_last4=raw_key[-4:],
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="device_gateway.created",
            entity_type="device_gateway",
            entity_id=gateway.id,
            # Deliberately no api_key/api_key_hash in the audit trail — see the docstring above.
            new_value={"name": name, "location_id": str(location_id) if location_id else None},
        )
        return gateway, raw_key

    async def get_gateway_or_404(self, gateway_id: uuid.UUID) -> DeviceGateway:
        gateway = await self.gateways.get_by_id(gateway_id)
        if gateway is None:
            raise NotFoundError("Device gateway not found.")
        return gateway

    async def list_gateways(self, *, offset: int = 0, limit: int = 20) -> list[DeviceGateway]:
        return await self.gateways.list(offset=offset, limit=limit)

    async def revoke_gateway(self, *, gateway_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> DeviceGateway:
        gateway = await self.get_gateway_or_404(gateway_id)
        if gateway.status == "revoked":
            raise ConflictError("Gateway is already revoked.")
        gateway.status = "revoked"
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="device_gateway.revoked",
            entity_type="device_gateway",
            entity_id=gateway.id,
        )
        return gateway

    async def register_device(
        self,
        *,
        gateway_id: uuid.UUID,
        device_type: str,
        vendor: str | None,
        model: str | None,
        serial_number: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Device:
        gateway = await self.get_gateway_or_404(gateway_id)
        device = self.devices.add(
            Device(
                gateway_id=gateway.id,
                device_type=device_type,
                vendor=vendor,
                model=model,
                serial_number=serial_number,
                status="active",
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="device.registered",
            entity_type="device",
            entity_id=device.id,
            new_value={"gateway_id": str(gateway_id), "device_type": device_type},
        )
        return device

    async def list_devices_for_gateway(self, gateway_id: uuid.UUID) -> list[Device]:
        await self.get_gateway_or_404(gateway_id)
        return await self.devices.list_for_gateway(gateway_id)

    async def get_device_or_404(self, device_id: uuid.UUID) -> Device:
        device = await self.devices.get_by_id(device_id)
        if device is None:
            raise NotFoundError("Device not found.")
        return device
