import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.base_repository import TenantScopedRepository
from app.tracking.models import Device, DeviceGateway, TrackingEvent


class TrackingEventRepository(TenantScopedRepository[TrackingEvent]):
    """Append-only — no deleted_at column, same pattern as AssetLifecycleTransitionRepository/
    AssetMovementRepository (app/flow/repository.py). The base
    TenantScopedRepository._base_query() references self.model.deleted_at, which
    TrackingEvent doesn't have — this override is required, not optional."""

    model = TrackingEvent

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.occurred_at.desc())

    async def list_for_asset(self, asset_id: uuid.UUID, *, limit: int = 50) -> list[TrackingEvent]:
        stmt = self._base_query().where(TrackingEvent.asset_id == asset_id).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_for_asset_device(
        self, asset_id: uuid.UUID, device_id: uuid.UUID, provider_type: str, since: datetime
    ) -> TrackingEvent | None:
        """The dedup lookup RfidIngestionService.ingest_batch relies on — keyed on
        (asset_id, device_id), NOT asset_id alone. A different device reading the same asset
        within the same window must NOT match here (a genuine zone transition, tag moving from
        Reader A to Reader B, must always surface as an immediate new TrackingEvent) — see the
        module's implementation plan's dedup-key design decision. Returns the single most
        recent match, not a list — that's all a dedup check needs."""
        stmt = (
            self._base_query()
            .where(
                TrackingEvent.asset_id == asset_id,
                TrackingEvent.device_id == device_id,
                TrackingEvent.provider_type == provider_type,
                TrackingEvent.occurred_at >= since,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class DeviceGatewayRepository(TenantScopedRepository[DeviceGateway]):
    model = DeviceGateway

    async def get_by_api_key_hash(self, api_key_hash: str) -> DeviceGateway | None:
        stmt = self._base_query().where(DeviceGateway.api_key_hash == api_key_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class DeviceRepository(TenantScopedRepository[Device]):
    model = Device

    async def list_for_gateway(self, gateway_id: uuid.UUID) -> list[Device]:
        stmt = self._base_query().where(Device.gateway_id == gateway_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
