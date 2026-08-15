"""tracking.scan vs tracking.view permission gating on the real endpoints — a user with only
one of the two must be rejected from the other."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_SETUP_PERMS = ["assets.view", "assets.create", "assets.edit", "asset_catalog.manage", "tracking.scan", "tracking.view"]


async def _setup_asset_with_identifier(client, db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="TrackingPermSetup", permission_keys=_SETUP_PERMS)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="setup@tracking-perm-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post("/api/v1/assets", json={"name": "Perm Test Asset", "asset_type_id": asset_type["id"]}, headers=headers)
    ).json()["data"]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "QR", "value": "PERM-TEST-QR"}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text
    return asset


async def test_scan_without_tracking_scan_permission_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="tracking-perm-scan-denied")
    asset = await _setup_asset_with_identifier(client, db, tenant)

    role = await make_role_with_permissions(db, tenant_id=None, name="ViewOnly", permission_keys=["tracking.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noscan@tracking-perm-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    scan_resp = await client.post(
        "/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "PERM-TEST-QR"}, headers=headers
    )
    assert scan_resp.status_code == 403

    # tracking.view alone is still enough to read history.
    events_resp = await client.get(f"/api/v1/assets/{asset['id']}/tracking-events", headers=headers)
    assert events_resp.status_code == 200


async def test_view_history_without_tracking_view_permission_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="tracking-perm-view-denied")
    asset = await _setup_asset_with_identifier(client, db, tenant)

    role = await make_role_with_permissions(db, tenant_id=None, name="ScanOnly", permission_keys=["tracking.scan"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noview@tracking-perm-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    # tracking.scan alone is still enough to record a scan.
    scan_resp = await client.post(
        "/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "PERM-TEST-QR"}, headers=headers
    )
    assert scan_resp.status_code == 201, scan_resp.text

    events_resp = await client.get(f"/api/v1/assets/{asset['id']}/tracking-events", headers=headers)
    assert events_resp.status_code == 403
