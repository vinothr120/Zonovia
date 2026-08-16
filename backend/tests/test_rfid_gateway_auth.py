"""app.tracking.deps's gateway-auth chain (GatewayPayload/get_gateway_payload/get_gateway_db/
require_module_for_gateway) exercised end to end via POST /rfid/ingest — the fully separate,
parallel dependency chain from user-JWT auth. Valid creds succeed and update last_seen_at;
bad/revoked creds are rejected 401; and BOTH directions of the auth-boundary claim are proven:
a user JWT cannot reach the gateway-only endpoint, and a gateway key cannot reach a
user-permission-gated endpoint."""

from sqlalchemy import select

from app.entitlements.models import TenantModuleEntitlement
from app.tracking.models import DeviceGateway
from tests.conftest import (
    gateway_headers,
    make_device_gateway,
    make_role_with_permissions,
    make_tenant,
    make_user_with_role,
)


async def _enabled_tenant(db, subdomain: str):
    tenant = await make_tenant(db, subdomain=subdomain)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="track-rfid", enabled=True, source="manual"))
    return tenant


async def test_valid_gateway_credentials_succeed_and_update_last_seen_at(client, db):
    tenant = await _enabled_tenant(db, "rfid-gw-auth-valid")
    gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()
    assert gateway.last_seen_at is None

    resp = await client.post(
        "/api/v1/rfid/ingest", json={"reads": []}, headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key)
    )
    assert resp.status_code == 201, resp.text

    refreshed = (await db.execute(select(DeviceGateway).where(DeviceGateway.id == gateway.id))).scalar_one()
    assert refreshed.last_seen_at is not None


async def test_wrong_api_key_is_rejected(client, db):
    tenant = await _enabled_tenant(db, "rfid-gw-auth-wrong-key")
    await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={"reads": []},
        headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key="totally-wrong-key"),
    )
    assert resp.status_code == 401


async def test_wrong_tenant_slug_is_rejected(client, db):
    tenant = await _enabled_tenant(db, "rfid-gw-auth-wrong-tenant")
    _gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={"reads": []},
        headers=gateway_headers(tenant_slug="no-such-tenant-slug", raw_api_key=raw_key),
    )
    assert resp.status_code == 401


async def test_revoked_gateway_key_stops_working_immediately(client, db):
    tenant = await _enabled_tenant(db, "rfid-gw-auth-revoked")
    gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()

    # Confirm the key genuinely works before revocation, isolating the assertion below to the
    # revoke transition itself.
    pre_resp = await client.post(
        "/api/v1/rfid/ingest", json={"reads": []}, headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key)
    )
    assert pre_resp.status_code == 201, pre_resp.text

    gateway.status = "revoked"
    await db.commit()

    post_resp = await client.post(
        "/api/v1/rfid/ingest", json={"reads": []}, headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key)
    )
    assert post_resp.status_code == 401


async def test_missing_gateway_headers_are_rejected(client, db):
    tenant = await _enabled_tenant(db, "rfid-gw-auth-missing-headers")
    await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()

    resp = await client.post("/api/v1/rfid/ingest", json={"reads": []})
    assert resp.status_code == 401


async def test_user_jwt_cannot_reach_gateway_only_ingest_endpoint(client, db):
    """Direction 1 of the auth-boundary claim: a perfectly valid user bearer token, with every
    relevant permission, still cannot authenticate to /rfid/ingest — that endpoint has no
    get_token_payload dependency anywhere in its chain at all."""
    tenant = await _enabled_tenant(db, "rfid-gw-auth-user-cannot-reach-gateway")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="FullRfidUser", permission_keys=["track_rfid.manage_tags", "track_rfid.view"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="user@rfid-gw-auth-test.example", role=role)
    await db.commit()

    resp = await client.post("/api/v1/rfid/ingest", json={"reads": []}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_gateway_key_cannot_reach_a_user_permission_gated_endpoint(client, db):
    """Direction 2 of the auth-boundary claim: a perfectly valid, active gateway key, sent as
    the two gateway headers with no Authorization bearer token, cannot reach an ordinary
    user-JWT endpoint — get_token_payload requires a bearer token regardless of what other
    headers are present."""
    tenant = await _enabled_tenant(db, "rfid-gw-auth-gateway-cannot-reach-user")
    _gateway, raw_key = await make_device_gateway(db, tenant_id=tenant.id)
    await db.commit()

    resp = await client.get(
        "/api/v1/tracking/gateways", headers=gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key)
    )
    assert resp.status_code == 401
