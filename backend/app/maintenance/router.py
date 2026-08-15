import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.response import ok
from app.maintenance.models import ServiceSchedule, Warranty
from app.maintenance.schemas import (
    MaintenanceTicketCreate,
    MaintenanceTicketRead,
    MaintenanceTicketUpdate,
    RecordServiceRequest,
    ScheduleDueReport,
    ServiceScheduleCreate,
    ServiceScheduleRead,
    ServiceScheduleUpdate,
    TicketCancelRequest,
    TicketCompleteRequest,
    WarrantyRead,
    WarrantyUpsert,
)
from app.maintenance.service import MaintenanceService, _schedule_due_info, _warranty_status
from app.users.models import User

_module_gate = Depends(require_module("maintenance"))


def _warranty_read_dict(warranty: Warranty) -> dict:
    """Merges Warranty's own columns with is_expired/days_remaining, computed at read time by
    app.maintenance.service._warranty_status — never stored on the model itself."""
    return {
        "id": warranty.id,
        "asset_id": warranty.asset_id,
        "vendor_id": warranty.vendor_id,
        "warranty_type": warranty.warranty_type,
        "start_date": warranty.start_date,
        "end_date": warranty.end_date,
        "terms": warranty.terms,
        "updated_at": warranty.updated_at,
        **_warranty_status(warranty),
    }


def _schedule_read_dict(schedule: ServiceSchedule) -> dict:
    """Merges ServiceSchedule's own columns with next_due_at/is_overdue, computed at read time
    by app.maintenance.service._schedule_due_info — never stored on the model itself."""
    return {
        "id": schedule.id,
        "asset_id": schedule.asset_id,
        "name": schedule.name,
        "interval_days": schedule.interval_days,
        "last_serviced_at": schedule.last_serviced_at,
        "created_at": schedule.created_at,
        **_schedule_due_info(schedule),
    }


router = APIRouter(prefix="/maintenance", tags=["maintenance"], dependencies=[_module_gate])


# -- tickets ----------------------------------------------------------------------------------
@router.post("/tickets", status_code=201)
async def create_ticket(
    body: MaintenanceTicketCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_tickets")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.create_ticket(
        asset_id=body.asset_id,
        service_schedule_id=body.service_schedule_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assigned_to=body.assigned_to,
        cost=body.cost,
        actor_user_id=actor.id,
    )
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


@router.get("/tickets")
async def list_tickets(
    status: str | None = None,
    asset_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    lifecycle_state_key: str | None = None,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    tickets = await service.list_tickets(
        status=status, asset_id=asset_id, assigned_to=assigned_to, lifecycle_state_key=lifecycle_state_key
    )
    return ok([MaintenanceTicketRead.model_validate(t).model_dump() for t in tickets])


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.get_ticket_or_404(ticket_id)
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: uuid.UUID,
    body: MaintenanceTicketUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_tickets")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.update_ticket(
        ticket_id=ticket_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assigned_to=body.assigned_to,
        cost=body.cost,
        actor_user_id=actor.id,
    )
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


@router.post("/tickets/{ticket_id}/start")
async def start_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_tickets")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.start_ticket(ticket_id=ticket_id, actor_user_id=actor.id)
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


@router.post("/tickets/{ticket_id}/complete")
async def complete_ticket(
    ticket_id: uuid.UUID,
    body: TicketCompleteRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_tickets")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.complete_ticket(ticket_id=ticket_id, resolution_note=body.resolution_note, actor_user_id=actor.id)
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


@router.post("/tickets/{ticket_id}/cancel")
async def cancel_ticket(
    ticket_id: uuid.UUID,
    body: TicketCancelRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_tickets")),
):
    service = MaintenanceService(db, payload.tenant_id)
    ticket = await service.cancel_ticket(ticket_id=ticket_id, note=body.note, actor_user_id=actor.id)
    return ok(MaintenanceTicketRead.model_validate(ticket).model_dump())


# -- service schedules --------------------------------------------------------------------------
@router.get("/schedules")
async def list_schedules(
    asset_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    schedules = await service.list_schedules(asset_id=asset_id)
    return ok([ServiceScheduleRead.model_validate(_schedule_read_dict(s)).model_dump() for s in schedules])


@router.post("/schedules", status_code=201)
async def create_schedule(
    body: ServiceScheduleCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_schedules")),
):
    service = MaintenanceService(db, payload.tenant_id)
    schedule = await service.create_schedule(
        asset_id=body.asset_id, name=body.name, interval_days=body.interval_days, actor_user_id=actor.id
    )
    return ok(ServiceScheduleRead.model_validate(_schedule_read_dict(schedule)).model_dump())


# Registered before "/schedules/{schedule_id}" — a literal path segment must be matched before
# a same-depth path parameter, or "/schedules/report" would be swallowed by the {schedule_id}
# route and fail UUID parsing.
@router.get("/schedules/report")
async def get_schedule_due_report(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    report = await service.get_schedule_due_report()
    return ok(
        ScheduleDueReport(
            overdue=[ServiceScheduleRead.model_validate(_schedule_read_dict(s)) for s in report["overdue"]],
            upcoming=[ServiceScheduleRead.model_validate(_schedule_read_dict(s)) for s in report["upcoming"]],
        ).model_dump()
    )


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    schedule = await service.get_schedule_or_404(schedule_id)
    return ok(ServiceScheduleRead.model_validate(_schedule_read_dict(schedule)).model_dump())


@router.patch("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: uuid.UUID,
    body: ServiceScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_schedules")),
):
    service = MaintenanceService(db, payload.tenant_id)
    schedule = await service.update_schedule(
        schedule_id=schedule_id, name=body.name, interval_days=body.interval_days, actor_user_id=actor.id
    )
    return ok(ServiceScheduleRead.model_validate(_schedule_read_dict(schedule)).model_dump())


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_schedules")),
):
    service = MaintenanceService(db, payload.tenant_id)
    await service.delete_schedule(schedule_id=schedule_id, actor_user_id=actor.id)


@router.post("/schedules/{schedule_id}/record-service")
async def record_service(
    schedule_id: uuid.UUID,
    body: RecordServiceRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_schedules")),
):
    service = MaintenanceService(db, payload.tenant_id)
    schedule = await service.record_service(schedule_id=schedule_id, serviced_at=body.serviced_at, actor_user_id=actor.id)
    return ok(ServiceScheduleRead.model_validate(_schedule_read_dict(schedule)).model_dump())


# -- warranty -------------------------------------------------------------------------------
warranty_router = APIRouter(prefix="/assets", tags=["maintenance-warranty"], dependencies=[_module_gate])


@warranty_router.get("/{asset_id}/warranty")
async def get_warranty(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("maintenance.view")),
):
    service = MaintenanceService(db, payload.tenant_id)
    warranty = await service.get_warranty_or_404(asset_id)
    return ok(WarrantyRead.model_validate(_warranty_read_dict(warranty)).model_dump())


@warranty_router.put("/{asset_id}/warranty")
async def upsert_warranty(
    asset_id: uuid.UUID,
    body: WarrantyUpsert,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("maintenance.manage_warranty")),
):
    service = MaintenanceService(db, payload.tenant_id)
    warranty = await service.upsert_warranty(
        asset_id=asset_id,
        vendor_id=body.vendor_id,
        warranty_type=body.warranty_type,
        start_date=body.start_date,
        end_date=body.end_date,
        terms=body.terms,
        actor_user_id=actor.id,
    )
    return ok(WarrantyRead.model_validate(_warranty_read_dict(warranty)).model_dump())
