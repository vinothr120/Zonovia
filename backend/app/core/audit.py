import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog


async def write_audit_log(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """The single write path for audit_logs (docs/database.md) — every module calls this
    same function from its service layer rather than inserting rows itself, so the audit
    trail can't be bypassed by a bug in a new module. Confirmed as a deliberate, two-product
    Virasaka convention (SchoolAssist, CMS) — not an oversight to "improve" with ORM event
    listeners."""
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
        )
    )
    await session.flush()
