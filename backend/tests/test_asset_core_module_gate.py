"""require_module("asset-core") and require_module("flow") exercised on REAL endpoints — the
first genuine exercise of Phase 0's entitlement plumbing beyond test_entitlements.py's
synthetic fake-route test, per the implementation plan's verification checklist. Both modules
default_enabled=True (bundled in the base "Zonovia Core" edition), so the "enabled" half is
just the absence of any TenantModuleEntitlement row; the "disabled" half requires inserting
one with enabled=False."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def test_asset_core_module_disabled_returns_403_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-asset-core-disabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="AssetCoreGateRole", permission_keys=["assets.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@asset-core-disabled.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="asset-core", enabled=False, source="manual"))
    await db.commit()

    resp = await client.get("/api/v1/assets", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_asset_core_module_enabled_by_default_returns_200_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-asset-core-enabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="AssetCoreGateRoleOk", permission_keys=["assets.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@asset-core-enabled.example", role=role)
    await db.commit()  # no TenantModuleEntitlement row — falls back to default_enabled=True

    resp = await client.get("/api/v1/assets", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_flow_module_disabled_returns_403_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-flow-disabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="FlowGateRole", permission_keys=["asset_lifecycle.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@flow-disabled.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="flow", enabled=False, source="manual"))
    await db.commit()

    resp = await client.get("/api/v1/asset-lifecycle/states", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_flow_module_enabled_by_default_returns_200_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-flow-enabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="FlowGateRoleOk", permission_keys=["asset_lifecycle.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@flow-enabled.example", role=role)
    await db.commit()  # no TenantModuleEntitlement row — falls back to default_enabled=True

    resp = await client.get("/api/v1/asset-lifecycle/states", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_asset_core_module_appears_in_admin_modules_listing(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-listing")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsViewerAssetCore", permission_keys=["entitlements.view"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="listing@module-gate-test.example", role=role)
    await db.commit()

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["asset-core"]["always_on"] is False
    assert modules_by_key["asset-core"]["enabled"] is True
    assert modules_by_key["flow"]["always_on"] is False
    assert modules_by_key["flow"]["enabled"] is True
