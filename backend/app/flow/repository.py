import uuid

from sqlalchemy import select

from app.core.base_repository import TenantScopedRepository
from app.flow.models import (
    AssetAssignment,
    AssetLifecycleTransition,
    AssetMovement,
    LifecycleStateDefinition,
    LifecycleTransitionDefinition,
)


class LifecycleStateDefinitionRepository(TenantScopedRepository[LifecycleStateDefinition]):
    model = LifecycleStateDefinition

    async def get_by_key(self, key: str) -> LifecycleStateDefinition | None:
        stmt = self._base_query().where(LifecycleStateDefinition.key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[LifecycleStateDefinition]:
        stmt = self._base_query().order_by(LifecycleStateDefinition.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def any_exist(self) -> bool:
        stmt = self._base_query().limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


class LifecycleTransitionDefinitionRepository(TenantScopedRepository[LifecycleTransitionDefinition]):
    model = LifecycleTransitionDefinition

    async def get_by_edge(self, *, from_state_id: uuid.UUID, to_state_id: uuid.UUID) -> LifecycleTransitionDefinition | None:
        stmt = self._base_query().where(
            LifecycleTransitionDefinition.from_state_id == from_state_id,
            LifecycleTransitionDefinition.to_state_id == to_state_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[LifecycleTransitionDefinition]:
        stmt = self._base_query()
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AssetLifecycleTransitionRepository(TenantScopedRepository[AssetLifecycleTransition]):
    """Append-only — no deleted_at column, so the base query is overridden, same pattern as
    AuditLogRepository."""

    model = AssetLifecycleTransition

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.transitioned_at.desc())

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetLifecycleTransition]:
        stmt = self._base_query().where(AssetLifecycleTransition.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AssetAssignmentRepository(TenantScopedRepository[AssetAssignment]):
    """Mutable history, no deleted_at column (TenantScopedBase minus SoftDeleteMixin) — the
    base query is overridden, same pattern as UserRoleRepository."""

    model = AssetAssignment

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def get_active_for_asset(self, asset_id: uuid.UUID) -> AssetAssignment | None:
        stmt = self._base_query().where(AssetAssignment.asset_id == asset_id, AssetAssignment.unassigned_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetAssignment]:
        stmt = self._base_query().where(AssetAssignment.asset_id == asset_id).order_by(AssetAssignment.assigned_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AssetMovementRepository(TenantScopedRepository[AssetMovement]):
    """Append-only — no deleted_at column, same pattern as AuditLogRepository."""

    model = AssetMovement

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.moved_at.desc())

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetMovement]:
        stmt = self._base_query().where(AssetMovement.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
