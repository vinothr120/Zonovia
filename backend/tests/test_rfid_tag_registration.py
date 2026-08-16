"""RfidTagService.register_tag: creates the AssetIdentifier(identifier_type="RFID_EPC") and the
1:1 RfidTag row atomically; a duplicate EPC is rejected 409 (asset_core's own uniqueness
constraint); and the non-exclusivity confirmation — asset_core's generic identifier endpoint can
add a bare RFID_EPC identifier with NO RfidTag row, same as QR/Barcode already can."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_CATALOG_PERMS = ["assets.view", "assets.create", "assets.edit", "asset_catalog.manage"]
_RFID_PERMS = ["track_rfid.manage_tags", "track_rfid.view"]


async def _make_user(db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="RfidRegUser", permission_keys=_RFID_PERMS + _CATALOG_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="reg@rfid-tag-test.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="track-rfid", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name="Tag Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"IT - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post(
            "/api/v1/asset-types", json={"category_id": category["id"], "name": f"Laptop - {name}"}, headers=headers
        )
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def test_register_tag_creates_identifier_and_tag_atomically(client, db):
    tenant = await make_tenant(db, subdomain="rfid-tag-atomic-create")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    resp = await client.post(
        "/api/v1/rfid/tags", json={"asset_id": asset["id"], "epc": "E200001A", "tag_type": "active"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["asset_id"] == asset["id"]
    assert data["tag_type"] == "active"
    assert data["epc"] == "E200001A"
    assert data["asset_identifier_id"] is not None

    # The AssetIdentifier row genuinely exists and is discoverable through asset_core's own
    # identifier listing — not a phantom reference.
    identifiers_resp = await client.get(f"/api/v1/assets/{asset['id']}/identifiers", headers=headers)
    identifiers = identifiers_resp.json()["data"]
    matching = [i for i in identifiers if i["identifier_type"] == "RFID_EPC" and i["value"] == "E200001A"]
    assert len(matching) == 1
    assert matching[0]["id"] == data["asset_identifier_id"]

    # And the tag is readable back through its own endpoint.
    read_resp = await client.get(f"/api/v1/rfid/tags/{asset['id']}", headers=headers)
    assert read_resp.status_code == 200
    assert read_resp.json()["data"]["id"] == data["id"]


async def test_duplicate_epc_returns_409(client, db):
    tenant = await make_tenant(db, subdomain="rfid-tag-duplicate-epc")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset_a = await _create_asset(client, headers, name="Asset A")
    asset_b = await _create_asset(client, headers, name="Asset B")

    first = await client.post("/api/v1/rfid/tags", json={"asset_id": asset_a["id"], "epc": "E200DUP1"}, headers=headers)
    assert first.status_code == 201, first.text

    dup = await client.post("/api/v1/rfid/tags", json={"asset_id": asset_b["id"], "epc": "E200DUP1"}, headers=headers)
    assert dup.status_code == 409


async def test_bare_rfid_identifier_with_no_tag_row_is_valid_non_exclusive(client, db):
    """asset_core's generic POST /assets/{id}/identifiers can add a bare RFID_EPC identifier
    with no RfidTag row — the same non-exclusive relationship QR/Barcode identifiers already
    have. RfidTag is opt-in enrichment, never a requirement."""
    tenant = await make_tenant(db, subdomain="rfid-tag-bare-non-exclusive")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    bare_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "RFID_EPC", "value": "E200BARE"}, headers=headers
    )
    assert bare_resp.status_code == 201, bare_resp.text

    # No RfidTag row exists for this asset — GET /rfid/tags/{asset_id} 404s even though a
    # genuinely valid RFID_EPC identifier exists on the asset.
    tag_resp = await client.get(f"/api/v1/rfid/tags/{asset['id']}", headers=headers)
    assert tag_resp.status_code == 404
