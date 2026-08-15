import uuid
from datetime import UTC, datetime
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_model import TenantScopedBase

ModelT = TypeVar("ModelT", bound=TenantScopedBase)


class TenantScopedRepository(Generic[ModelT]):
    """Every module's repository inherits from this. Every query is filtered by tenant_id
    explicitly here, IN ADDITION to Postgres RLS (see app/core/database.py) — defense in
    depth per docs/multi-tenancy.md, so a bug in one layer can't leak data by itself."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id

    def _base_query(self, *, include_deleted: bool = False):
        stmt = select(self.model).where(self.model.tenant_id == self.tenant_id)
        if not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    async def get_by_id(self, entity_id: uuid.UUID, *, include_deleted: bool = False) -> ModelT | None:
        stmt = self._base_query(include_deleted=include_deleted).where(self.model.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, offset: int = 0, limit: int = 20, include_deleted: bool = False) -> list[ModelT]:
        stmt = self._base_query(include_deleted=include_deleted).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_deleted: bool = False) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self._base_query(include_deleted=include_deleted).subquery())
        result = await self.session.execute(stmt)
        return result.scalar_one()

    def add(self, entity: ModelT) -> ModelT:
        entity.tenant_id = self.tenant_id
        self.session.add(entity)
        return entity

    async def soft_delete(self, entity: ModelT, *, deleted_by: uuid.UUID | None = None) -> None:
        entity.deleted_at = datetime.now(UTC)
        if deleted_by is not None:
            entity.updated_by = deleted_by
        await self.session.flush()
