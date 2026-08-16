"""require_module("track-rfid") on the user-JWT side (mirrors test_maintenance_module_gate.py's
shape) AND require_module_for_gateway("track-rfid") on the gateway-auth side — both are
default-off (default_enabled=False) entitlement checks that must independently prove the same
thing: no TenantModuleEntitlement row at all falls back to default_enabled=False and blocks
every relevant endpoint, even when the caller's credentials (user permissions, or a genuinely
valid+active gateway key) are otherwise perfectly good."""

import uuid

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import gateway_headers, make_device_gateway, make_role_with_permissions, make_tenant, make_user_with_role

_ALL_RFID_PERMS = ["track_rfid.manage_tags", "track_rfid.view"]


async def test_track_rfid_module_disabled_by_default_returns_403_on_user_jwt_endpoints(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-track-rfid-user-off")
    role = await make_role_with_permissions(db, tenant_id=None, name="RfidGateRoleFull", permission_keys=_ALL_RFID_PERMS)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@track-rfid-user-off.example", role=role)
    await db.commit()  # deliberately no TenantModuleEntitlement row
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = str(uuid.uuid4())

    assert (
        await client.post("/api/v1/rfid/tags", json={"asset_id": fake_id, "epc": "E200001A"}, headers=headers)
    ).status_code == 403
    assert (await client.get(f"/api/v1/rfid/tags/{fake_id}", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/rfid/tags", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/rfid/read-events", headers=headers)).status_code == 403


async def test_track_rfid_module_disabled_by_default_returns_403_on_gateway_ingest(client, db):
    """The gateway-auth-side proof: a genuinely valid, active gateway (correct tenant slug +
    correct key) still gets 403 from /rfid/ingest when track-rfid has no entitlement row —
    proving require_module_for_gateway's own live entitlement lookup works, not just that
    get_gateway_payload's auth check works."""
    tenant = await make_tenant(db, subdomain="module-gate-track-rfid-gw-off")
    gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id, name="Gate Test Gateway")
    await db.commit()  # deliberately no TenantModuleEntitlement row

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={"reads": []},
        headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key),
    )
    assert resp.status_code == 403


async def test_track_rfid_module_explicitly_enabled_returns_200_on_user_jwt_and_gateway_endpoints(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-track-rfid-explicit-on")
    role = await make_role_with_permissions(db, tenant_id=None, name="RfidGateRoleOk", permission_keys=["track_rfid.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gate@track-rfid-on.example", role=role)
    gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id, name="Gate Test Gateway On")
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="track-rfid", enabled=True, source="manual"))
    await db.commit()

    user_resp = await client.get("/api/v1/rfid/tags", headers={"Authorization": f"Bearer {token}"})
    assert user_resp.status_code == 200

    gw_resp = await client.post(
        "/api/v1/rfid/ingest",
        json={"reads": []},
        headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key),
    )
    assert gw_resp.status_code == 201, gw_resp.text


async def test_track_rfid_module_appears_in_admin_modules_listing_as_disabled_by_default(client, db):
    tenant = await make_tenant(db, subdomain="module-gate-track-rfid-listing")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsViewerTrackRfid", permission_keys=["entitlements.view"]
    )
    _user, token = await make_user_with_role(
        db, tenant_id=tenant.id, email="listing@module-gate-track-rfid-test.example", role=role
    )
    await db.commit()  # no TenantModuleEntitlement row for track-rfid

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["track-rfid"]["always_on"] is False
    assert modules_by_key["track-rfid"]["enabled"] is False
    assert modules_by_key["track-rfid"]["source"] == "default"
