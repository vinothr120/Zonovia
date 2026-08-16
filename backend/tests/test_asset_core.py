"""app.asset_core — category/type/vendor catalog CRUD and core Asset CRUD (identifiers and
documents get their own dedicated test files). asset-core defaults to entitled
(default_enabled=True) so these hit the real require_module("asset-core") gate on every
request without needing an explicit TenantModuleEntitlement row — see test_asset_core_module_gate.py
for the gate itself being exercised in isolation."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_CATALOG_PERMS = ["assets.view", "assets.create", "assets.edit", "assets.delete", "asset_catalog.manage"]


async def _make_catalog_user(db, tenant, *, permission_keys=None):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="AssetCatalogUser", permission_keys=permission_keys or _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="catalog@asset-core-test.example", role=role)
    return user, token


async def _create_category(client, headers, name="IT Equipment"):
    resp = await client.post("/api/v1/asset-categories", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_type(client, headers, category_id, name="Laptop"):
    resp = await client.post("/api/v1/asset-types", json={"category_id": category_id, "name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_create_category_type_vendor_and_asset_end_to_end(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-e2e")
    _user, token = await _make_catalog_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    category = await _create_category(client, headers)
    asset_type = await _create_type(client, headers, category["id"])

    vendor_resp = await client.post("/api/v1/vendors", json={"name": "Acme Supplies"}, headers=headers)
    assert vendor_resp.status_code == 201, vendor_resp.text
    vendor = vendor_resp.json()["data"]

    create_resp = await client.post(
        "/api/v1/assets",
        json={
            "name": "Dell Latitude #1",
            "asset_type_id": asset_type["id"],
            "vendor_id": vendor["id"],
            "purchase_price": "1200.50",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    asset = create_resp.json()["data"]
    assert asset["name"] == "Dell Latitude #1"
    assert asset["current_lifecycle_state_id"] is None  # AssetService.create_asset always leaves this NULL
    assert asset["current_location_id"] is None

    get_resp = await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["vendor_id"] == vendor["id"]

    list_resp = await client.get("/api/v1/assets", headers=headers)
    assert list_resp.status_code == 200
    assert any(a["id"] == asset["id"] for a in list_resp.json()["data"])

    update_resp = await client.patch(
        f"/api/v1/assets/{asset['id']}", json={"name": "Dell Latitude #1 (renamed)"}, headers=headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"] == "Dell Latitude #1 (renamed)"

    delete_resp = await client.delete(f"/api/v1/assets/{asset['id']}", headers=headers)
    assert delete_resp.status_code == 204

    after_delete = await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)
    assert after_delete.status_code == 404


async def test_duplicate_category_name_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-dup-category")
    _user, token = await _make_catalog_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    await _create_category(client, headers, name="Furniture")
    dup = await client.post("/api/v1/asset-categories", json={"name": "Furniture"}, headers=headers)
    assert dup.status_code == 409


async def test_create_asset_type_under_missing_category_is_404(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-type-404")
    _user, token = await _make_catalog_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/asset-types",
        json={"category_id": "00000000-0000-0000-0000-000000000000", "name": "Ghost Type"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_create_asset_with_missing_asset_type_is_404(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-asset-404")
    _user, token = await _make_catalog_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/assets",
        json={"name": "Orphan Asset", "asset_type_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_asset_endpoints_require_permission(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-perm-guard")
    role = await make_role_with_permissions(db, tenant_id=None, name="NoAssetPerms", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noperm@asset-core-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/assets", headers=headers)
    assert resp.status_code == 403


async def test_asset_identifier_allow_list_and_single_primary_enforcement(client, db):
    tenant = await make_tenant(db, subdomain="asset-core-identifiers")
    _user, token = await _make_catalog_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    category = await _create_category(client, headers)
    asset_type = await _create_type(client, headers, category["id"])
    asset_resp = await client.post(
        "/api/v1/assets", json={"name": "Tagged Asset", "asset_type_id": asset_type["id"]}, headers=headers
    )
    asset_id = asset_resp.json()["data"]["id"]

    bad_type = await client.post(
        f"/api/v1/assets/{asset_id}/identifiers", json={"identifier_type": "NFC_TAG", "value": "abc"}, headers=headers
    )
    assert bad_type.status_code == 422

    # RFID_EPC (Phase 6) IS in the allow-list now — a bare identifier with no app.track_rfid.
    # RfidTag row is valid, same non-exclusive relationship QR/Barcode already have; see
    # app.track_rfid.models.RfidTag's docstring.
    rfid_bare = await client.post(
        f"/api/v1/assets/{asset_id}/identifiers", json={"identifier_type": "RFID_EPC", "value": "E200001A"}, headers=headers
    )
    assert rfid_bare.status_code == 201, rfid_bare.text

    first = await client.post(
        f"/api/v1/assets/{asset_id}/identifiers",
        json={"identifier_type": "QR", "value": "QR-0001", "is_primary": True},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    assert first.json()["data"]["is_primary"] is True

    second = await client.post(
        f"/api/v1/assets/{asset_id}/identifiers",
        json={"identifier_type": "BARCODE", "value": "BC-0001", "is_primary": True},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["data"]["is_primary"] is True

    listing = await client.get(f"/api/v1/assets/{asset_id}/identifiers", headers=headers)
    primaries = [i for i in listing.json()["data"] if i["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["value"] == "BC-0001"

    dup = await client.post(
        f"/api/v1/assets/{asset_id}/identifiers", json={"identifier_type": "QR", "value": "QR-0001"}, headers=headers
    )
    assert dup.status_code == 409
