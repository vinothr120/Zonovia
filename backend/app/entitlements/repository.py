from app.core.base_repository import TenantScopedRepository
from app.entitlements.models import TenantModuleEntitlement


class TenantModuleEntitlementRepository(TenantScopedRepository[TenantModuleEntitlement]):
    model = TenantModuleEntitlement

    async def get_by_module_key(self, module_key: str) -> TenantModuleEntitlement | None:
        stmt = self._base_query().where(TenantModuleEntitlement.module_key == module_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[TenantModuleEntitlement]:
        stmt = self._base_query().order_by(TenantModuleEntitlement.module_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
