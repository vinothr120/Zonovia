import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError, NotFoundError
from app.tenants.models import Tenant, TenantConnectionRoute, TenantSetting
from app.tenants.repository import TenantConnectionRouteRepository, TenantRepository, TenantSettingRepository


class TenantService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID | None = None):
        self.session = session
        self.tenant_id = tenant_id
        self.tenants = TenantRepository(session)
        self.routes = TenantConnectionRouteRepository(session)
        # `settings` is only usable once a tenant_id is known (it's the tenant-scoped
        # /tenants/me/settings surface) — platform-level tenant CRUD below doesn't need it.
        self.settings = TenantSettingRepository(session, tenant_id) if tenant_id is not None else None

    async def create_tenant(
        self, *, name: str, subdomain: str, subscription_tier: str, actor_user_id: uuid.UUID | None
    ) -> Tenant:
        subdomain = subdomain.lower().strip()
        if await self.tenants.get_by_subdomain(subdomain) is not None:
            raise ConflictError(f"Subdomain '{subdomain}' is already in use.")

        tenant = self.tenants.add(Tenant(name=name, subdomain=subdomain, subscription_tier=subscription_tier))
        await self.session.flush()

        # Every Phase 0 tenant routes to the shared pool — see ADR-003 and
        # app.core.connection_router. Created here so the row always exists once a tenant
        # does, instead of being created lazily the first time something reads it.
        self.routes.add(TenantConnectionRoute(tenant_id=tenant.id, connection_mode="shared_pool"))
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=tenant.id,
            actor_user_id=actor_user_id,
            action="platform.tenant_created",
            entity_type="tenant",
            entity_id=tenant.id,
            new_value={"name": tenant.name, "subdomain": tenant.subdomain},
        )
        return tenant

    async def get_setting(self, key: str) -> TenantSetting | None:
        assert self.settings is not None
        return await self.settings.get_by_key(key)

    async def list_settings(self) -> list[TenantSetting]:
        assert self.settings is not None
        return await self.settings.list_all()

    async def upsert_setting(self, *, key: str, value, actor_user_id: uuid.UUID | None) -> TenantSetting:
        assert self.settings is not None and self.tenant_id is not None
        existing = await self.settings.get_by_key(key)
        old_value = existing.value if existing is not None else None

        if existing is None:
            setting = self.settings.add(TenantSetting(key=key, value=value))
        else:
            existing.value = value
            setting = existing
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="tenant_setting.upserted",
            entity_type="tenant_setting",
            entity_id=setting.id,
            old_value={"value": old_value} if existing is not None else None,
            new_value={"key": key, "value": value},
        )
        return setting

    async def get_setting_or_404(self, key: str) -> TenantSetting:
        setting = await self.get_setting(key)
        if setting is None:
            raise NotFoundError(f"No setting named '{key}' is configured for this tenant.")
        return setting
