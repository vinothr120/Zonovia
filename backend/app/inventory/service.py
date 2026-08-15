import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.models import Asset
from app.asset_core.repository import AssetLocationRepository, AssetRepository
from app.core.audit import write_audit_log
from app.core.base_model import utcnow
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.inventory.models import (
    _RECONCILIATION_ACTION_TYPES,
    InventoryCount,
    InventoryCycle,
    ReconciliationAction,
)
from app.inventory.repository import InventoryCountRepository, InventoryCycleRepository, ReconciliationActionRepository
from app.tracking.service import TrackingService


class InventoryService:
    """Cycle lifecycle + verification + reconciliation + reporting. Depends on asset-core
    (AssetRepository, AssetLocationRepository) and tracking-engine (TrackingService, composed
    directly and reused as-is — record_verification never reimplements scan resolution), never
    on flow: `record_reconciliation` purely persists a decision, it does not execute one. See
    the module's implementation plan for the full reasoning."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.cycles = InventoryCycleRepository(session, tenant_id)
        self.counts = InventoryCountRepository(session, tenant_id)
        self.reconciliations = ReconciliationActionRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)
        self.locations = AssetLocationRepository(session, tenant_id)
        self.tracking = TrackingService(session, tenant_id)

    # -- cycle lifecycle ------------------------------------------------------------------
    async def create_cycle(
        self, *, name: str, description: str | None, root_location_id: uuid.UUID | None, actor_user_id: uuid.UUID | None
    ) -> InventoryCycle:
        if root_location_id is not None and await self.locations.get_by_id(root_location_id) is None:
            raise NotFoundError("Asset location not found.")

        cycle = self.cycles.add(InventoryCycle(name=name, description=description, root_location_id=root_location_id))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_cycle.created",
            entity_type="inventory_cycle",
            entity_id=cycle.id,
            new_value={"name": name, "root_location_id": str(root_location_id) if root_location_id else None},
        )
        return cycle

    async def get_cycle_or_404(self, cycle_id: uuid.UUID) -> InventoryCycle:
        cycle = await self.cycles.get_by_id(cycle_id)
        if cycle is None:
            raise NotFoundError("Inventory cycle not found.")
        return cycle

    async def list_cycles(self, *, offset: int = 0, limit: int = 20) -> list[InventoryCycle]:
        return await self.cycles.list(offset=offset, limit=limit)

    async def start_cycle(self, *, cycle_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> InventoryCycle:
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.status != "draft":
            raise ConflictError(f"Cannot start a cycle in status '{cycle.status}' — only a 'draft' cycle can be started.")
        cycle.status = "in_progress"
        cycle.started_at = utcnow()
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_cycle.started",
            entity_type="inventory_cycle",
            entity_id=cycle.id,
        )
        return cycle

    async def complete_cycle(self, *, cycle_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> InventoryCycle:
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.status != "in_progress":
            raise ConflictError(
                f"Cannot complete a cycle in status '{cycle.status}' — only an 'in_progress' cycle can be completed."
            )
        # No completeness requirement here — missing/discrepant assets are the expected case,
        # surfaced by get_cycle_report, not blocked at completion time.
        cycle.status = "completed"
        cycle.completed_at = utcnow()
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_cycle.completed",
            entity_type="inventory_cycle",
            entity_id=cycle.id,
        )
        return cycle

    async def cancel_cycle(self, *, cycle_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> InventoryCycle:
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.status not in ("draft", "in_progress"):
            raise ConflictError(f"Cannot cancel a cycle in status '{cycle.status}'.")
        cycle.status = "cancelled"
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_cycle.cancelled",
            entity_type="inventory_cycle",
            entity_id=cycle.id,
        )
        return cycle

    # -- scope resolution -------------------------------------------------------------------
    async def list_expected_assets(self, cycle_id: uuid.UUID) -> list[Asset]:
        """None root_location_id -> every tenant asset; otherwise the root location plus every
        descendant (never sibling or ancestor locations) -> AssetRepository.list_by_location_ids."""
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.root_location_id is None:
            return await self.assets.list_all()

        descendants = await self.locations.list_descendants(cycle.root_location_id)
        location_ids = [cycle.root_location_id, *(loc.id for loc in descendants)]
        return await self.assets.list_by_location_ids(location_ids)

    # -- verification -------------------------------------------------------------------
    async def record_verification(
        self,
        *,
        cycle_id: uuid.UUID,
        identifier_type: str,
        raw_value: str,
        found_location_id: uuid.UUID | None,
        note: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> InventoryCount:
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.status != "in_progress":
            raise ConflictError(f"Cannot record a verification against a cycle in status '{cycle.status}'.")

        # Reused as-is, not reimplemented — its own 404/422 propagate unchanged, and no
        # InventoryCount is written on that path.
        asset, tracking_event = await self.tracking.record_scan(
            identifier_type=identifier_type, raw_value=raw_value, note=note, actor_user_id=actor_user_id
        )

        # Snapshotted NOW rather than read live from the report later, so it stays accurate
        # even if Flow moves the asset after this verification is recorded.
        expected_location_id = asset.current_location_id
        resolved_found_location_id = found_location_id if found_location_id is not None else expected_location_id
        has_discrepancy = resolved_found_location_id != expected_location_id

        count = self.counts.add(
            InventoryCount(
                cycle_id=cycle_id,
                asset_id=asset.id,
                verified_by=actor_user_id,
                expected_location_id=expected_location_id,
                found_location_id=resolved_found_location_id,
                has_discrepancy=has_discrepancy,
                condition_note=note,
                tracking_event_id=tracking_event.id,
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_count.recorded",
            entity_type="inventory_count",
            entity_id=count.id,
            new_value={
                "cycle_id": str(cycle_id),
                "asset_id": str(asset.id),
                "has_discrepancy": has_discrepancy,
                "tracking_event_id": str(tracking_event.id),
            },
        )
        return count

    async def list_counts_for_cycle(self, cycle_id: uuid.UUID) -> list[InventoryCount]:
        await self.get_cycle_or_404(cycle_id)
        return await self.counts.list_for_cycle(cycle_id)

    # -- reporting -------------------------------------------------------------------------
    async def get_cycle_report(self, cycle_id: uuid.UUID) -> dict:
        """Computed on demand, not stored — same convention as FlowService.get_asset_history.
        Missing = expected - verified (latest count per asset); discrepancies = latest counts
        flagged has_discrepancy. A re-scan that corrects an earlier wrong-location count
        always wins here, since list_latest_per_asset only ever returns the newest row."""
        cycle = await self.get_cycle_or_404(cycle_id)
        expected_assets = await self.list_expected_assets(cycle_id)
        expected_ids = [a.id for a in expected_assets]

        latest_counts = await self.counts.list_latest_per_asset(cycle_id)
        verified_ids = [c.asset_id for c in latest_counts]
        verified_id_set = set(verified_ids)
        missing_ids = [asset_id for asset_id in expected_ids if asset_id not in verified_id_set]
        discrepancies = [c for c in latest_counts if c.has_discrepancy]

        return {
            "cycle_id": cycle.id,
            "expected_asset_ids": expected_ids,
            "verified_asset_ids": verified_ids,
            "missing_asset_ids": missing_ids,
            "discrepancies": discrepancies,
        }

    # -- reconciliation -----------------------------------------------------------------
    async def record_reconciliation(
        self, *, cycle_id: uuid.UUID, asset_id: uuid.UUID, action_type: str, note: str | None, actor_user_id: uuid.UUID | None
    ) -> ReconciliationAction:
        """Purely persists the finding/decision — deliberately does NOT call FlowService or
        otherwise change the asset's current_location_id/current_lifecycle_state_id. Executing
        a decision is a separate, explicit follow-up call against Flow's own already-
        permissioned endpoints (the architecturally-intended seam for Phase 7's workflow
        engine, per the implementation plan)."""
        cycle = await self.get_cycle_or_404(cycle_id)
        if cycle.status not in ("in_progress", "completed"):
            raise ConflictError(f"Cannot record a reconciliation against a cycle in status '{cycle.status}'.")
        if action_type not in _RECONCILIATION_ACTION_TYPES:
            raise ValidationAppError(
                f"Unsupported reconciliation action type '{action_type}'. Allowed: {', '.join(_RECONCILIATION_ACTION_TYPES)}."
            )
        if await self.assets.get_by_id(asset_id) is None:
            raise NotFoundError("Asset not found.")

        action = self.reconciliations.add(
            ReconciliationAction(
                cycle_id=cycle_id, asset_id=asset_id, action_type=action_type, note=note, resolved_by=actor_user_id
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="inventory_reconciliation.recorded",
            entity_type="reconciliation_action",
            entity_id=action.id,
            new_value={"cycle_id": str(cycle_id), "asset_id": str(asset_id), "action_type": action_type},
        )
        return action

    async def list_reconciliations_for_cycle(self, cycle_id: uuid.UUID) -> list[ReconciliationAction]:
        await self.get_cycle_or_404(cycle_id)
        return await self.reconciliations.list_for_cycle(cycle_id)
