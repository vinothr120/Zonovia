import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import TenantScopedRepository
from app.tenants.models import Tenant, TenantConnectionRoute, TenantSetting


class TenantRepository:
    """Tenants are platform-global (not tenant-scoped, obviously), so this doesn't extend
    TenantScopedRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)))
        return result.scalar_one_or_none()

    async def get_by_subdomain(self, subdomain: str) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).where(Tenant.subdomain == subdomain.lower().strip(), Tenant.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_all(self, *, offset: int = 0, limit: int = 20) -> list[Tenant]:
        result = await self.session.execute(select(Tenant).where(Tenant.deleted_at.is_(None)).offset(offset).limit(limit))
        return list(result.scalars().all())

    def add(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        return tenant


class TenantConnectionRouteRepository:
    """Also platform-global / not RLS-protected — see TenantConnectionRoute's docstring."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_tenant(self, tenant_id: uuid.UUID) -> TenantConnectionRoute | None:
        result = await self.session.execute(select(TenantConnectionRoute).where(TenantConnectionRoute.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    def add(self, route: TenantConnectionRoute) -> TenantConnectionRoute:
        self.session.add(route)
        return route


class TenantSettingRepository(TenantScopedRepository[TenantSetting]):
    model = TenantSetting

    async def get_by_key(self, key: str) -> TenantSetting | None:
        stmt = self._base_query().where(TenantSetting.key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[TenantSetting]:
        stmt = self._base_query().order_by(TenantSetting.key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
