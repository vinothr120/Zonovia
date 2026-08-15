from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_permission, require_platform_admin
from app.core.pagination import PageParams, page_params
from app.core.response import PageMeta, ok
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate, TenantRead, TenantSettingRead, TenantSettingUpsert
from app.tenants.service import TenantService
from app.users.models import User

router = APIRouter(prefix="/platform/tenants", tags=["platform"])


@router.get("")
async def list_tenants(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_platform_admin()),
    _perm=Depends(require_permission("platform.manage_tenants")),
):
    repo = TenantRepository(db)
    tenants = await repo.list_all(offset=pagination.offset, limit=pagination.limit)
    return ok(
        [TenantRead.model_validate(t).model_dump() for t in tenants],
        meta=PageMeta(page=pagination.page, page_size=pagination.page_size, total=len(tenants)),
    )


@router.post("", status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _admin=Depends(require_platform_admin()),
    _perm=Depends(require_permission("platform.manage_tenants")),
):
    service = TenantService(db)
    tenant = await service.create_tenant(
        name=body.name, subdomain=body.subdomain, subscription_tier=body.subscription_tier, actor_user_id=actor.id
    )
    return ok(TenantRead.model_validate(tenant).model_dump())


settings_router = APIRouter(prefix="/tenants/me/settings", tags=["tenant-settings"])


@settings_router.get("")
async def list_my_settings(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tenants.view_settings")),
):
    service = TenantService(db, payload.tenant_id)
    settings = await service.list_settings()
    return ok([TenantSettingRead.model_validate(s).model_dump() for s in settings])


@settings_router.get("/{key}")
async def get_my_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("tenants.view_settings")),
):
    service = TenantService(db, payload.tenant_id)
    setting = await service.get_setting_or_404(key)
    return ok(TenantSettingRead.model_validate(setting).model_dump())


@settings_router.put("/{key}")
async def upsert_my_setting(
    key: str,
    body: TenantSettingUpsert,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("tenants.manage_settings")),
):
    service = TenantService(db, payload.tenant_id)
    setting = await service.upsert_setting(key=key, value=body.value, actor_user_id=actor.id)
    return ok(TenantSettingRead.model_validate(setting).model_dump())
