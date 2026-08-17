"""workflow schema — Phase 7: workflow_definitions, approval_step_definitions,
approval_instances, approval_instance_steps, notifications

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-17

users.id already exists by this point, so every FK to it here is a normal (non-deferred) FK.
app.workflow is a standalone engine this increment — no FK to assets or any other module's
table; entity_type/entity_id are plain columns, matching the blueprint's own dependency row
("Workflow depends only on Identity & Tenancy (roles)"). Order matters within this file only:
workflow_definitions -> approval_step_definitions -> approval_instances (FKs
workflow_definitions.id) -> approval_instance_steps (FKs both approval_instances.id and,
nullably, approval_step_definitions.id) -> notifications (no FK to any other table in this
migration, ordered last for readability only).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
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


def _tenant_id_col():
    return sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        _id_col(),
        _tenant_id_col(),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("condition_attribute", sa.String(100), nullable=True),
        sa.Column("condition_operator", sa.String(10), nullable=True),
        sa.Column("condition_value", postgresql.JSONB(), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "approval_step_definitions",
        _id_col(),
        _tenant_id_col(),
        sa.Column(
            "workflow_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_definitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approver_role_key", sa.String(100), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "approval_instances",
        _id_col(),
        _tenant_id_col(),
        sa.Column(
            "workflow_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_definitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("current_sequence_order", sa.Integer(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "approval_instance_steps",
        _id_col(),
        _tenant_id_col(),
        sa.Column(
            "approval_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_instances.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "step_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_step_definitions.id"),
            nullable=True,
        ),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approver_role_key", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )

    op.create_table(
        "notifications",
        _id_col(),
        _tenant_id_col(),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String(2000), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_cols(),
        *_audit_cols(),
        _soft_delete_col(),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("approval_instance_steps")
    op.drop_table("approval_instances")
    op.drop_table("approval_step_definitions")
    op.drop_table("workflow_definitions")
