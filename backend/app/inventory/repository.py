import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.base_repository import TenantScopedRepository
from app.inventory.models import InventoryCount, InventoryCycle, ReconciliationAction


class InventoryCycleRepository(TenantScopedRepository[InventoryCycle]):
    model = InventoryCycle


class InventoryCountRepository(TenantScopedRepository[InventoryCount]):
    """Append-only — no deleted_at column, same pattern as TrackingEventRepository/
    AssetMovementRepository."""

    model = InventoryCount

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.verified_at.desc())

    async def list_for_cycle(self, cycle_id: uuid.UUID) -> list[InventoryCount]:
        stmt = self._base_query().where(InventoryCount.cycle_id == cycle_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_per_asset(self, cycle_id: uuid.UUID) -> list[InventoryCount]:
        """One row per asset — the most recent InventoryCount by verified_at for each asset
        counted in this cycle, via ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY
        verified_at DESC). Portable to both SQLite-in-tests and Postgres, the same tier
        AssetLocationRepository.list_descendants's recursive CTE already relies on. This is
        the query InventoryService.get_cycle_report uses so a re-scan correcting an earlier
        wrong-location count doesn't leave the asset erroneously flagged as a discrepancy."""
        row_number = (
            func.row_number()
            .over(partition_by=InventoryCount.asset_id, order_by=InventoryCount.verified_at.desc())
            .label("row_number")
        )
        subq = (
            select(InventoryCount, row_number)
            .where(InventoryCount.tenant_id == self.tenant_id, InventoryCount.cycle_id == cycle_id)
            .subquery()
        )
        ranked = aliased(InventoryCount, subq)
        stmt = select(ranked).where(subq.c.row_number == 1)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ReconciliationActionRepository(TenantScopedRepository[ReconciliationAction]):
    """Append-only — no deleted_at column, same pattern as InventoryCountRepository."""

    model = ReconciliationAction

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.resolved_at.desc())

    async def list_for_cycle(self, cycle_id: uuid.UUID) -> list[ReconciliationAction]:
        stmt = self._base_query().where(ReconciliationAction.cycle_id == cycle_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
