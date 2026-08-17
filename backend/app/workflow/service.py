import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.base_model import utcnow
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationAppError
from app.users.repository import RoleRepository, UserRepository, UserRoleRepository
from app.workflow.models import (
    _CONDITION_OPERATORS,
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalStepDefinition,
    Notification,
    WorkflowDefinition,
)
from app.workflow.repository import (
    ApprovalInstanceRepository,
    ApprovalInstanceStepRepository,
    ApprovalStepDefinitionRepository,
    NotificationRepository,
    WorkflowDefinitionRepository,
)

# Sentinel distinguishing "field omitted from the PATCH body" from "field explicitly sent as
# null" — needed only for update_step's approver_user_id/approver_role_key pair, since that XOR
# pair deliberately deviates from the ambient "None = don't touch" PATCH convention (see the
# module's implementation plan). The router passes this when the field name isn't present in
# the request body's `model_fields_set`.
UNSET: Any = object()


def _condition_matches(definition: WorkflowDefinition, context: dict) -> bool:
    """A missing context key or a type-mismatched comparison must never raise — it just means
    this definition doesn't match, the same "fail closed to no-match, not to an error" rule as
    every other guard in this service. `condition_attribute is None` means "no condition set",
    which always matches every instance of the entity_type."""
    if definition.condition_attribute is None:
        return True
    if definition.condition_attribute not in context:
        return False

    actual = context[definition.condition_attribute]
    expected = definition.condition_value
    operator = definition.condition_operator
    try:
        if operator == "eq":
            return bool(actual == expected)
        if operator == "ne":
            return bool(actual != expected)
        if operator == "gt":
            return bool(actual > expected)
        if operator == "gte":
            return bool(actual >= expected)
        if operator == "lt":
            return bool(actual < expected)
        if operator == "lte":
            return bool(actual <= expected)
    except TypeError:
        # e.g. comparing a str context value against a numeric condition_value with >/< — a
        # type mismatch, not a match.
        return False
    return False


def _validate_condition_triple(attribute: str | None, operator: str | None, value: Any) -> None:
    """All-three-or-none — condition_attribute/condition_operator/condition_value are a single
    logical unit, not three independent optional fields. A bare "compare to JSON null" isn't a
    supported use case in this MVP, so condition_value counts toward the guard exactly like the
    other two."""
    set_count = sum(field is not None for field in (attribute, operator, value))
    if set_count not in (0, 3):
        raise ValidationAppError(
            "condition_attribute, condition_operator, and condition_value must all be set together, or all omitted."
        )
    if operator is not None and operator not in _CONDITION_OPERATORS:
        raise ValidationAppError(f"Unsupported condition_operator '{operator}'. Allowed: {', '.join(_CONDITION_OPERATORS)}.")


