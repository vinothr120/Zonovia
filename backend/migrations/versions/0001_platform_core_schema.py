"""platform core schema — Phase 0: tenancy, RBAC, entitlements, audit

Revision ID: 0001
Revises:
Create Date: 2026-08-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id_col():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _timestamp_cols():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _audit_cols():
    return [
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    ]


def _soft_delete_col():
    return sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)


def _tenant_id_col(nullable: bool = False):
    return sa.Column(
        "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=nullable, index=True
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ---- platform-global tables (no tenant_id / not RLS-protected) -------------------
    op.create_table(
        "tenants",
        _id_col(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subdomain", sa.String(100), nullable=False, unique=True),
        sa.Column("subscription_tier", sa.String(50), nullable=False, server_default="basic"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    # The Tenant Routing Table ADR-003 requires from Phase 0 (see app/tenants/models.py).
    # Platform-global / not RLS-protected — same reasoning as `tenants` itself.
    op.create_table(
        "tenant_connection_routes",
        _id_col(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, unique=True, index=True),
        sa.Column("connection_mode", sa.String(20), nullable=False, server_default="shared_pool"),
        sa.Column("dedicated_dsn_secret_ref", sa.String(255), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
    )

    op.create_table(
        "permissions",
        _id_col(),
        sa.Column("key", sa.String(150), nullable=False, unique=True),
        sa.Column("module_key", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_permissions_module_key", "permissions", ["module_key"])

    # ---- roles: tenant_id nullable (system roles are shared across tenants) ----------
    op.create_table(
        "roles",
        _id_col(),
        _tenant_id_col(nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_system_role", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
        ),
    )

    # ---- users & user_roles -----------------------------------------------------------
    op.create_table(
        "users",
        _id_col(),
        _tenant_id_col(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_roles",
        _id_col(),
        _tenant_id_col(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="tenant"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
    )

    # ---- configuration: flat tenant-level key/value settings store --------------------
    op.create_table(
        "tenant_settings",
        _id_col(),
        _tenant_id_col(),
        sa.Column("key", sa.String(150), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_tenant_key"),
    )
    op.create_index("ix_tenant_settings_key", "tenant_settings", ["key"])

    # ---- licensing & entitlements ------------------------------------------------------
    op.create_table(
        "tenant_module_entitlements",
        _id_col(),
        _tenant_id_col(),
        sa.Column("module_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(20), nullable=False, server_default="seed"),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
        sa.UniqueConstraint("tenant_id", "module_key", name="uq_tenant_module_entitlements_tenant_module"),
    )
    op.create_index("ix_tenant_module_entitlements_module_key", "tenant_module_entitlements", ["module_key"])

    # ---- auth & audit ---------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        _id_col(),
        _tenant_id_col(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_info", sa.String(255), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    op.create_table(
        "audit_logs",
        _id_col(),
        _tenant_id_col(),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("tenant_module_entitlements")
    op.drop_table("tenant_settings")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("tenant_connection_routes")
    op.drop_table("tenants")
