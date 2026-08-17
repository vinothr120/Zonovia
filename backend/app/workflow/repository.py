import uuid

from app.core.base_repository import TenantScopedRepository
from app.workflow.models import (
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalStepDefinition,
    Notification,
    WorkflowDefinition,
)


class WorkflowDefinitionRepository(TenantScopedRepository[WorkflowDefinition]):
    model = WorkflowDefinition

    async def list_filtered(self, *, entity_type: str | None = None, is_active: bool | None = None) -> list[WorkflowDefinition]:
        stmt = self._base_query()
        if entity_type is not None:
            stmt = stmt.where(WorkflowDefinition.entity_type == entity_type)
        if is_active is not None:
            stmt = stmt.where(WorkflowDefinition.is_active == is_active)
        stmt = stmt.order_by(WorkflowDefinition.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_entity_type(self, entity_type: str) -> list[WorkflowDefinition]:
        """Used by WorkflowService.evaluate_and_maybe_open — created_at ascending, so "first
        active definition whose condition matches wins" is deterministic."""
        return await self.list_filtered(entity_type=entity_type, is_active=True)


class ApprovalStepDefinitionRepository(TenantScopedRepository[ApprovalStepDefinition]):
    model = ApprovalStepDefinition

    async def list_for_definition(self, definition_id: uuid.UUID) -> list[ApprovalStepDefinition]:
        stmt = (
            self._base_query()
            .where(ApprovalStepDefinition.workflow_definition_id == definition_id)
            .order_by(ApprovalStepDefinition.sequence_order.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ApprovalInstanceRepository(TenantScopedRepository[ApprovalInstance]):
    model = ApprovalInstance

    async def get_open_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> ApprovalInstance | None:
        """The duplicate-open guard's data access — WorkflowService.evaluate_and_maybe_open
        returns None immediately if this finds an existing pending instance."""
        stmt = self._base_query().where(
            ApprovalInstance.entity_type == entity_type,
            ApprovalInstance.entity_id == entity_id,
            ApprovalInstance.status == "pending",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[ApprovalInstance]:
        stmt = self._base_query()
        if entity_type is not None:
            stmt = stmt.where(ApprovalInstance.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ApprovalInstance.entity_id == entity_id)
        if status is not None:
            stmt = stmt.where(ApprovalInstance.status == status)
        stmt = stmt.order_by(ApprovalInstance.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ApprovalInstanceStepRepository(TenantScopedRepository[ApprovalInstanceStep]):
    model = ApprovalInstanceStep

    async def list_for_instance(self, instance_id: uuid.UUID) -> list[ApprovalInstanceStep]:
        stmt = (
            self._base_query()
            .where(ApprovalInstanceStep.approval_instance_id == instance_id)
            .order_by(ApprovalInstanceStep.sequence_order.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_instance_and_sequence(self, instance_id: uuid.UUID, sequence_order: int) -> list[ApprovalInstanceStep]:
        stmt = self._base_query().where(
            ApprovalInstanceStep.approval_instance_id == instance_id,
            ApprovalInstanceStep.sequence_order == sequence_order,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class NotificationRepository(TenantScopedRepository[Notification]):
    model = Notification

    async def list_for_user(self, user_id: uuid.UUID, *, unread_only: bool = False) -> list[Notification]:
        stmt = self._base_query().where(Notification.recipient_user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = stmt.order_by(Notification.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
