import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import (
    AuditColumnsMixin,
    Base,
    IdMixin,
    SoftDeleteMixin,
    TenantScopedBase,
    TenantScopedMixin,
    TimestampMixin,
)


class User(TenantScopedBase):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active/inactive
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Role(Base, IdMixin, TimestampMixin, AuditColumnsMixin, SoftDeleteMixin):
    """tenant_id is nullable here (unlike every other domain table) because system roles
    (Platform Admin, Tenant Admin, Member, Viewer, ...) are shared catalog rows visible to
    every tenant. See the tenant_isolation_or_system RLS policy in migrations/versions/0002."""

    __tablename__ = "roles"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(Base, IdMixin):
    """Platform-global permission catalog. Not tenant-scoped, not RLS-protected — every
    tenant reads the same definitions; only role_permissions grants differ per role."""

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    module_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class RolePermission(Base):
    """Association table. Not independently RLS-protected — it's never queried without
    joining through roles, whose own visibility rule already governs it."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base, IdMixin, TenantScopedMixin, TimestampMixin, AuditColumnsMixin):
    """The grant, with scope. `scope_type`/`scope_id` keep the same column shape SchoolAssist
    uses for its school/campus-scoped roles, but Phase 0 only implements/validates
    `scope_type="tenant"` — there is no location concept yet (`AssetLocation` is Asset Core,
    Phase 1, per the blueprint's bounded-context table). This is a deliberately kept seam:
    Phase 1's location-scoped roles become a `UserService`/`grant_covers` code change, not a
    migration. See docs/authorization.md."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant")  # tenant only in Phase 0
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
