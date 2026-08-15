import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.repository import AssetRepository, VendorRepository
from app.core.audit import write_audit_log
from app.core.base_model import utcnow
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.flow.repository import LifecycleStateDefinitionRepository
from app.maintenance.models import _TICKET_PRIORITIES, MaintenanceTicket, ServiceSchedule, Warranty
from app.maintenance.repository import MaintenanceTicketRepository, ServiceScheduleRepository, WarrantyRepository


def _warranty_status(warranty: Warranty, *, today: date | None = None) -> dict:
    """Computed at read time, never stored — is_expired/days_remaining. `end_date == today` is
    the boundary: still valid through the whole of that day, so NOT expired and
    days_remaining == 0."""
    today = today or utcnow().date()
    return {"is_expired": today > warranty.end_date, "days_remaining": (warranty.end_date - today).days}


def _schedule_due_info(schedule: ServiceSchedule, *, today: date | None = None) -> dict:
    """Computed at read time, never stored — next_due_at/is_overdue. A never-serviced
    schedule (last_serviced_at is None) computes from created_at, not last_serviced_at — the
    never-serviced-yet edge case."""
    today = today or utcnow().date()
    base_date = schedule.last_serviced_at if schedule.last_serviced_at is not None else schedule.created_at.date()
    next_due_at = base_date + timedelta(days=schedule.interval_days)
    return {"next_due_at": next_due_at, "is_overdue": today > next_due_at}


