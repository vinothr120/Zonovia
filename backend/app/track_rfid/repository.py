import uuid

from sqlalchemy import select

from app.core.base_repository import TenantScopedRepository
from app.track_rfid.models import RfidReadEvent, RfidTag


class RfidTagRepository(TenantScopedRepository[RfidTag]):
    model = RfidTag

    async def get_by_asset_identifier_id(self, asset_identifier_id: uuid.UUID) -> RfidTag | None:
        stmt = self._base_query().where(RfidTag.asset_identifier_id == asset_identifier_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_asset_id(self, asset_id: uuid.UUID) -> RfidTag | None:
        stmt = self._base_query().where(RfidTag.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, *, offset: int = 0, limit: int = 20) -> list[RfidTag]:
        return await self.list(offset=offset, limit=limit)


class RfidReadEventRepository(TenantScopedRepository[RfidReadEvent]):
    """Append-only — no deleted_at column, same pattern as TrackingEventRepository/
    InventoryCountRepository."""

    model = RfidReadEvent

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.read_at.desc())

    async def list_filtered(
        self,
        *,
        resolved: bool | None = None,
        device_id: uuid.UUID | None = None,
        tag_epc: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RfidReadEvent]:
        stmt = self._base_query()
        if resolved is True:
            stmt = stmt.where(RfidReadEvent.asset_id.is_not(None))
        elif resolved is False:
            stmt = stmt.where(RfidReadEvent.asset_id.is_(None))
        if device_id is not None:
            stmt = stmt.where(RfidReadEvent.device_id == device_id)
        if tag_epc is not None:
            stmt = stmt.where(RfidReadEvent.tag_epc == tag_epc)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
