"""app.tracking's scan resolution end to end: QR happy path, BARCODE happy path (proving the
two-provider claim, not just one code path), unresolved code -> 404 + audit row + no
TrackingEvent row, unsupported identifier_type ("SERIAL") -> 422, and per-asset event
isolation."""

from sqlalchemy import select

from app.audit.models import AuditLog
from app.tracking.models import TrackingEvent
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_TRACKING_PERMS = ["tracking.scan", "tracking.view"]
_CATALOG_PERMS = ["assets.view", "assets.create", "assets.edit", "asset_catalog.manage"]


async def _make_tracking_user(db, tenant, *, email="tracker@tracking-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="TrackingUser", permission_keys=_TRACKING_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def _create_asset_with_identifier(client, headers, *, identifier_type, value, name="Tracked Laptop"):
    # Category/type names are unique per tenant (uq_asset_categories_tenant_name /
    # uq_asset_types_tenant_name) — derive them from `name` so this helper can be called more
    # than once against the same tenant without a 409 collision.
    category = (await client.post("/api/v1/asset-categories", json={"name": f"IT - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post(
            "/api/v1/asset-types", json={"category_id": category["id"], "name": f"Laptop - {name}"}, headers=headers
        )
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers",
        json={"identifier_type": identifier_type, "value": value},
        headers=headers,
    )
    assert ident_resp.status_code == 201, ident_resp.text
    return asset


async def test_scan_resolves_via_qr_happy_path(client, db):
    tenant = await make_tenant(db, subdomain="tracking-qr-happy-path")
    _user, token = await _make_tracking_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset_with_identifier(client, headers, identifier_type="QR", value="QR-CODE-001")

    resp = await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "QR-CODE-001"}, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert set(data.keys()) == {"asset", "tracking_event"}
    assert data["asset"]["id"] == asset["id"]
    assert data["asset"]["name"] == asset["name"]
    assert data["tracking_event"]["asset_id"] == asset["id"]
    assert data["tracking_event"]["provider_type"] == "QR"
    assert data["tracking_event"]["event_type"] == "scan"
    assert data["tracking_event"]["payload"]["normalized_value"] == "QR-CODE-001"
    assert data["tracking_event"]["payload"]["raw_value"] == "QR-CODE-001"

    events_resp = await client.get(f"/api/v1/assets/{asset['id']}/tracking-events", headers=headers)
    assert events_resp.status_code == 200
    events = events_resp.json()["data"]
    assert isinstance(events, list)
    assert len(events) == 1
    assert events[0]["id"] == data["tracking_event"]["id"]


async def test_scan_resolves_via_barcode_happy_path(client, db):
    """Proves the two-provider claim end to end — a separate BARCODE-type identifier resolves
    through BarcodeProvider, not just QRProvider."""
    tenant = await make_tenant(db, subdomain="tracking-barcode-happy-path")
    _user, token = await _make_tracking_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset_with_identifier(client, headers, identifier_type="BARCODE", value="012345678905")

    resp = await client.post(
        "/api/v1/tracking/scan", json={"identifier_type": "BARCODE", "value": "012345678905"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["asset"]["id"] == asset["id"]
    assert data["tracking_event"]["provider_type"] == "BARCODE"
    assert data["tracking_event"]["payload"]["normalized_value"] == "012345678905"


async def test_scan_with_unresolved_code_returns_404_writes_audit_log_and_no_tracking_event(client, db):
    tenant = await make_tenant(db, subdomain="tracking-unresolved")
    _user, token = await _make_tracking_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "no-such-code"}, headers=headers)
    assert resp.status_code == 404

    events = (await db.execute(select(TrackingEvent).where(TrackingEvent.tenant_id == tenant.id))).scalars().all()
    assert events == []

    logs = (
        (await db.execute(select(AuditLog).where(AuditLog.tenant_id == tenant.id, AuditLog.action == "tracking.scan_unresolved")))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].entity_id is None
    assert logs[0].new_value["raw_value"] == "no-such-code"


async def test_scan_with_unsupported_identifier_type_serial_returns_422(client, db):
    """asset_core's allow-list stays untouched — tracking-engine independently has no
    provider registered for SERIAL, since a serial number isn't something a camera scans."""
    tenant = await make_tenant(db, subdomain="tracking-serial-rejected")
    _user, token = await _make_tracking_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/tracking/scan", json={"identifier_type": "SERIAL", "value": "SN-001"}, headers=headers)
    assert resp.status_code == 422


async def test_tracking_events_are_isolated_per_asset(client, db):
    tenant = await make_tenant(db, subdomain="tracking-per-asset-isolation")
    _user, token = await _make_tracking_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset_a = await _create_asset_with_identifier(client, headers, identifier_type="QR", value="ASSET-A-QR", name="Asset A")
    asset_b = await _create_asset_with_identifier(client, headers, identifier_type="QR", value="ASSET-B-QR", name="Asset B")

    await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "ASSET-A-QR"}, headers=headers)
    await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "ASSET-A-QR"}, headers=headers)
    await client.post("/api/v1/tracking/scan", json={"identifier_type": "QR", "value": "ASSET-B-QR"}, headers=headers)

    events_a = (await client.get(f"/api/v1/assets/{asset_a['id']}/tracking-events", headers=headers)).json()["data"]
    events_b = (await client.get(f"/api/v1/assets/{asset_b['id']}/tracking-events", headers=headers)).json()["data"]
    assert len(events_a) == 2
    assert len(events_b) == 1
    assert all(e["asset_id"] == asset_a["id"] for e in events_a)
    assert all(e["asset_id"] == asset_b["id"] for e in events_b)
