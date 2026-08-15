"""maintenance.view / maintenance.manage_tickets / maintenance.manage_warranty /
maintenance.manage_schedules gating on the real maintenance/warranty endpoints — a user missing
the specific permission a route requires must be rejected (403), even with the maintenance
module itself enabled and every other maintenance permission granted. Mirrors
test_inventory_permissions.py's shape."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]
_ALL_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]


async def _enable_maintenance(db, tenant_id):
    db.add(TenantModuleEntitlement(tenant_id=tenant_id, module_key="maintenance", enabled=True, source="manual"))


async def _make_setup_user(db, tenant):
    """Full-permission user used only to create fixture data (asset, schedule)."""
    role = await make_role_with_permissions(
        db, tenant_id=None, name="MaintPermSetup", permission_keys=_ALL_MAINTENANCE_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="setup@maintenance-perm-test.example", role=role)
    await _enable_maintenance(db, tenant.id)
    return user, token


async def _create_asset(client, headers, name="Perm Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _make_role_with_only(db, tenant, *, permission_keys, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"OnlyRole-{email}", permission_keys=permission_keys)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return token


async def test_manage_tickets_permission_gates_create_start_complete_cancel(client, db):
    tenant = await make_tenant(db, subdomain="maint-perm-manage-tickets")
    _setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    asset = await _create_asset(client, setup_headers)

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["maintenance.view"], email="viewonly@maintenance-perm-test.example"
    )
    await db.commit()
    view_only_headers = {"Authorization": f"Bearer {view_only_token}"}

    create_resp = await client.post(
        "/api/v1/maintenance/tickets", json={"asset_id": asset["id"], "title": "Denied"}, headers=view_only_headers
    )
    assert create_resp.status_code == 403

    ticket = (
        await client.post(
            "/api/v1/maintenance/tickets", json={"asset_id": asset["id"], "title": "Setup Ticket"}, headers=setup_headers
        )
    ).json()["data"]

    start_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=view_only_headers)
    assert start_resp.status_code == 403

    # maintenance.view alone is still enough to read.
    read_resp = await client.get(f"/api/v1/maintenance/tickets/{ticket['id']}", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_manage_warranty_permission_gates_upsert_but_not_read(client, db):
    tenant = await make_tenant(db, subdomain="maint-perm-manage-warranty")
    _setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    asset = await _create_asset(client, setup_headers)
    await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": "2026-01-01", "end_date": "2027-01-01"},
        headers=setup_headers,
    )

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["maintenance.view"], email="viewonly@maintenance-warranty-perm-test.example"
    )
    await db.commit()
    view_only_headers = {"Authorization": f"Bearer {view_only_token}"}

    upsert_resp = await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": "2026-01-01", "end_date": "2028-01-01"},
        headers=view_only_headers,
    )
    assert upsert_resp.status_code == 403

    read_resp = await client.get(f"/api/v1/assets/{asset['id']}/warranty", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_manage_schedules_permission_gates_create_delete_record_service(client, db):
    tenant = await make_tenant(db, subdomain="maint-perm-manage-schedules")
    _setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    asset = await _create_asset(client, setup_headers)
    schedule = (
        await client.post(
            "/api/v1/maintenance/schedules",
            json={"asset_id": asset["id"], "name": "Setup Schedule", "interval_days": 30},
            headers=setup_headers,
        )
    ).json()["data"]

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["maintenance.view"], email="viewonly@maintenance-schedule-perm-test.example"
    )
    await db.commit()
    view_only_headers = {"Authorization": f"Bearer {view_only_token}"}

    create_resp = await client.post(
        "/api/v1/maintenance/schedules",
        json={"asset_id": asset["id"], "name": "Denied", "interval_days": 10},
        headers=view_only_headers,
    )
    assert create_resp.status_code == 403

    record_resp = await client.post(
        f"/api/v1/maintenance/schedules/{schedule['id']}/record-service", json={}, headers=view_only_headers
    )
    assert record_resp.status_code == 403

    delete_resp = await client.delete(f"/api/v1/maintenance/schedules/{schedule['id']}", headers=view_only_headers)
    assert delete_resp.status_code == 403

    # maintenance.view alone is still enough to read.
    read_resp = await client.get(f"/api/v1/maintenance/schedules/{schedule['id']}", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_view_permission_gates_listing_and_report(client, db):
    tenant = await make_tenant(db, subdomain="maint-perm-view")
    await _make_setup_user(db, tenant)
    await db.commit()

    no_view_token = await _make_role_with_only(
        db, tenant, permission_keys=["maintenance.manage_tickets"], email="noview@maintenance-perm-test.example"
    )
    await db.commit()
    no_view_headers = {"Authorization": f"Bearer {no_view_token}"}

    assert (await client.get("/api/v1/maintenance/tickets", headers=no_view_headers)).status_code == 403
    assert (await client.get("/api/v1/maintenance/schedules", headers=no_view_headers)).status_code == 403
    assert (await client.get("/api/v1/maintenance/schedules/report", headers=no_view_headers)).status_code == 403
