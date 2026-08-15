import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(dt: datetime) -> datetime:
    """SQLite doesn't preserve tzinfo on DateTime(timezone=True) columns (Postgres does) —
    a value round-tripped through SQLite comes back naive. Every comparison against
    utcnow() that reads a stored datetime should go through this first, so the exact same
    service code behaves identically whether it's running against SQLite in tests or
    Postgres in production."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=text("now()")
    )


class AuditColumnsMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantScopedMixin:
    """Every tenant-scoped table gets its own tenant_id column (not inferred through joins) —
    this is what lets a single flat Postgres RLS policy apply uniformly, per docs/multi-tenancy.md.

    Uses SQLAlchemy's dialect-generic Uuid type (native UUID on Postgres, portable elsewhere)
    so the exact same models can build a SQLite schema for fast unit tests — RLS itself is
    Postgres-only and is covered separately by the integration tests in
    tests/test_tenant_isolation_postgres.py."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)


class TenantScopedBase(Base, IdMixin, TenantScopedMixin, TimestampMixin, AuditColumnsMixin, SoftDeleteMixin):
    """Base for every tenant-owned domain table. Platform-global tables (tenants itself,
    the permissions catalog, system roles) do not inherit this."""

    __abstract__ = True
