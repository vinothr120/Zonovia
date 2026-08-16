"""app.tracking's DeviceGateway/Device admin surface (/tracking/gateways) — ordinary user-JWT +
require_permission("tracking.manage_gateways"/"tracking.manage_devices"), entirely separate from
the gateway-auth-only /rfid/ingest chain (see test_rfid_gateway_auth.py for that). Covers: the
raw API key is returned exactly once, at creation, and never again on any later read; revoke is
terminal; device registration/listing under a gateway; permission gating."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_GATEWAY_PERMS = ["tracking.manage_gateways", "tracking.manage_devices"]


async def _make_gateway_admin(db, tenant, *, email="gwadmin@tracking-gateway-test.example"):
    role = await make_role_with_permissions(db, tenant_id=None, name="GatewayAdmin", permission_keys=_ALL_GATEWAY_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def test_create_gateway_returns_raw_api_key_exactly_once(client, db):
    tenant = await make_tenant(db, subdomain="tracking-gateway-onetime-key")
    _user, token = await _make_gateway_admin(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post("/api/v1/tracking/gateways", json={"name": "Reader Fleet A"}, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    data = create_resp.json()["data"]
    assert set(data.keys()) == {"gateway", "api_key"}
    raw_key = data["api_key"]
    assert len(raw_key) > 20
    assert data["gateway"]["api_key_last4"] == raw_key[-4:]
    assert "api_key" not in data["gateway"]
    assert "api_key_hash" not in data["gateway"]
    gateway_id = data["gateway"]["id"]

    # Every later read — GET by id, GET list — carries api_key_last4 only, never the raw key
    # or its hash. This is the whole point of "returned exactly once."
    get_resp = await client.get(f"/api/v1/tracking/gateways/{gateway_id}", headers=headers)
    assert get_resp.status_code == 200
    got = get_resp.json()["data"]
    assert got["api_key_last4"] == raw_key[-4:]
    assert "api_key" not in got
    assert "api_key_hash" not in got
    assert raw_key not in str(got)

    list_resp = await client.get("/api/v1/tracking/gateways", headers=headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]
    assert any(g["id"] == gateway_id for g in listed)
    assert raw_key not in str(listed)


async def test_revoke_gateway_is_terminal(client, db):
    tenant = await make_tenant(db, subdomain="tracking-gateway-revoke-terminal")
    _user, token = await _make_gateway_admin(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    gateway = (await client.post("/api/v1/tracking/gateways", json={"name": "Revoke Me"}, headers=headers)).json()["data"][
        "gateway"
    ]

    revoke_resp = await client.post(f"/api/v1/tracking/gateways/{gateway['id']}/revoke", headers=headers)
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["data"]["status"] == "revoked"

    # Terminal — revoking an already-revoked gateway is rejected, not silently a no-op.
    second_revoke = await client.post(f"/api/v1/tracking/gateways/{gateway['id']}/revoke", headers=headers)
    assert second_revoke.status_code == 409


async def test_register_and_list_devices_under_a_gateway(client, db):
    tenant = await make_tenant(db, subdomain="tracking-gateway-devices")
    _user, token = await _make_gateway_admin(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    gateway = (await client.post("/api/v1/tracking/gateways", json={"name": "Devices Gateway"}, headers=headers)).json()["data"][
        "gateway"
    ]

    device_resp = await client.post(
        f"/api/v1/tracking/gateways/{gateway['id']}/devices",
        json={"device_type": "RFID_READER", "vendor": "Zebra", "model": "FX9600"},
        headers=headers,
    )
    assert device_resp.status_code == 201, device_resp.text
    device = device_resp.json()["data"]
    assert device["gateway_id"] == gateway["id"]
    assert device["device_type"] == "RFID_READER"
    assert device["status"] == "active"

    list_resp = await client.get(f"/api/v1/tracking/gateways/{gateway['id']}/devices", headers=headers)
    assert list_resp.status_code == 200
    devices = list_resp.json()["data"]
    assert len(devices) == 1
    assert devices[0]["id"] == device["id"]


async def test_gateway_device_type_has_no_allow_list(client, db):
    """Device.device_type is deliberately free text — no allow-list, unlike
    AssetIdentifier.identifier_type. A future track-sense BLE beacon type must work today
    without a code change."""
    tenant = await make_tenant(db, subdomain="tracking-gateway-device-type-free-text")
    _user, token = await _make_gateway_admin(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    gateway = (await client.post("/api/v1/tracking/gateways", json={"name": "Freeform Gateway"}, headers=headers)).json()["data"][
        "gateway"
    ]

    device_resp = await client.post(
        f"/api/v1/tracking/gateways/{gateway['id']}/devices", json={"device_type": "BLE_BEACON"}, headers=headers
    )
    assert device_resp.status_code == 201, device_resp.text
    assert device_resp.json()["data"]["device_type"] == "BLE_BEACON"


async def test_gateway_endpoints_require_manage_gateways_permission(client, db):
    tenant = await make_tenant(db, subdomain="tracking-gateway-perm-denied")
    _admin, admin_token = await _make_gateway_admin(db, tenant)
    await db.commit()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    gateway = (await client.post("/api/v1/tracking/gateways", json={"name": "Perm Test Gateway"}, headers=admin_headers)).json()[
        "data"
    ]["gateway"]

    no_perm_role = await make_role_with_permissions(db, tenant_id=None, name="NoGatewayPerms", permission_keys=[])
    _user, token = await make_user_with_role(
        db, tenant_id=tenant.id, email="noperm@tracking-gateway-test.example", role=no_perm_role
    )
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    assert (await client.post("/api/v1/tracking/gateways", json={"name": "Denied"}, headers=headers)).status_code == 403
    assert (await client.get("/api/v1/tracking/gateways", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/tracking/gateways/{gateway['id']}", headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/tracking/gateways/{gateway['id']}/revoke", headers=headers)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/tracking/gateways/{gateway['id']}/devices", json={"device_type": "RFID_READER"}, headers=headers
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/tracking/gateways/{gateway['id']}/devices", headers=headers)).status_code == 403


async def test_manage_gateways_permission_alone_does_not_grant_manage_devices(client, db):
    """The two permissions are independent — Tenant-Admin-only in practice per the seed
    bundle, but the router itself must enforce them separately (device endpoints check
    tracking.manage_devices, not tracking.manage_gateways)."""
    tenant = await make_tenant(db, subdomain="tracking-gateway-perm-split")
    _admin, admin_token = await _make_gateway_admin(db, tenant)
    await db.commit()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    gateway = (await client.post("/api/v1/tracking/gateways", json={"name": "Split Perm Gateway"}, headers=admin_headers)).json()[
        "data"
    ]["gateway"]

    role = await make_role_with_permissions(db, tenant_id=None, name="GatewaysOnly", permission_keys=["tracking.manage_gateways"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gwonly@tracking-gateway-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    assert (await client.get(f"/api/v1/tracking/gateways/{gateway['id']}", headers=headers)).status_code == 200
    assert (
        await client.post(
            f"/api/v1/tracking/gateways/{gateway['id']}/devices", json={"device_type": "RFID_READER"}, headers=headers
        )
    ).status_code == 403
