import uuid

from app.core.base_repository import TenantScopedRepository
from app.maintenance.models import MaintenanceTicket, ServiceSchedule, Warranty


class MaintenanceTicketRepository(TenantScopedRepository[MaintenanceTicket]):
    model = MaintenanceTicket

    async def list_filtered(
        self,
        *,
        status: str | None = None,
        asset_id: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        asset_ids: list[uuid.UUID] | None = None,
    ) -> list[MaintenanceTicket]:
        """`asset_ids`, when given, is the read-only Flow lifecycle_state_key -> asset id
        resolution from MaintenanceService.list_tickets — intersected with every other filter,
        never a replacement for asset_id. An empty (but non-None) `asset_ids` means the
        lifecycle key matched zero assets, so the query correctly returns zero tickets rather
        than silently ignoring the filter."""
        stmt = self._base_query()
        if status is not None:
            stmt = stmt.where(MaintenanceTicket.status == status)
        if asset_id is not None:
            stmt = stmt.where(MaintenanceTicket.asset_id == asset_id)
        if assigned_to is not None:
            stmt = stmt.where(MaintenanceTicket.assigned_to == assigned_to)
        if asset_ids is not None:
            stmt = stmt.where(MaintenanceTicket.asset_id.in_(asset_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class WarrantyRepository(TenantScopedRepository[Warranty]):
    model = Warranty

    async def get_by_asset_id(self, asset_id: uuid.UUID) -> Warranty | None:
        stmt = self._base_query().where(Warranty.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ServiceScheduleRepository(TenantScopedRepository[ServiceSchedule]):
    model = ServiceSchedule

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[ServiceSchedule]:
        stmt = self._base_query().where(ServiceSchedule.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[ServiceSchedule]:
        """Unpaginated — used by MaintenanceService.get_schedule_due_report, which must see
        every active schedule to split overdue/upcoming correctly."""
        stmt = self._base_query()
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
