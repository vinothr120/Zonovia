"""MaintenanceTicket status guard-clauses: the open -> in_progress -> completed|cancelled
state machine, illegal transitions rejected with 409 (mirrors InventoryCycle's
start_cycle/complete_cycle/cancel_cycle pattern), terminal tickets (completed/cancelled)
immutable via PATCH, and the priority allow-list enforced (422) on both create and update."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


async def _make_user(db, tenant, *, email="user@maintenance-tickets-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"MaintTicketUser-{email}", permission_keys=_MAINTENANCE_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name="Ticket Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _create_ticket(client, headers, asset_id, **overrides):
    body = {"asset_id": asset_id, "title": "Broken screen"} | overrides
    resp = await client.post("/api/v1/maintenance/tickets", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_create_ticket_defaults_status_open_and_reported_by_actor(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-create")
    user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])

    assert ticket["status"] == "open"
    assert ticket["asset_id"] == asset["id"]
    assert ticket["reported_by"] == str(user.id)
    assert ticket["resolved_at"] is None


async def test_priority_allow_list_rejected_on_create(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-priority-create")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(
        "/api/v1/maintenance/tickets",
        json={"asset_id": asset["id"], "title": "Bad priority", "priority": "not_a_real_priority"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_create_ticket_against_missing_asset_returns_404(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-missing-asset")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.post("/api/v1/maintenance/tickets", json={"asset_id": fake_id, "title": "Ghost asset"}, headers=headers)
    assert resp.status_code == 404


async def test_start_ticket_from_open_succeeds_then_double_start_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-double-start")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])

    first = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "in_progress"

    second = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    assert second.status_code == 409


async def test_complete_requires_in_progress_status(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-complete-guard")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])

    # Still "open" — completing directly must be rejected.
    resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={}, headers=headers)
    assert resp.status_code == 409


async def test_complete_sets_resolved_at_and_resolution_note(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-complete-happy")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])
    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)

    resp = await client.post(
        f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={"resolution_note": "Replaced the part."}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["resolved_at"] is not None
    assert data["resolution_note"] == "Replaced the part."


async def test_cancel_allowed_from_open_and_from_in_progress(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-cancel-allowed")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    open_ticket = await _create_ticket(client, headers, asset["id"], title="Cancel from open")
    cancel_open = await client.post(f"/api/v1/maintenance/tickets/{open_ticket['id']}/cancel", json={}, headers=headers)
    assert cancel_open.status_code == 200, cancel_open.text
    assert cancel_open.json()["data"]["status"] == "cancelled"

    in_progress_ticket = await _create_ticket(client, headers, asset["id"], title="Cancel from in_progress")
    await client.post(f"/api/v1/maintenance/tickets/{in_progress_ticket['id']}/start", headers=headers)
    cancel_in_progress = await client.post(
        f"/api/v1/maintenance/tickets/{in_progress_ticket['id']}/cancel", json={}, headers=headers
    )
    assert cancel_in_progress.status_code == 200, cancel_in_progress.text
    assert cancel_in_progress.json()["data"]["status"] == "cancelled"


async def test_cancel_rejected_from_a_terminal_status(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-cancel-terminal")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])
    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={}, headers=headers)

    resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/cancel", json={}, headers=headers)
    assert resp.status_code == 409


async def test_terminal_ticket_is_immutable_via_patch(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-immutable")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])
    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/cancel", json={}, headers=headers)

    resp = await client.patch(f"/api/v1/maintenance/tickets/{ticket['id']}", json={"title": "New title"}, headers=headers)
    assert resp.status_code == 409


async def test_priority_allow_list_rejected_on_update(client, db):
    tenant = await make_tenant(db, subdomain="maint-ticket-priority-update")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])

    resp = await client.patch(f"/api/v1/maintenance/tickets/{ticket['id']}", json={"priority": "urgentish"}, headers=headers)
    assert resp.status_code == 422