class WorkflowService:
    """Generic approval engine. Depends on its own 5 repositories plus RoleRepository/
    UserRoleRepository/UserRepository from app.users.repository (read-only — the concrete
    implementation of the blueprint's "Workflow depends on Identity & Tenancy (roles)")."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.definitions = WorkflowDefinitionRepository(session, tenant_id)
        self.steps = ApprovalStepDefinitionRepository(session, tenant_id)
        self.instances = ApprovalInstanceRepository(session, tenant_id)
        self.instance_steps = ApprovalInstanceStepRepository(session, tenant_id)
        self.notifications = NotificationRepository(session, tenant_id)
        self.roles = RoleRepository(session, tenant_id)
        self.user_roles = UserRoleRepository(session, tenant_id)
        self.users = UserRepository(session, tenant_id)

    # -- approver resolution ------------------------------------------------------------------
    async def _check_approver_exists(self, *, approver_user_id: uuid.UUID | None, approver_role_key: str | None) -> None:
        if approver_user_id is not None and await self.users.get_by_id(approver_user_id) is None:
            raise NotFoundError("Approver user not found.")
        if approver_role_key is not None and await self.roles.get_by_name(approver_role_key) is None:
            raise NotFoundError(f"Approver role '{approver_role_key}' not found.")

    async def _resolve_approver_user_ids(self, step: ApprovalStepDefinition | ApprovalInstanceStep) -> list[uuid.UUID]:
        if step.approver_user_id is not None:
            return [step.approver_user_id]
        if step.approver_role_key is not None:
            role = await self.roles.get_by_name(step.approver_role_key)
            if role is None:
                return []
            return await self.user_roles.list_user_ids_for_role(role.id)
        return []

    async def _is_assignee(self, step: ApprovalInstanceStep, actor_user_id: uuid.UUID | None) -> bool:
        if actor_user_id is None:
            return False
        if step.approver_user_id is not None:
            return step.approver_user_id == actor_user_id
        if step.approver_role_key is not None:
            role = await self.roles.get_by_name(step.approver_role_key)
            if role is None:
                return False
            member_ids = await self.user_roles.list_user_ids_for_role(role.id)
            return actor_user_id in member_ids
        return False

    async def _notify_users(
        self,
        user_ids: set[uuid.UUID],
        *,
        notification_type: str,
        title: str,
        body: str | None,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> None:
        for user_id in user_ids:
            self.notifications.add(
                Notification(
                    recipient_user_id=user_id,
                    type=notification_type,
                    title=title,
                    body=body,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )
        if user_ids:
            await self.session.flush()

    async def _notify_group(self, instance: ApprovalInstance, group_steps: list[ApprovalInstanceStep]) -> None:
        recipient_ids: set[uuid.UUID] = set()
        for step in group_steps:
            recipient_ids.update(await self._resolve_approver_user_ids(step))
        await self._notify_users(
            recipient_ids,
            notification_type="approval_pending",
            title="Approval requested",
            body=f"An approval step is waiting on you for {instance.entity_type} {instance.entity_id}.",
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
        )

    async def _notify_requester(self, instance: ApprovalInstance, *, resolution: str) -> None:
        if instance.requested_by is None:
            return
        await self._notify_users(
            {instance.requested_by},
            notification_type="approval_resolved",
            title=f"Approval {resolution}",
            body=f"Your approval request for {instance.entity_type} {instance.entity_id} was {resolution}.",
            entity_type=instance.entity_type,
            entity_id=instance.entity_id,
        )

    # -- definitions ----------------------------------------------------------------------------
    async def create_definition(
        self,
        *,
        entity_type: str,
        name: str,
        is_active: bool,
        condition_attribute: str | None,
        condition_operator: str | None,
        condition_value: Any,
        steps: list[dict[str, Any]],
        actor_user_id: uuid.UUID | None,
    ) -> WorkflowDefinition:
        if not entity_type or not entity_type.strip():
            raise ValidationAppError("entity_type must not be empty.")
        _validate_condition_triple(condition_attribute, condition_operator, condition_value)
        if not steps:
            raise ValidationAppError("A workflow definition needs at least one approval step.")
        for step in steps:
            approver_user_id = step.get("approver_user_id")
            approver_role_key = step.get("approver_role_key")
            if (approver_user_id is None) == (approver_role_key is None):
                raise ValidationAppError("Each step must set exactly one of approver_user_id or approver_role_key.")
            await self._check_approver_exists(approver_user_id=approver_user_id, approver_role_key=approver_role_key)

        definition = self.definitions.add(
            WorkflowDefinition(
                entity_type=entity_type,
                name=name,
                is_active=is_active,
                condition_attribute=condition_attribute,
                condition_operator=condition_operator,
                condition_value=condition_value,
            )
        )
        await self.session.flush()
        for step in steps:
            self.steps.add(
                ApprovalStepDefinition(
                    workflow_definition_id=definition.id,
                    sequence_order=step["sequence_order"],
                    approver_user_id=step.get("approver_user_id"),
                    approver_role_key=step.get("approver_role_key"),
                )
            )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="workflow_definition.created",
            entity_type="workflow_definition",
            entity_id=definition.id,
            new_value={"entity_type": entity_type, "name": name, "step_count": len(steps)},
        )
        return definition

    async def get_definition_or_404(self, definition_id: uuid.UUID) -> WorkflowDefinition:
        definition = await self.definitions.get_by_id(definition_id)
        if definition is None:
            raise NotFoundError("Workflow definition not found.")
        return definition

    async def list_definitions(
        self, *, entity_type: str | None = None, is_active: bool | None = None
    ) -> list[WorkflowDefinition]:
        return await self.definitions.list_filtered(entity_type=entity_type, is_active=is_active)

    async def update_definition(
        self,
        *,
        definition_id: uuid.UUID,
        name: str | None,
        is_active: bool | None,
        condition_attribute: str | None,
        condition_operator: str | None,
        condition_value: Any,
        actor_user_id: uuid.UUID | None,
    ) -> WorkflowDefinition:
        """Ambient "None = don't touch" PATCH convention — unlike update_step, this trio isn't
        given a tri-state sentinel; changing the condition means sending all three non-None
        together (re-validated here exactly like create_definition), same limitation as every
        other PATCH in this codebase (e.g. MaintenanceService.update_ticket's cost field)."""
        definition = await self.get_definition_or_404(definition_id)
        if any(field is not None for field in (condition_attribute, condition_operator, condition_value)):
            _validate_condition_triple(condition_attribute, condition_operator, condition_value)

        old_value = {"name": definition.name, "is_active": definition.is_active}
        if name is not None:
            definition.name = name
        if is_active is not None:
            definition.is_active = is_active
        if condition_attribute is not None or condition_operator is not None or condition_value is not None:
            definition.condition_attribute = condition_attribute
            definition.condition_operator = condition_operator
            definition.condition_value = condition_value
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="workflow_definition.updated",
            entity_type="workflow_definition",
            entity_id=definition.id,
            old_value=old_value,
            new_value={"name": definition.name, "is_active": definition.is_active},
        )
        return definition

    async def delete_definition(self, *, definition_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        """Soft delete — safe since running ApprovalInstances are self-contained snapshots
        (ApprovalInstanceStep never re-reads its source ApprovalStepDefinition)."""
        definition = await self.get_definition_or_404(definition_id)
        await self.definitions.soft_delete(definition, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="workflow_definition.deleted",
            entity_type="workflow_definition",
            entity_id=definition.id,
            old_value={"name": definition.name},
        )

    # -- steps ------------------------------------------------------------------------------------
    async def list_steps(self, definition_id: uuid.UUID) -> list[ApprovalStepDefinition]:
        return await self.steps.list_for_definition(definition_id)

    async def add_step(
        self,
        *,
        definition_id: uuid.UUID,
        sequence_order: int,
        approver_user_id: uuid.UUID | None,
        approver_role_key: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> ApprovalStepDefinition:
        definition = await self.get_definition_or_404(definition_id)
        if (approver_user_id is None) == (approver_role_key is None):
            raise ValidationAppError("Exactly one of approver_user_id or approver_role_key must be set.")
        await self._check_approver_exists(approver_user_id=approver_user_id, approver_role_key=approver_role_key)

        step = self.steps.add(
            ApprovalStepDefinition(
                workflow_definition_id=definition.id,
                sequence_order=sequence_order,
                approver_user_id=approver_user_id,
                approver_role_key=approver_role_key,
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_step_definition.created",
            entity_type="approval_step_definition",
            entity_id=step.id,
            new_value={
                "workflow_definition_id": str(definition.id),
                "sequence_order": sequence_order,
                "approver_user_id": str(approver_user_id) if approver_user_id else None,
                "approver_role_key": approver_role_key,
            },
        )
        return step

    async def get_step_or_404(self, step_id: uuid.UUID) -> ApprovalStepDefinition:
        step = await self.steps.get_by_id(step_id)
        if step is None:
            raise NotFoundError("Approval step definition not found.")
        return step

    async def update_step(
        self,
        *,
        step_id: uuid.UUID,
        sequence_order: int | None,
        approver_user_id: Any = UNSET,
        approver_role_key: Any = UNSET,
        actor_user_id: uuid.UUID | None,
    ) -> ApprovalStepDefinition:
        """Deliberate deviation from the ambient "None = don't touch" PATCH convention:
        approver_user_id/approver_role_key is an XOR pair, so a partial-field PATCH can't
        safely express "switch from role-based to user-based." Both fields must be sent
        together (as UNSET or not, in lockstep) whenever either changes — see the module's
        implementation plan. sequence_order keeps the ordinary ambient convention since it
        isn't part of the XOR pair."""
        step = await self.get_step_or_404(step_id)

        user_given = approver_user_id is not UNSET
        role_given = approver_role_key is not UNSET
        if user_given != role_given:
            raise ValidationAppError("approver_user_id and approver_role_key must be sent together whenever either one changes.")

        old_value = {
            "sequence_order": step.sequence_order,
            "approver_user_id": str(step.approver_user_id) if step.approver_user_id else None,
            "approver_role_key": step.approver_role_key,
        }
        if sequence_order is not None:
            step.sequence_order = sequence_order
        if user_given and role_given:
            if (approver_user_id is None) == (approver_role_key is None):
                raise ValidationAppError("Exactly one of approver_user_id or approver_role_key must be set.")
            await self._check_approver_exists(approver_user_id=approver_user_id, approver_role_key=approver_role_key)
            step.approver_user_id = approver_user_id
            step.approver_role_key = approver_role_key
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_step_definition.updated",
            entity_type="approval_step_definition",
            entity_id=step.id,
            old_value=old_value,
            new_value={
                "sequence_order": step.sequence_order,
                "approver_user_id": str(step.approver_user_id) if step.approver_user_id else None,
                "approver_role_key": step.approver_role_key,
            },
        )
        return step

    async def delete_step(self, *, step_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        step = await self.get_step_or_404(step_id)
        siblings = await self.steps.list_for_definition(step.workflow_definition_id)
        if len(siblings) <= 1:
            raise ConflictError("Cannot delete the last remaining step of a workflow definition.")
        await self.steps.soft_delete(step, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_step_definition.deleted",
            entity_type="approval_step_definition",
            entity_id=step.id,
            old_value={"sequence_order": step.sequence_order},
        )

    # -- instances --------------------------------------------------------------------------------
    async def evaluate_and_maybe_open(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        context: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> ApprovalInstance | None:
        """(1) an existing open instance for this exact entity blocks a duplicate. (2) the
        first active definition for entity_type whose condition matches context wins — no
        match, no candidate, and no ambiguity between multiple matches is resolved beyond
        "first by creation order" (see WorkflowDefinitionRepository.list_active_for_entity_type).
        (3) opens the instance plus one ApprovalInstanceStep per step definition upfront, for
        full traceability. (4) notifies every approver in the first group."""
        if await self.instances.get_open_for_entity(entity_type, entity_id) is not None:
            return None

        candidates = await self.definitions.list_active_for_entity_type(entity_type)
        matched: WorkflowDefinition | None = None
        for candidate in candidates:
            if _condition_matches(candidate, context):
                matched = candidate
                break
        if matched is None:
            return None

        step_defs = await self.steps.list_for_definition(matched.id)
        if not step_defs:
            return None

        instance = self.instances.add(
            ApprovalInstance(
                workflow_definition_id=matched.id,
                entity_type=entity_type,
                entity_id=entity_id,
                status="pending",
                current_sequence_order=min(s.sequence_order for s in step_defs),
                context=context,
                requested_by=actor_user_id,
            )
        )
        await self.session.flush()

        instance_steps: list[ApprovalInstanceStep] = []
        for step_def in step_defs:
            instance_steps.append(
                self.instance_steps.add(
                    ApprovalInstanceStep(
                        approval_instance_id=instance.id,
                        step_definition_id=step_def.id,
                        sequence_order=step_def.sequence_order,
                        approver_user_id=step_def.approver_user_id,
                        approver_role_key=step_def.approver_role_key,
                        status="pending",
                    )
                )
            )
        await self.session.flush()

        first_group = [s for s in instance_steps if s.sequence_order == instance.current_sequence_order]
        await self._notify_group(instance, first_group)

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_instance.opened",
            entity_type="approval_instance",
            entity_id=instance.id,
            new_value={
                "workflow_definition_id": str(matched.id),
                "entity_type": entity_type,
                "entity_id": str(entity_id),
            },
        )
        return instance

    async def get_instance_or_404(self, instance_id: uuid.UUID) -> ApprovalInstance:
        instance = await self.instances.get_by_id(instance_id)
        if instance is None:
            raise NotFoundError("Approval instance not found.")
        return instance

    async def list_instances(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[ApprovalInstance]:
        return await self.instances.list_filtered(entity_type=entity_type, entity_id=entity_id, status=status)

    async def list_instance_steps(self, instance_id: uuid.UUID) -> list[ApprovalInstanceStep]:
        return await self.instance_steps.list_for_instance(instance_id)

    async def _get_actionable_step(self, instance_step_id: uuid.UUID) -> tuple[ApprovalInstanceStep, ApprovalInstance]:
        """Shared guard chain for approve_step/reject_step, up to (but not including) the
        assignee check: exists -> parent still pending -> step's group is the current group ->
        step still pending."""
        step = await self.instance_steps.get_by_id(instance_step_id)
        if step is None:
            raise NotFoundError("Approval instance step not found.")
        instance = await self.instances.get_by_id(step.approval_instance_id)
        if instance is None:
            raise NotFoundError("Approval instance not found.")
        if instance.status != "pending":
            raise ConflictError(f"Cannot decide a step on an instance in status '{instance.status}'.")
        if step.sequence_order != instance.current_sequence_order:
            raise ConflictError("This step is not in the currently actionable approval group.")
        if step.status != "pending":
            raise ConflictError(f"This step has already been decided (status '{step.status}').")
        return step, instance

    async def approve_step(self, *, instance_step_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> ApprovalInstanceStep:
        step, instance = await self._get_actionable_step(instance_step_id)
        if not await self._is_assignee(step, actor_user_id):
            raise PermissionDeniedError("You are not the assignee for this approval step.")

        step.status = "approved"
        step.decided_by = actor_user_id
        step.decided_at = utcnow()
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_instance_step.approved",
            entity_type="approval_instance_step",
            entity_id=step.id,
            new_value={"approval_instance_id": str(instance.id), "sequence_order": step.sequence_order},
        )

        group = await self.instance_steps.list_for_instance_and_sequence(instance.id, step.sequence_order)
        if all(s.status == "approved" for s in group):
            all_steps = await self.instance_steps.list_for_instance(instance.id)
            pending_later = [s for s in all_steps if s.status == "pending" and s.sequence_order > step.sequence_order]
            if pending_later:
                next_sequence = min(s.sequence_order for s in pending_later)
                instance.current_sequence_order = next_sequence
                await self.session.flush()
                next_group = [s for s in pending_later if s.sequence_order == next_sequence]
                await self._notify_group(instance, next_group)
                await write_audit_log(
                    self.session,
                    tenant_id=self.tenant_id,
                    actor_user_id=actor_user_id,
                    action="approval_instance.advanced",
                    entity_type="approval_instance",
                    entity_id=instance.id,
                    new_value={"current_sequence_order": next_sequence},
                )
            else:
                instance.status = "approved"
                instance.current_sequence_order = None
                instance.resolved_at = utcnow()
                await self.session.flush()
                await self._notify_requester(instance, resolution="approved")
                await write_audit_log(
                    self.session,
                    tenant_id=self.tenant_id,
                    actor_user_id=actor_user_id,
                    action="approval_instance.approved",
                    entity_type="approval_instance",
                    entity_id=instance.id,
                )
        return step

    async def reject_step(self, *, instance_step_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> ApprovalInstanceStep:
        """Rejecting any single step immediately resolves the entire instance as rejected and
        bulk-skips every other still-pending step (current and future groups) — no
        partial-continuation semantics."""
        step, instance = await self._get_actionable_step(instance_step_id)
        if not await self._is_assignee(step, actor_user_id):
            raise PermissionDeniedError("You are not the assignee for this approval step.")

        step.status = "rejected"
        step.decided_by = actor_user_id
        step.decided_at = utcnow()

        instance.status = "rejected"
        instance.current_sequence_order = None
        instance.resolved_at = utcnow()

        all_steps = await self.instance_steps.list_for_instance(instance.id)
        for sibling in all_steps:
            if sibling.id != step.id and sibling.status == "pending":
                sibling.status = "skipped"
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_instance_step.rejected",
            entity_type="approval_instance_step",
            entity_id=step.id,
            new_value={"approval_instance_id": str(instance.id), "sequence_order": step.sequence_order},
        )
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_instance.rejected",
            entity_type="approval_instance",
            entity_id=instance.id,
            new_value={"rejected_step_id": str(step.id)},
        )
        await self._notify_requester(instance, resolution="rejected")
        return step

    async def cancel_instance(self, *, instance_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> ApprovalInstance:
        instance = await self.get_instance_or_404(instance_id)
        if instance.status != "pending":
            raise ConflictError(f"Cannot cancel an instance in status '{instance.status}' — only 'pending' can be cancelled.")

        instance.status = "cancelled"
        instance.current_sequence_order = None
        instance.resolved_at = utcnow()

        all_steps = await self.instance_steps.list_for_instance(instance.id)
        for step in all_steps:
            if step.status == "pending":
                step.status = "skipped"
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="approval_instance.cancelled",
            entity_type="approval_instance",
            entity_id=instance.id,
        )
        await self._notify_requester(instance, resolution="cancelled")
        return instance

    # -- notifications ----------------------------------------------------------------------------
    async def list_for_user(self, user_id: uuid.UUID, *, unread_only: bool = False) -> list[Notification]:
        return await self.notifications.list_for_user(user_id, unread_only=unread_only)

    async def mark_read(self, *, notification_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> Notification:
        """No write_audit_log call here — a notification read is a side effect of an
        already-audited business event (e.g. approval_instance.opened), not an independently
        auditable one. See the module's implementation plan. Idempotent: marking an
        already-read notification read again is a no-op, not an error."""
        notification = await self.notifications.get_by_id(notification_id)
        if notification is None:
            raise NotFoundError("Notification not found.")
        if notification.recipient_user_id != actor_user_id:
            raise PermissionDeniedError("You can only mark your own notifications as read.")
        if notification.read_at is None:
            notification.read_at = utcnow()
            await self.session.flush()
        return notification
