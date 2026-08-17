import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.repository import AssetLocationRepository, AssetRepository
from app.core.audit import write_audit_log
from app.core.base_model import utcnow
from app.core.exceptions import ConflictError, NotFoundError
from app.flow.models import (
    AssetAssignment,
    AssetLifecycleTransition,
    AssetMovement,
    LifecycleStateDefinition,
    LifecycleTransitionDefinition,
)
from app.flow.repository import (
    AssetAssignmentRepository,
    AssetLifecycleTransitionRepository,
    AssetMovementRepository,
    LifecycleStateDefinitionRepository,
    LifecycleTransitionDefinitionRepository,
)
from app.workflow.service import WorkflowService

# WorkflowService.evaluate_and_maybe_open's entity_type for asset lifecycle transitions — see
# transition_asset's call site and the module implementation plan's entity_id design decision
# (the transition row's own id, not the asset's id, so repeated matching transitions on the same
# asset each get an independent ApprovalInstance instead of being silently suppressed by the
# duplicate-open guard).
_WORKFLOW_ENTITY_TYPE = "asset_lifecycle_transition"

# The default lifecycle graph lazily seeded per tenant on first use (list_states or
# transition_asset — never from AssetService.create_asset, per the module dependency
# direction core -> asset-core -> flow). Fully editable afterward; not a fixed linear chain.
_DEFAULT_STATES: list[tuple[str, str, bool, bool]] = [
    # (key, label, is_initial, is_terminal)
    ("procured", "Procured", True, False),
    ("received", "Received", False, False),
    ("registered", "Registered", False, False),
    ("tagged", "Tagged", False, False),
    ("available", "Available", False, False),
    ("assigned", "Assigned", False, False),
    ("in_use", "In Use", False, False),
    ("transferred", "Transferred", False, False),
    ("under_maintenance", "Under Maintenance", False, False),
    ("lost", "Lost", False, False),
    ("damaged", "Damaged", False, False),
    ("retired", "Retired", False, False),
    ("disposed", "Disposed", False, True),
]

_DEFAULT_TRANSITIONS: list[tuple[str, str]] = [
    ("procured", "received"),
    ("received", "registered"),
    ("registered", "tagged"),
    ("tagged", "available"),
    ("available", "assigned"),
    ("assigned", "in_use"),
    ("in_use", "available"),
    ("assigned", "under_maintenance"),
    ("in_use", "under_maintenance"),
    ("under_maintenance", "available"),
    ("available", "transferred"),
    ("assigned", "transferred"),
    ("transferred", "available"),
    ("available", "lost"),
    ("assigned", "lost"),
    ("in_use", "lost"),
    ("lost", "available"),
    ("available", "damaged"),
    ("in_use", "damaged"),
    ("damaged", "under_maintenance"),
    ("damaged", "retired"),
    ("available", "retired"),
    ("under_maintenance", "retired"),
    ("retired", "disposed"),
]


