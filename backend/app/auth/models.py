import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import TenantScopedBase


class RefreshToken(TenantScopedBase):
    """Stores a hash of the refresh token, never the token itself — a leaked database
    backup shouldn't hand out usable sessions. Rotated on every use (old row revoked, new
    row issued) so a stolen-and-reused refresh token is detectable."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
