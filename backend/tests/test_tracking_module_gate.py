"""require_module("tracking-engine") exercised on the real /tracking/scan endpoint, mirroring
test_asset_core_module_gate.py's disabled-403 / enabled-200(-range) / admin-listing pattern."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_SCAN_SETUP_PERMS = ["tracking.scan", "assets.view", "assets.create", "assets.edit", "asset_catalog.manage"]


async def test_tracking_module_disabled_returns_403_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-tracking-disabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="TrackingGateRole", permission_keys=["tracking.scan"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@tracking-disabled.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="tracking-engine", enabled=False, source="manual"))
    await db.commit()

    resp = await client.post(
        "/api/v1/tracking/scan",
        json={"identifier_type": "QR", "value": "whatever"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_tracking_module_enabled_by_default_returns_201_on_a_real_endpoint(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-tracking-enabled")
    role = await make_role_with_permissions(db, tenant_id=None, name="TrackingGateRoleOk", permission_keys=_SCAN_SETUP_PERMS)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@tracking-enabled.example", role=role)
    await db.commit()  # no TenantModuleEntitlement row — falls back to default_enabled=True
    headers = {"Authorization": f"Bearer {token}"}

    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post("/api/v1/assets", json={"name": "Gate Test Asset", "asset_type_id": asset_type["id"]}, headers=headers)
    ).json()["data"]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "QR", "value": "GATE-TEST-QR"}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text

    resp = await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "GATE-TEST-QR"}, headers=headers)
    assert resp.status_code == 201, resp.text


async def test_tracking_module_appears_in_admin_modules_listing(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-tracking-listing")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsViewerTracking", permission_keys=["entitlements.view"]
    )
    _user, token = await make_user_with_role(
        db, tenant_id=tenant.id, email="listing@module-gate-tracking-test.example", role=role
    )
    await db.commit()

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["tracking-engine"]["always_on"] is False
    assert modules_by_key["tracking-engine"]["enabled"] is True