class FlowService:
    """The configurable lifecycle engine, plus assignment/movement/history. Depends on
    asset-core (AssetRepository, AssetLocationRepository), never the reverse. The one deliberate
    exception is Workflow: transition_asset calls WorkflowService.evaluate_and_maybe_open (a
    genuine write, in the same transaction) to optionally open an ApprovalInstance for
    visibility — non-blocking, its return value is discarded, and it never gates or reverses a
    lifecycle transition."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.states = LifecycleStateDefinitionRepository(session, tenant_id)
        self.transition_defs = LifecycleTransitionDefinitionRepository(session, tenant_id)
        self.transitions = AssetLifecycleTransitionRepository(session, tenant_id)
        self.assignments = AssetAssignmentRepository(session, tenant_id)
        self.movements = AssetMovementRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)
        self.locations = AssetLocationRepository(session, tenant_id)

    async def ensure_default_lifecycle_seeded(self) -> None:
        """Idempotent — a tenant with any LifecycleStateDefinition row already is left
        untouched (its lifecycle may have already been hand-edited)."""
        if await self.states.any_exist():
            return

        states_by_key: dict[str, LifecycleStateDefinition] = {}
        for sort_order, (key, label, is_initial, is_terminal) in enumerate(_DEFAULT_STATES):
            state = self.states.add(
                LifecycleStateDefinition(
                    key=key, label=label, is_initial=is_initial, is_terminal=is_terminal, sort_order=sort_order
                )
            )
            states_by_key[key] = state
        await self.session.flush()

        for from_key, to_key in _DEFAULT_TRANSITIONS:
            self.transition_defs.add(
                LifecycleTransitionDefinition(from_state_id=states_by_key[from_key].id, to_state_id=states_by_key[to_key].id)
            )
        await self.session.flush()

    # -- lifecycle state/transition definitions (tenant configuration) ------------------
    async def list_states(self) -> list[LifecycleStateDefinition]:
        await self.ensure_default_lifecycle_seeded()
        return await self.states.list_all()

    async def get_state_or_404(self, state_id: uuid.UUID) -> LifecycleStateDefinition:
        state = await self.states.get_by_id(state_id)
        if state is None:
            raise NotFoundError("Lifecycle state not found.")
        return state

    async def create_state(
        self, *, key: str, label: str, is_initial: bool, is_terminal: bool, sort_order: int, actor_user_id: uuid.UUID | None
    ) -> LifecycleStateDefinition:
        await self.ensure_default_lifecycle_seeded()
        if await self.states.get_by_key(key) is not None:
            raise ConflictError(f"A lifecycle state with key '{key}' already exists.")
        state = self.states.add(
            LifecycleStateDefinition(key=key, label=label, is_initial=is_initial, is_terminal=is_terminal, sort_order=sort_order)
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="lifecycle_state.created",
            entity_type="lifecycle_state_definition",
            entity_id=state.id,
            new_value={"key": key, "label": label, "is_initial": is_initial, "is_terminal": is_terminal},
        )
        return state

    async def update_state(
        self,
        *,
        state_id: uuid.UUID,
        label: str | None,
        is_initial: bool | None,
        is_terminal: bool | None,
        sort_order: int | None,
        actor_user_id: uuid.UUID | None,
    ) -> LifecycleStateDefinition:
        state = await self.get_state_or_404(state_id)
        old_value = {"label": state.label, "is_initial": state.is_initial, "is_terminal": state.is_terminal}
        if label is not None:
            state.label = label
        if is_initial is not None:
            state.is_initial = is_initial
        if is_terminal is not None:
            state.is_terminal = is_terminal
        if sort_order is not None:
            state.sort_order = sort_order
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="lifecycle_state.updated",
            entity_type="lifecycle_state_definition",
            entity_id=state.id,
            old_value=old_value,
            new_value={"label": state.label, "is_initial": state.is_initial, "is_terminal": state.is_terminal},
        )
        return state

    async def delete_state(self, *, state_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        state = await self.get_state_or_404(state_id)
        referenced = await self.transition_defs.list_all()
        if any(t.from_state_id == state.id or t.to_state_id == state.id for t in referenced):
            raise ConflictError("Cannot delete a lifecycle state that is still referenced by a transition definition.")
        await self.states.soft_delete(state, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="lifecycle_state.deleted",
            entity_type="lifecycle_state_definition",
            entity_id=state.id,
            old_value={"key": state.key},
        )

    async def list_transition_definitions(self) -> list[LifecycleTransitionDefinition]:
        await self.ensure_default_lifecycle_seeded()
        return await self.transition_defs.list_all()

    async def create_transition_definition(
        self, *, from_state_id: uuid.UUID, to_state_id: uuid.UUID, actor_user_id: uuid.UUID | None
    ) -> LifecycleTransitionDefinition:
        await self.get_state_or_404(from_state_id)
        await self.get_state_or_404(to_state_id)
        if await self.transition_defs.get_by_edge(from_state_id=from_state_id, to_state_id=to_state_id) is not None:
            raise ConflictError("This transition is already defined.")
        transition_def = self.transition_defs.add(
            LifecycleTransitionDefinition(from_state_id=from_state_id, to_state_id=to_state_id)
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="lifecycle_transition_definition.created",
            entity_type="lifecycle_transition_definition",
            entity_id=transition_def.id,
            new_value={"from_state_id": str(from_state_id), "to_state_id": str(to_state_id)},
        )
        return transition_def

    async def delete_transition_definition(self, *, transition_def_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        transition_def = await self.transition_defs.get_by_id(transition_def_id)
        if transition_def is None:
            raise NotFoundError("Lifecycle transition definition not found.")
        await self.transition_defs.soft_delete(transition_def, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="lifecycle_transition_definition.deleted",
            entity_type="lifecycle_transition_definition",
            entity_id=transition_def.id,
            old_value={"from_state_id": str(transition_def.from_state_id), "to_state_id": str(transition_def.to_state_id)},
        )

    # -- asset lifecycle transitions -----------------------------------------------------
    async def transition_asset(
        self, *, asset_id: uuid.UUID, to_state_id: uuid.UUID, actor_user_id: uuid.UUID | None, note: str | None
    ) -> AssetLifecycleTransition:
        await self.ensure_default_lifecycle_seeded()
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        to_state = await self.get_state_or_404(to_state_id)

        current_state_id = asset.current_lifecycle_state_id
        if current_state_id is None:
            if not to_state.is_initial:
                raise ConflictError(
                    f"An asset with no lifecycle state yet can only transition into an initial state; '{to_state.label}' is not initial."
                )
        else:
            transition_def = await self.transition_defs.get_by_edge(from_state_id=current_state_id, to_state_id=to_state.id)
            if transition_def is None:
                raise ConflictError(f"No lifecycle transition is defined from the asset's current state to '{to_state.label}'.")

        history = self.transitions.add(
            AssetLifecycleTransition(
                asset_id=asset.id,
                from_state_id=current_state_id,
                to_state_id=to_state.id,
                transitioned_by=actor_user_id,
                note=note,
            )
        )
        asset.current_lifecycle_state_id = to_state.id
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.lifecycle_transitioned",
            entity_type="asset",
            entity_id=asset.id,
            old_value={"from_state_id": str(current_state_id) if current_state_id else None},
            new_value={"to_state_id": str(to_state.id), "to_state_key": to_state.key},
        )
        # Non-blocking, record-only integration: never gates or reverses the transition, return
        # value discarded. entity_id is history.id — this transition row's own id, NOT
        # asset.id — so repeated matching transitions on the same asset each open an
        # independent ApprovalInstance instead of being suppressed by evaluate_and_maybe_open's
        # duplicate-open guard (get_open_for_entity keys on the exact (entity_type, entity_id)
        # pair). `purchase_price` must be converted from Decimal to float before it enters
        # `context` (a JSON column) — a raw Decimal is not JSON-serializable, same hazard as
        # MaintenanceTicket.cost. See the module's implementation plan's design decision.
        from_state = await self.states.get_by_id(current_state_id) if current_state_id is not None else None
        await WorkflowService(self.session, self.tenant_id).evaluate_and_maybe_open(
            entity_type=_WORKFLOW_ENTITY_TYPE,
            entity_id=history.id,
            context={
                "purchase_price": float(asset.purchase_price) if asset.purchase_price is not None else None,
                "to_state_key": to_state.key,
                "from_state_key": from_state.key if from_state is not None else None,
            },
            actor_user_id=actor_user_id,
        )
        return history

    # -- custody --------------------------------------------------------------------------
    async def assign_custodian(
        self, *, asset_id: uuid.UUID, custodian_user_id: uuid.UUID, actor_user_id: uuid.UUID | None, note: str | None
    ) -> AssetAssignment:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        if await self.assignments.get_active_for_asset(asset_id) is not None:
            raise ConflictError("Asset already has an active assignment — unassign it before assigning a new custodian.")

        assignment = self.assignments.add(
            AssetAssignment(asset_id=asset.id, custodian_user_id=custodian_user_id, assigned_by=actor_user_id, note=note)
        )
        asset.current_custodian_id = custodian_user_id
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.assigned",
            entity_type="asset",
            entity_id=asset.id,
            new_value={"custodian_user_id": str(custodian_user_id)},
        )
        return assignment

    async def unassign_custodian(
        self, *, asset_id: uuid.UUID, actor_user_id: uuid.UUID | None, note: str | None
    ) -> AssetAssignment:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        active = await self.assignments.get_active_for_asset(asset_id)
        if active is None:
            raise NotFoundError("Asset has no active assignment to unassign.")

        active.unassigned_at = utcnow()
        if note is not None:
            active.note = note
        asset.current_custodian_id = None
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.unassigned",
            entity_type="asset",
            entity_id=asset.id,
            old_value={"custodian_user_id": str(active.custodian_user_id)},
        )
        return active

    # -- movement ---------------------------------------------------------------------------
    async def move_asset(
        self, *, asset_id: uuid.UUID, to_location_id: uuid.UUID, actor_user_id: uuid.UUID | None, note: str | None
    ) -> AssetMovement:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        if await self.locations.get_by_id(to_location_id) is None:
            raise NotFoundError("Asset location not found.")

        from_location_id = asset.current_location_id
        movement = self.movements.add(
            AssetMovement(
                asset_id=asset.id,
                from_location_id=from_location_id,
                to_location_id=to_location_id,
                moved_by=actor_user_id,
                note=note,
            )
        )
        asset.current_location_id = to_location_id
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.moved",
            entity_type="asset",
            entity_id=asset.id,
            old_value={"from_location_id": str(from_location_id) if from_location_id else None},
            new_value={"to_location_id": str(to_location_id)},
        )
        return movement

    # -- history -----------------------------------------------------------------------------
    async def get_asset_history(self, asset_id: uuid.UUID) -> list[dict]:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")

        entries: list[tuple[datetime, dict]] = []
        for t in await self.transitions.list_for_asset(asset_id):
            entries.append(
                (
                    t.transitioned_at,
                    {
                        "entry_type": "lifecycle_transition",
                        "occurred_at": t.transitioned_at,
                        "data": {
                            "id": str(t.id),
                            "from_state_id": str(t.from_state_id) if t.from_state_id else None,
                            "to_state_id": str(t.to_state_id),
                            "transitioned_by": str(t.transitioned_by) if t.transitioned_by else None,
                            "note": t.note,
                        },
                    },
                )
            )
        for a in await self.assignments.list_for_asset(asset_id):
            entries.append(
                (
                    a.assigned_at,
                    {
                        "entry_type": "assignment",
                        "occurred_at": a.assigned_at,
                        "data": {
                            "custodian_user_id": str(a.custodian_user_id),
                            "assigned_at": a.assigned_at.isoformat(),
                            "unassigned_at": a.unassigned_at.isoformat() if a.unassigned_at else None,
                            "note": a.note,
                        },
                    },
                )
            )
        for m in await self.movements.list_for_asset(asset_id):
            entries.append(
                (
                    m.moved_at,
                    {
                        "entry_type": "movement",
                        "occurred_at": m.moved_at,
                        "data": {
                            "from_location_id": str(m.from_location_id) if m.from_location_id else None,
                            "to_location_id": str(m.to_location_id),
                            "note": m.note,
                        },
                    },
                )
            )

        entries.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in entries]
