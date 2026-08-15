"""InventoryService.record_verification: reuses app.tracking.service.TrackingService.record_scan
directly (not reimplemented) — a real TrackingEvent row is created and InventoryCount.
tracking_event_id links to it; the expected_location_id snapshot is taken at record time and
must stay accurate even after a later Flow move; found != expected flags has_discrepancy;
and a cycle that isn't in_progress rejects the verification outright. Per the implementation
plan's verification checklist: don't just assert the count row exists, assert the link."""

from sqlalchemy import select

from app.entitlements.models import TenantModuleEntitlement
from app.tracking.models import TrackingEvent
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]
_CATALOG_PERMS = [
    "assets.view",
    "assets.create",
    "assets.edit",
    "asset_catalog.manage",
    "asset_locations.view",
    "asset_locations.manage",
    "assets.move",
    "asset_lifecycle.view",
]


async def _make_verification_user(db, tenant, *, email="verify@inventory-verify-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryVerifyUser", permission_keys=_INVENTORY_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="inventory", enabled=True, source="manual"))
    return user, token


async def _create_location(client, headers, name):
    resp = await client.post("/api/v1/asset-locations", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_asset_with_identifier(client, headers, *, name, value, location_id=None):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    body = {"name": name, "asset_type_id": asset_type["id"]}
    if location_id is not None:
        body["current_location_id"] = location_id
    asset = (await client.post("/api/v1/assets", json=body, headers=headers)).json()["data"]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "QR", "value": value}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text
    return asset


async def _start_cycle(client, headers, name="Verify Cycle"):
    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": name}, headers=headers)).json()["data"]
    start_resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    assert start_resp.status_code == 200, start_resp.text
    return cycle


async def test_verification_creates_a_real_tracking_event_and_links_it(client, db):
    tenant = await make_tenant(db, subdomain="inventory-verify-tracking-link")
    _user, token = await _make_verification_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    asset = await _create_asset_with_identifier(
        client, headers, name="Linked Asset", value="INV-LINK-QR", location_id=warehouse["id"]
    )
    cycle = await _start_cycle(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "INV-LINK-QR"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    count = resp.json()["data"]
    assert count["asset_id"] == asset["id"]
    assert count["tracking_event_id"] is not None

    events = (await db.execute(select(TrackingEvent).where(TrackingEvent.tenant_id == tenant.id))).scalars().all()
    assert len(events) == 1
    assert str(events[0].id) == count["tracking_event_id"]
    assert str(events[0].asset_id) == asset["id"]


async def test_expected_location_snapshot_stays_accurate_after_a_later_flow_move(client, db):
    """expected_location_id is captured from the asset's current location AT RECORD TIME, not
    read live — so a later Flow move must not retroactively change what an earlier
    InventoryCount says was 'expected'."""
    tenant = await make_tenant(db, subdomain="inventory-verify-snapshot-stable")
    _user, token = await _make_verification_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    office = await _create_location(client, headers, "Office")
    asset = await _create_asset_with_identifier(
        client, headers, name="Snapshot Asset", value="INV-SNAPSHOT-QR", location_id=warehouse["id"]
    )
    cycle = await _start_cycle(client, headers, name="Snapshot Cycle")

    count_resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "INV-SNAPSHOT-QR"},
        headers=headers,
    )
    assert count_resp.status_code == 201, count_resp.text
    count = count_resp.json()["data"]
    assert count["expected_location_id"] == warehouse["id"]
    assert count["found_location_id"] == warehouse["id"]
    assert count["has_discrepancy"] is False

    # Flow moves the asset AFTER the verification was recorded.
    move_resp = await client.post(f"/api/v1/assets/{asset['id']}/move", json={"to_location_id": office["id"]}, headers=headers)
    assert move_resp.status_code == 200, move_resp.text

    counts_after = (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/counts", headers=headers)).json()["data"]
    assert len(counts_after) == 1
    assert counts_after[0]["expected_location_id"] == warehouse["id"]  # unchanged, still the snapshot


async def test_found_location_different_from_expected_flags_discrepancy(client, db):
    tenant = await make_tenant(db, subdomain="inventory-verify-discrepancy")
    _user, token = await _make_verification_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    office = await _create_location(client, headers, "Office")
    await _create_asset_with_identifier(
        client, headers, name="Discrepant Asset", value="INV-DISC-QR", location_id=warehouse["id"]
    )
    cycle = await _start_cycle(client, headers, name="Discrepancy Cycle")

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "INV-DISC-QR", "found_location_id": office["id"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    count = resp.json()["data"]
    assert count["expected_location_id"] == warehouse["id"]
    assert count["found_location_id"] == office["id"]
    assert count["has_discrepancy"] is True


async def test_verification_against_a_non_in_progress_cycle_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="inventory-verify-wrong-status")
    _user, token = await _make_verification_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    await _create_asset_with_identifier(client, headers, name="Draft Cycle Asset", value="INV-DRAFT-QR")
    draft_cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Still Draft"}, headers=headers)).json()["data"]

    resp = await client.post(
        f"/api/v1/inventory/cycles/{draft_cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "INV-DRAFT-QR"},
        headers=headers,
    )
    assert resp.status_code == 409
