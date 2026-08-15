import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import AuditColumnsMixin, Base, IdMixin, SoftDeleteMixin, TenantScopedBase, TimestampMixin
from app.core.db_types import JSONVariant


class Tenant(Base, IdMixin, TimestampMixin, AuditColumnsMixin, SoftDeleteMixin):
    """The isolation boundary itself — not tenant-scoped (it IS the tenant), never RLS-filtered.
    See docs/multi-tenancy.md for why this is a separate entity from any future Site/Location
    concept (Asset Core, Phase 1)."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subscription_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="basic")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class TenantConnectionRoute(Base, IdMixin, TimestampMixin, AuditColumnsMixin):
    """The Tenant Routing Table ADR-003 requires from Phase 0: which physical database a
    tenant's requests resolve to. Not RLS-protected — same reasoning as `tenants` itself,
    this table IS part of the platform-global routing/control plane, not tenant-owned data.
    Every Phase 0 row is 'shared_pool'; app.core.connection_router.resolve_session_factory
    is the only reader, and it ignores this row's contents entirely until Phase 9 (dedicated
    per-tenant databases for Private Cloud/Enterprise/On-Prem, per blueprint §9)."""

    __tablename__ = "tenant_connection_routes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id"), unique=True, nullable=False, index=True
    )
    connection_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="shared_pool")  # shared_pool|dedicated
    dedicated_dsn_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TenantSetting(TenantScopedBase):
    """The Configuration deliverable (blueprint §6/§7 Platform Core): a flat, schemaless
    key -> JSON store. Phase 0 ships storage + CRUD + audit logging and defines zero concrete
    keys — the first Phase 1+ module that needs a tenant-level setting defines its own key
    name, no schema change required."""

    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_tenant_key"),)

    key: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONVariant, nullable=False, default=dict)
