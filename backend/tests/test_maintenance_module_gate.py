"""require_module("maintenance") exercised on real endpoints. Mirrors
test_inventory_module_gate.py's shape: maintenance is default_enabled=False, same as
inventory, so the important case is — with NO TenantModuleEntitlement row at all, every
maintenance/warranty endpoint must 403, proving the default_enabled=False fallback itself
works, not just that require_module() as a mechanism works."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]


async def test_maintenance_module_disabled_by_default_returns_403_on_every_endpoint(client, db):
    """No TenantModuleEntitlement row at all — falls back to ModuleDefinition.default_enabled,
    which for maintenance is False. The user has every maintenance permission, so a 403 here
    can only be coming from the module gate, not a permission check."""
    tenant = await make_tenant(db, subdomain="module-gate-maintenance-default-off")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="MaintenanceGateRoleFull", permission_keys=_ALL_MAINTENANCE_PERMS
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@maintenance-default-off.example", role=role)
    await db.commit()  # deliberately no TenantModuleEntitlement row
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = "00000000-0000-0000-0000-000000000000"

    assert (await client.get("/api/v1/maintenance/tickets", headers=headers)).status_code == 403
    assert (
        await client.post("/api/v1/maintenance/tickets", json={"asset_id": fake_id, "title": "Nope"}, headers=headers)
    ).status_code == 403
    assert (await client.get(f"/api/v1/maintenance/tickets/{fake_id}", headers=headers)).status_code == 403
    assert (
        await client.patch(f"/api/v1/maintenance/tickets/{fake_id}", json={"title": "Nope"}, headers=headers)
    ).status_code == 403
    assert (await client.post(f"/api/v1/maintenance/tickets/{fake_id}/start", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/maintenance/tickets/{fake_id}/complete", json={}, headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/maintenance/tickets/{fake_id}/cancel", json={}, headers=headers)).status_code == 403

    assert (await client.get("/api/v1/maintenance/schedules", headers=headers)).status_code == 403
    assert (
        await client.post(
            "/api/v1/maintenance/schedules", json={"asset_id": fake_id, "name": "Nope", "interval_days": 30}, headers=headers
        )
    ).status_code == 403
    assert (await client.get("/api/v1/maintenance/schedules/report", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/maintenance/schedules/{fake_id}", headers=headers)).status_code == 403
    assert (
        await client.patch(f"/api/v1/maintenance/schedules/{fake_id}", json={"name": "Nope"}, headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/maintenance/schedules/{fake_id}", headers=headers)).status_code == 403
    assert (
        await client.post(f"/api/v1/maintenance/schedules/{fake_id}/record-service", json={}, headers=headers)
    ).status_code == 403

    assert (await client.get(f"/api/v1/assets/{fake_id}/warranty", headers=headers)).status_code == 403
    assert (
        await client.put(
            f"/api/v1/assets/{fake_id}/warranty",
            json={"start_date": "2026-01-01", "end_date": "2027-01-01"},
            headers=headers,
        )
    ).status_code == 403


async def test_maintenance_module_explicitly_enabled_returns_200_on_a_real_endpoint(client, db):
    """The flip side: an explicit source='manual' enabled=True row makes the same tenant
    reachable, proving the gate is a genuine live lookup, not a permanently-off switch."""
    tenant = await make_tenant(db, subdomain="module-gate-maintenance-explicit-on")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="MaintenanceGateRoleOk", permission_keys=["maintenance.view"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@maintenance-explicit-on.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/maintenance/tickets", headers=headers)
    assert resp.status_code == 200


async def test_maintenance_module_appears_in_admin_modules_listing_as_disabled_by_default(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-maintenance-listing")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsViewerMaintenance", permission_keys=["entitlements.view"]
    )
    _user, token = await make_user_with_role(
        db, tenant_id=tenant.id, email="listing@module-gate-maintenance-test.example", role=role
    )
    await db.commit()  # no TenantModuleEntitlement row for maintenance

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["maintenance"]["always_on"] is False
    assert modules_by_key["maintenance"]["enabled"] is False
    assert modules_by_key["maintenance"]["source"] == "default"
