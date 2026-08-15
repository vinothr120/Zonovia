import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import AuditColumnsMixin, Base, IdMixin, TenantScopedBase, TenantScopedMixin, TimestampMixin, utcnow


class LifecycleStateDefinition(TenantScopedBase):
    """Tenant-configurable node in the lifecycle state machine — see app/flow/service.py's
    ensure_default_lifecycle_seeded for the default 13-state graph lazily seeded per tenant
    on first use."""

    __tablename__ = "lifecycle_state_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_lifecycle_state_definitions_tenant_key"),)

    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LifecycleTransitionDefinition(TenantScopedBase):
    """An edge list: from_state_id -> to_state_id, both NOT NULL — a transition definition is
    unambiguously a real edge; the only bootstrap path is the target state's is_initial flag,
    not a nullable 'any state' sentinel (see FlowService.transition_asset)."""

    __tablename__ = "lifecycle_transition_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "from_state_id", "to_state_id", name="uq_lifecycle_transition_definitions_tenant_edge"),
    )

    from_state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lifecycle_state_definitions.id"), nullable=False, index=True
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lifecycle_state_definitions.id"), nullable=False, index=True
    )


class AssetLifecycleTransition(Base, IdMixin, TenantScopedMixin):
    """Append-only history log — no separate 'audit' table for lifecycle state, mirroring the
    blueprint's own stated principle that transition/movement records are themselves the
    history. Same shape as app.audit.models.AuditLog: no timestamps/soft-delete mixins, its
    own bespoke `transitioned_at` column."""

    __tablename__ = "asset_lifecycle_transitions"

    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    from_state_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lifecycle_state_definitions.id"), nullable=True
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lifecycle_state_definitions.id"), nullable=False
    )
    transitioned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AssetAssignment(Base, IdMixin, TenantScopedMixin, TimestampMixin, AuditColumnsMixin):
    """Mutable history, TenantScopedBase minus soft-delete — nothing is deleted, only closed
    out via `unassigned_at`. A row with unassigned_at IS NULL is the current custody (this IS
    the blueprint's CustodyRecord concept — no separate table). 'One active assignment per
    asset' is enforced in the service layer (query for unassigned_at IS NULL before
    inserting), not a DB partial index, to stay portable to the SQLite test tier."""

    __tablename__ = "asset_assignments"

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    custodian_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()")
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AssetMovement(Base, IdMixin, TenantScopedMixin):
    """Append-only, same shape as AuditLog/AssetLifecycleTransition."""

    __tablename__ = "asset_movements"

    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"), index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=True
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("asset_locations.id"), nullable=False)
    moved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
