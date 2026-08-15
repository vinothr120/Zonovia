import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.module_registry import get_registered_modules
from app.entitlements.models import TenantModuleEntitlement
from app.entitlements.repository import TenantModuleEntitlementRepository
from app.entitlements.schemas import ModuleEntitlementRead


class EntitlementService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.entitlements = TenantModuleEntitlementRepository(session, tenant_id)

    async def is_enabled(self, module_key: str) -> bool:
        """The Entitlement Check itself (blueprint §18, ADR-007): a live DB lookup against
        the tenant's TenantModuleEntitlement row. If none exists yet, falls back to the
        module's own ModuleDefinition.default_enabled — a tenant is entitled to a module by
        default the moment it's registered, until something (seed data or a platform admin)
        explicitly says otherwise."""
        row = await self.entitlements.get_by_module_key(module_key)
        if row is not None:
            return row.enabled
        module = get_registered_modules().get(module_key)
        return module.default_enabled if module is not None else False

    async def list_for_tenant(self) -> list[ModuleEntitlementRead]:
        """Every registered module, joined against this tenant's entitlement rows (if any) —
        the source list for GET /api/v1/admin/modules."""
        rows_by_key = {row.module_key: row for row in await self.entitlements.list_all()}
        results: list[ModuleEntitlementRead] = []
        for module in get_registered_modules().values():
            row = rows_by_key.get(module.key)
            if row is not None:
                enabled, source = row.enabled, row.source
            else:
                enabled, source = module.default_enabled, "default"
            results.append(
                ModuleEntitlementRead(
                    module_key=module.key,
                    display_name=module.display_name,
                    always_on=module.always_on,
                    enabled=enabled,
                    source=source,
                )
            )
        return sorted(results, key=lambda r: r.module_key)

    async def set_enabled(self, *, module_key: str, enabled: bool, actor_user_id: uuid.UUID | None) -> TenantModuleEntitlement:
        row = await self.entitlements.get_by_module_key(module_key)
        old_value = {"enabled": row.enabled} if row is not None else None
        if row is None:
            row = self.entitlements.add(TenantModuleEntitlement(module_key=module_key, enabled=enabled, source="manual"))
        else:
            row.enabled = enabled
            row.source = "manual"
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="entitlement.updated",
            entity_type="tenant_module_entitlement",
            entity_id=row.id,
            old_value=old_value,
            new_value={"module_key": module_key, "enabled": enabled},
        )
        return row
