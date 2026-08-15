from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditLogRepository
from app.audit.schemas import AuditLogRead
from app.core.deps import TokenPayload, get_db, get_token_payload, require_permission
from app.core.pagination import PageParams, page_params
from app.core.response import PageMeta, ok

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("audit_logs.view")),
):
    repo = AuditLogRepository(db, payload.tenant_id)
    logs = await repo.list(offset=pagination.offset, limit=pagination.limit)
    total = await repo.count()
    return ok(
        [AuditLogRead.model_validate(log).model_dump() for log in logs],
        meta=PageMeta(page=pagination.page, page_size=pagination.page_size, total=total),
    )
