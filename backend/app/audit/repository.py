from sqlalchemy import select

from app.audit.models import AuditLog
from app.core.base_repository import TenantScopedRepository


class AuditLogRepository(TenantScopedRepository[AuditLog]):
    """AuditLog has no deleted_at (append-only, never soft-deleted) so the base query is
    overridden rather than relying on TenantScopedRepository's default deleted_at filter."""

    model = AuditLog

    def _base_query(self, *, include_deleted: bool = False):  # noqa: ARG002 — signature matches the base class it overrides
        return select(self.model).where(self.model.tenant_id == self.tenant_id).order_by(self.model.occurred_at.desc())
