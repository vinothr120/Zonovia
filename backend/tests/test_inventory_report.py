"""InventoryService.get_cycle_report: missing = expected - verified (using list_expected_assets'
scope resolution); discrepancies must be computed from the LATEST InventoryCount per asset, not
any count ever recorded — a correcting re-scan must flip an asset out of the discrepancy list.
Per the implementation plan's verification checklist, this is tested explicitly, not just
inferred from the happy path."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]
_CATALOG_PERMS = [
    "assets.view",
    "assets.create",
    "assets.edit",
    "asset_catalog.manage",
    "asset_locations.view",
    "asset_locations.manage",
]


async def _make_report_user(db, tenant, *, email="report@inventory-report-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryReportUser", permission_keys=_INVENTORY_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="inventory", enabled=True, source="manual"))
    return user, token


async def _create_location(client, headers, name):
    resp = await client.post("/api/v1/asset-locations", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_asset_with_identifier(client, headers, *, name, value, location_id):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post(
            "/api/v1/assets",
            json={"name": name, "asset_type_id": asset_type["id"], "current_location_id": location_id},
            headers=headers,
        )
    ).json()["data"]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "QR", "value": value}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text
    return asset


async def test_missing_equals_expected_minus_verified(client, db):
    tenant = await make_tenant(db, subdomain="inventory-report-missing")
    _user, token = await _make_report_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    verified_asset = await _create_asset_with_identifier(
        client, headers, name="Verified Asset", value="RPT-VERIFIED-QR", location_id=warehouse["id"]
    )
    missing_asset = await _create_asset_with_identifier(
        client, headers, name="Missing Asset", value="RPT-MISSING-QR", location_id=warehouse["id"]
    )

    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Missing Report Cycle"}, headers=headers)).json()["data"]
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    scan_resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "RPT-VERIFIED-QR"},
        headers=headers,
    )
    assert scan_resp.status_code == 201, scan_resp.text

    report = (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=headers)).json()["data"]
    assert set(report["expected_asset_ids"]) == {verified_asset["id"], missing_asset["id"]}
    assert report["verified_asset_ids"] == [verified_asset["id"]]
    assert report["missing_asset_ids"] == [missing_asset["id"]]


async def test_discrepancy_uses_latest_count_not_any_count_ever(client, db):
    """A wrong-location scan flags a discrepancy; a subsequent correcting re-scan of the same
    asset must make it disappear from the discrepancy list — the report has to key off the
    LATEST count per asset, not any historical one."""
    tenant = await make_tenant(db, subdomain="inventory-report-latest-count")
    _user, token = await _make_report_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    office = await _create_location(client, headers, "Office")
    asset = await _create_asset_with_identifier(
        client, headers, name="Re-scanned Asset", value="RPT-RESCAN-QR", location_id=warehouse["id"]
    )

    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Rescan Cycle"}, headers=headers)).json()["data"]
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)

    # First scan: wrong location -> discrepancy.
    wrong_resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "RPT-RESCAN-QR", "found_location_id": office["id"]},
        headers=headers,
    )
    assert wrong_resp.status_code == 201, wrong_resp.text
    assert wrong_resp.json()["data"]["has_discrepancy"] is True

    report_before = (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=headers)).json()["data"]
    discrepant_ids_before = {d["asset_id"] for d in report_before["discrepancies"]}
    assert asset["id"] in discrepant_ids_before

    # Correcting re-scan: found matches expected -> no discrepancy on the latest row.
    correct_resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "RPT-RESCAN-QR", "found_location_id": warehouse["id"]},
        headers=headers,
    )
    assert correct_resp.status_code == 201, correct_resp.text
    assert correct_resp.json()["data"]["has_discrepancy"] is False

    report_after = (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=headers)).json()["data"]
    discrepant_ids_after = {d["asset_id"] for d in report_after["discrepancies"]}
    assert asset["id"] not in discrepant_ids_after
    # Two InventoryCount rows exist for this asset, but only one entry in verified_asset_ids —
    # "latest per asset", not "one row per count".
    assert report_after["verified_asset_ids"].count(asset["id"]) == 1

    counts_history = (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/counts", headers=headers)).json()["data"]
    assert len(counts_history) == 2
