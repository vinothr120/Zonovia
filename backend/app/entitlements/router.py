from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_permission, require_platform_admin
from app.core.response import ok
from app.entitlements.schemas import ModuleEntitlementUpdate
from app.entitlements.service import EntitlementService
from app.users.models import User

router = APIRouter(prefix="/admin/modules", tags=["entitlements"])


@router.get("")
async def list_modules(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("entitlements.view")),
):
    service = EntitlementService(db, payload.tenant_id)
    modules = await service.list_for_tenant()
    return ok([m.model_dump() for m in modules])


@router.put("/{module_key}")
async def update_module_entitlement(
    module_key: str,
    body: ModuleEntitlementUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _admin=Depends(require_platform_admin()),
    _perm=Depends(require_permission("entitlements.manage")),
):
    service = EntitlementService(db, payload.tenant_id)
    row = await service.set_enabled(module_key=module_key, enabled=body.enabled, actor_user_id=actor.id)
    return ok({"module_key": row.module_key, "enabled": row.enabled, "source": row.source})
