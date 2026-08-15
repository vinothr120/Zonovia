"""require_module("inventory") exercised on real endpoints. Unlike every prior module-gate
test (asset-core/flow/tracking-engine, all default_enabled=True), inventory is the FIRST
module in the project with default_enabled=False — so the important new case here is: with NO
TenantModuleEntitlement row at all, every inventory endpoint must 403, proving the
default_enabled=False fallback itself works, not just that require_module() as a mechanism
works (that was already proven by the disabled-via-explicit-row case in the other module-gate
test files)."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]


async def test_inventory_module_disabled_by_default_returns_403_on_every_endpoint(client, db):
    """No TenantModuleEntitlement row at all — falls back to ModuleDefinition.default_enabled,
    which for inventory is False. The user has every inventory permission, so a 403 here can
    only be coming from the module gate, not a permission check."""
    tenant = await make_tenant(db, subdomain="module-gate-inventory-default-off")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryGateRoleFull", permission_keys=_ALL_INVENTORY_PERMS
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@inventory-default-off.example", role=role)
    await db.commit()  # deliberately no TenantModuleEntitlement row
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = "00000000-0000-0000-0000-000000000000"

    assert (await client.get("/api/v1/inventory/cycles", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/inventory/cycles", json={"name": "Nope"}, headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/inventory/cycles/{fake_id}", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/inventory/cycles/{fake_id}/start", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/inventory/cycles/{fake_id}/complete", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/inventory/cycles/{fake_id}/cancel", headers=headers)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/inventory/cycles/{fake_id}/counts", json={"identifier_type": "QR", "value": "X"}, headers=headers
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/inventory/cycles/{fake_id}/counts", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/inventory/cycles/{fake_id}/report", headers=headers)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/inventory/cycles/{fake_id}/reconciliations",
            json={"asset_id": fake_id, "action_type": "acknowledged"},
            headers=headers,
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/inventory/cycles/{fake_id}/reconciliations", headers=headers)).status_code == 403


async def test_inventory_module_explicitly_enabled_returns_200_on_a_real_endpoint(client, db):
    """The flip side: an explicit source='manual' enabled=True row makes the same tenant
    reachable, proving the gate is a genuine live lookup, not a permanently-off switch."""
    tenant = await make_tenant(db, subdomain="module-gate-inventory-explicit-on")
    role = await make_role_with_permissions(db, tenant_id=None, name="InventoryGateRoleOk", permission_keys=["inventory.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@inventory-explicit-on.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="inventory", enabled=True, source="manual"))
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/inventory/cycles", headers=headers)
    assert resp.status_code == 200


async def test_inventory_module_appears_in_admin_modules_listing_as_disabled_by_default(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-inventory-listing")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsViewerInventory", permission_keys=["entitlements.view"]
    )
    _user, token = await make_user_with_role(
        db, tenant_id=tenant.id, email="listing@module-gate-inventory-test.example", role=role
    )
    await db.commit()  # no TenantModuleEntitlement row for inventory

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["inventory"]["always_on"] is False
    assert modules_by_key["inventory"]["enabled"] is False
    assert modules_by_key["inventory"]["source"] == "default"
