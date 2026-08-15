import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import Base, IdMixin, TenantScopedMixin, utcnow
from app.core.db_types import JSONVariant


class AuditLog(Base, IdMixin, TenantScopedMixin):
    """Append-only. No soft delete, no updated_at/updated_by — an audit trail that could be
    edited isn't an audit trail."""

    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    old_value: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