class MaintenanceService:
    """Ticket lifecycle + warranty upsert + service-schedule management/reporting. Depends on
    asset-core (AssetRepository, VendorRepository) and a READ-ONLY
    app.flow.repository.LifecycleStateDefinitionRepository (key -> id resolution only) —
    never app.flow.service.FlowService, never transition_asset. See the module's
    implementation plan's "Flow dependency: read-only, not write-through" design decision."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.tickets = MaintenanceTicketRepository(session, tenant_id)
        self.warranties = WarrantyRepository(session, tenant_id)
        self.schedules = ServiceScheduleRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)
        self.vendors = VendorRepository(session, tenant_id)
        self.lifecycle_states = LifecycleStateDefinitionRepository(session, tenant_id)

    # -- tickets ----------------------------------------------------------------------------
    async def create_ticket(
        self,
        *,
        asset_id: uuid.UUID,
        service_schedule_id: uuid.UUID | None,
        title: str,
        description: str | None,
        priority: str | None,
        assigned_to: uuid.UUID | None,
        cost: Decimal | None,
        actor_user_id: uuid.UUID | None,
    ) -> MaintenanceTicket:
        if await self.assets.get_by_id(asset_id) is None:
            raise NotFoundError("Asset not found.")
        if service_schedule_id is not None:
            schedule = await self.schedules.get_by_id(service_schedule_id)
            if schedule is None:
                raise NotFoundError("Service schedule not found.")
            if schedule.asset_id != asset_id:
                raise ValidationAppError("The linked service schedule belongs to a different asset.")
        if priority is not None and priority not in _TICKET_PRIORITIES:
            raise ValidationAppError(f"Unsupported priority '{priority}'. Allowed: {', '.join(_TICKET_PRIORITIES)}.")

        ticket = self.tickets.add(
            MaintenanceTicket(
                asset_id=asset_id,
                service_schedule_id=service_schedule_id,
                title=title,
                description=description,
                priority=priority,
                assigned_to=assigned_to,
                cost=cost,
                reported_by=actor_user_id,
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="maintenance_ticket.created",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
            new_value={"asset_id": str(asset_id), "title": title, "priority": priority},
        )
        return ticket

    async def get_ticket_or_404(self, ticket_id: uuid.UUID) -> MaintenanceTicket:
        ticket = await self.tickets.get_by_id(ticket_id)
        if ticket is None:
            raise NotFoundError("Maintenance ticket not found.")
        return ticket

    async def list_tickets(
        self,
        *,
        status: str | None = None,
        asset_id: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        lifecycle_state_key: str | None = None,
    ) -> list[MaintenanceTicket]:
        """`lifecycle_state_key` resolves via the read-only LifecycleStateDefinitionRepository
        (key -> id) plus AssetRepository.list_by_lifecycle_state_id, then intersects with
        every other filter. An unknown key resolves to zero assets (not a 404) — this is a
        read-side convenience filter, not a resource lookup."""
        asset_ids: list[uuid.UUID] | None = None
        if lifecycle_state_key is not None:
            state = await self.lifecycle_states.get_by_key(lifecycle_state_key)
            if state is None:
                return []
            matching_assets = await self.assets.list_by_lifecycle_state_id(state.id)
            asset_ids = [a.id for a in matching_assets]
        return await self.tickets.list_filtered(status=status, asset_id=asset_id, assigned_to=assigned_to, asset_ids=asset_ids)

    async def update_ticket(
        self,
        *,
        ticket_id: uuid.UUID,
        title: str | None,
        description: str | None,
        priority: str | None,
        assigned_to: uuid.UUID | None,
        cost: Decimal | None,
        actor_user_id: uuid.UUID | None,
    ) -> MaintenanceTicket:
        ticket = await self.get_ticket_or_404(ticket_id)
        if ticket.status in ("completed", "cancelled"):
            raise ConflictError(f"Cannot update a ticket in terminal status '{ticket.status}'.")
        if priority is not None and priority not in _TICKET_PRIORITIES:
            raise ValidationAppError(f"Unsupported priority '{priority}'. Allowed: {', '.join(_TICKET_PRIORITIES)}.")

        old_value = {
            "title": ticket.title,
            "priority": ticket.priority,
            "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        }
        if title is not None:
            ticket.title = title
        if description is not None:
            ticket.description = description
        if priority is not None:
            ticket.priority = priority
        if assigned_to is not None:
            ticket.assigned_to = assigned_to
        if cost is not None:
            ticket.cost = cost
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="maintenance_ticket.updated",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
            old_value=old_value,
            new_value={
                "title": ticket.title,
                "priority": ticket.priority,
                "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
            },
        )
        return ticket

    async def start_ticket(self, *, ticket_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> MaintenanceTicket:
        ticket = await self.get_ticket_or_404(ticket_id)
        if ticket.status != "open":
            raise ConflictError(f"Cannot start a ticket in status '{ticket.status}' — only an 'open' ticket can be started.")
        ticket.status = "in_progress"
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="maintenance_ticket.started",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
        )
        return ticket

    async def complete_ticket(
        self, *, ticket_id: uuid.UUID, resolution_note: str | None, actor_user_id: uuid.UUID | None
    ) -> MaintenanceTicket:
        """Never touches Flow — the asset's current_lifecycle_state_id is left exactly as it
        was. Also never auto-triggers record_service on a linked schedule, even if
        service_schedule_id is set — see the module's "ServiceSchedule and MaintenanceTicket
        stay uncoupled" design decision. record_service is a separate, explicit action."""
        ticket = await self.get_ticket_or_404(ticket_id)
        if ticket.status != "in_progress":
            raise ConflictError(
                f"Cannot complete a ticket in status '{ticket.status}' — only an 'in_progress' ticket can be completed."
            )
        ticket.status = "completed"
        ticket.resolved_at = utcnow()
        if resolution_note is not None:
            ticket.resolution_note = resolution_note
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="maintenance_ticket.completed",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
        )
        return ticket

    async def cancel_ticket(
        self, *, ticket_id: uuid.UUID, note: str | None, actor_user_id: uuid.UUID | None
    ) -> MaintenanceTicket:
        ticket = await self.get_ticket_or_404(ticket_id)
        if ticket.status not in ("open", "in_progress"):
            raise ConflictError(f"Cannot cancel a ticket in status '{ticket.status}'.")
        ticket.status = "cancelled"
        if note is not None:
            ticket.resolution_note = note
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="maintenance_ticket.cancelled",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
        )
        return ticket

    # -- warranty ---------------------------------------------------------------------------
    async def upsert_warranty(
        self,
        *,
        asset_id: uuid.UUID,
        vendor_id: uuid.UUID | None,
        warranty_type: str | None,
        start_date: date,
        end_date: date,
        terms: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Warranty:
        """Get-or-create-then-mutate, same shape as TenantService.upsert_setting — genuinely
        update-in-place, never a second row for the same asset (asset_id is UNIQUE)."""
        if await self.assets.get_by_id(asset_id) is None:
            raise NotFoundError("Asset not found.")
        if vendor_id is not None and await self.vendors.get_by_id(vendor_id) is None:
            raise NotFoundError("Vendor not found.")
        if end_date < start_date:
            raise ValidationAppError("end_date must be on or after start_date.")

        existing = await self.warranties.get_by_asset_id(asset_id)
        old_value = None
        if existing is None:
            warranty = self.warranties.add(
                Warranty(
                    asset_id=asset_id,
                    vendor_id=vendor_id,
                    warranty_type=warranty_type,
                    start_date=start_date,
                    end_date=end_date,
                    terms=terms,
                )
            )
        else:
            old_value = {
                "vendor_id": str(existing.vendor_id) if existing.vendor_id else None,
                "warranty_type": existing.warranty_type,
                "start_date": existing.start_date.isoformat(),
                "end_date": existing.end_date.isoformat(),
                "terms": existing.terms,
            }
            existing.vendor_id = vendor_id
            existing.warranty_type = warranty_type
            existing.start_date = start_date
            existing.end_date = end_date
            existing.terms = terms
            warranty = existing
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="warranty.upserted",
            entity_type="warranty",
            entity_id=warranty.id,
            old_value=old_value,
            new_value={
                "asset_id": str(asset_id),
                "vendor_id": str(vendor_id) if vendor_id else None,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        return warranty

    async def get_warranty_or_404(self, asset_id: uuid.UUID) -> Warranty:
        warranty = await self.warranties.get_by_asset_id(asset_id)
        if warranty is None:
            raise NotFoundError("No warranty is recorded for this asset.")
        return warranty

    # -- service schedules --------------------------------------------------------------------
    async def create_schedule(
        self, *, asset_id: uuid.UUID, name: str, interval_days: int, actor_user_id: uuid.UUID | None
    ) -> ServiceSchedule:
        if await self.assets.get_by_id(asset_id) is None:
            raise NotFoundError("Asset not found.")
        if interval_days <= 0:
            raise ValidationAppError("interval_days must be greater than zero.")

        schedule = self.schedules.add(ServiceSchedule(asset_id=asset_id, name=name, interval_days=interval_days))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="service_schedule.created",
            entity_type="service_schedule",
            entity_id=schedule.id,
            new_value={"asset_id": str(asset_id), "name": name, "interval_days": interval_days},
        )
        return schedule

    async def get_schedule_or_404(self, schedule_id: uuid.UUID) -> ServiceSchedule:
        schedule = await self.schedules.get_by_id(schedule_id)
        if schedule is None:
            raise NotFoundError("Service schedule not found.")
        return schedule

    async def list_schedules(self, *, asset_id: uuid.UUID | None = None) -> list[ServiceSchedule]:
        if asset_id is not None:
            return await self.schedules.list_for_asset(asset_id)
        return await self.schedules.list_all()

    async def update_schedule(
        self, *, schedule_id: uuid.UUID, name: str | None, interval_days: int | None, actor_user_id: uuid.UUID | None
    ) -> ServiceSchedule:
        schedule = await self.get_schedule_or_404(schedule_id)
        if interval_days is not None and interval_days <= 0:
            raise ValidationAppError("interval_days must be greater than zero.")

        old_value = {"name": schedule.name, "interval_days": schedule.interval_days}
        if name is not None:
            schedule.name = name
        if interval_days is not None:
            schedule.interval_days = interval_days
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="service_schedule.updated",
            entity_type="service_schedule",
            entity_id=schedule.id,
            old_value=old_value,
            new_value={"name": schedule.name, "interval_days": schedule.interval_days},
        )
        return schedule

    async def delete_schedule(self, *, schedule_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        schedule = await self.get_schedule_or_404(schedule_id)
        await self.schedules.soft_delete(schedule, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="service_schedule.deleted",
            entity_type="service_schedule",
            entity_id=schedule.id,
            old_value={"name": schedule.name},
        )

    async def record_service(
        self, *, schedule_id: uuid.UUID, serviced_at: date | None, actor_user_id: uuid.UUID | None
    ) -> ServiceSchedule:
        """A separate, explicit action — never triggered by complete_ticket. Recomputes
        next_due_at (at read time, via _schedule_due_info) off the new last_serviced_at."""
        schedule = await self.get_schedule_or_404(schedule_id)
        old_value = {"last_serviced_at": schedule.last_serviced_at.isoformat() if schedule.last_serviced_at else None}
        schedule.last_serviced_at = serviced_at if serviced_at is not None else utcnow().date()
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="service_schedule.service_recorded",
            entity_type="service_schedule",
            entity_id=schedule.id,
            old_value=old_value,
            new_value={"last_serviced_at": schedule.last_serviced_at.isoformat()},
        )
        return schedule

    async def get_schedule_due_report(self) -> dict[str, list[ServiceSchedule]]:
        """Computed on demand, not stored — same convention as
        InventoryService.get_cycle_report/FlowService.get_asset_history. Split into
        overdue/upcoming, each sorted by next_due_at ascending."""
        schedules = await self.schedules.list_all()
        today = utcnow().date()
        overdue: list[tuple[ServiceSchedule, date]] = []
        upcoming: list[tuple[ServiceSchedule, date]] = []
        for schedule in schedules:
            info = _schedule_due_info(schedule, today=today)
            bucket = overdue if info["is_overdue"] else upcoming
            bucket.append((schedule, info["next_due_at"]))
        overdue.sort(key=lambda pair: pair[1])
        upcoming.sort(key=lambda pair: pair[1])
        return {"overdue": [s for s, _ in overdue], "upcoming": [s for s, _ in upcoming]}
