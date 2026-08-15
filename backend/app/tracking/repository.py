import uuid

from sqlalchemy import select

from app.core.base_repository import TenantScopedRepository
from app.tracking.models import TrackingEvent


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
