"""service_schedule_id on a MaintenanceTicket is optional traceability only, per the module's
"ServiceSchedule and MaintenanceTicket stay uncoupled" design decision: a schedule linked to a
ticket must belong to the SAME asset (cross-asset link rejected), and completing a linked
ticket must NOT touch the schedule's last_serviced_at — record_service is a separate, explicit
action, never auto-triggered by complete_ticket."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


async def _make_user(db, tenant, *, email="user@maintenance-ticket-link-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"MaintLinkUser-{email}", permission_keys=_MAINTENANCE_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _create_schedule(client, headers, asset_id, *, name="Quarterly Check", interval_days=90):
    resp = await client.post(
        "/api/v1/maintenance/schedules",
        json={"asset_id": asset_id, "name": name, "interval_days": interval_days},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_ticket_linked_to_a_schedule_on_a_different_asset_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="maint-link-cross-asset")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset_a = await _create_asset(client, headers, "Asset A")
    asset_b = await _create_asset(client, headers, "Asset B")
    schedule_on_b = await _create_schedule(client, headers, asset_b["id"])

    resp = await client.post(
        "/api/v1/maintenance/tickets",
        json={"asset_id": asset_a["id"], "title": "Cross-asset link attempt", "service_schedule_id": schedule_on_b["id"]},
        headers=headers,
    )
    assert resp.status_code in (404, 422)


async def test_ticket_linked_to_a_missing_schedule_returns_404(client, db):
    tenant = await make_tenant(db, subdomain="maint-link-missing-schedule")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    fake_schedule_id = "00000000-0000-0000-0000-000000000000"

    asset = await _create_asset(client, headers, "Solo Asset")
    resp = await client.post(
        "/api/v1/maintenance/tickets",
        json={"asset_id": asset["id"], "title": "Missing schedule link", "service_schedule_id": fake_schedule_id},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_ticket_linked_to_a_schedule_on_the_same_asset_is_allowed(client, db):
    tenant = await make_tenant(db, subdomain="maint-link-same-asset")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Linked Asset")
    schedule = await _create_schedule(client, headers, asset["id"])

    resp = await client.post(
        "/api/v1/maintenance/tickets",
        json={"asset_id": asset["id"], "title": "Legit link", "service_schedule_id": schedule["id"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["service_schedule_id"] == schedule["id"]


async def test_completing_a_linked_ticket_does_not_change_the_schedules_last_serviced_at(client, db):
    """The concrete non-coupling test: a ticket linked to a schedule, fully run through
    start -> complete, must leave the schedule's last_serviced_at exactly as it was before
    (None, in this case, since the schedule has never been serviced) — completing a ticket is
    not the same event as recording a scheduled service."""
    tenant = await make_tenant(db, subdomain="maint-link-no-coupling")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Uncoupled Asset")
    schedule = await _create_schedule(client, headers, asset["id"])
    assert schedule["last_serviced_at"] is None

    ticket_resp = await client.post(
        "/api/v1/maintenance/tickets",
        json={"asset_id": asset["id"], "title": "Ad-hoc repair", "service_schedule_id": schedule["id"]},
        headers=headers,
    )
    assert ticket_resp.status_code == 201, ticket_resp.text
    ticket = ticket_resp.json()["data"]

    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    complete_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={}, headers=headers)
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["data"]["status"] == "completed"

    after = await client.get(f"/api/v1/maintenance/schedules/{schedule['id']}", headers=headers)
    assert after.status_code == 200, after.text
    assert after.json()["data"]["last_serviced_at"] is None
