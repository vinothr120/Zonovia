"""InventoryService.list_expected_assets scope resolution (exercised via GET
.../cycles/{id}/report's expected_asset_ids): root_location_id=None must resolve to every
tenant asset; a location-scoped cycle must resolve to the root location plus every descendant
via AssetLocationRepository.list_descendants (reused directly), using a real multi-level
location tree, and must explicitly EXCLUDE sibling-branch locations, not just some descendants
— per the implementation plan's verification checklist."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage", "asset_locations.view", "asset_locations.manage"]


async def _make_scope_user(db, tenant, *, email="scope@inventory-scope-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryScopeUser", permission_keys=_INVENTORY_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="inventory", enabled=True, source="manual"))
    return user, token


async def _create_location(client, headers, name, parent_id=None):
    resp = await client.post("/api/v1/asset-locations", json={"name": name, "parent_location_id": parent_id}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_asset(client, headers, name, location_id=None):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    body = {"name": name, "asset_type_id": asset_type["id"]}
    if location_id is not None:
        body["current_location_id"] = location_id
    resp = await client.post("/api/v1/assets", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _build_tree_and_assets(client, headers):
    building_a = await _create_location(client, headers, "Building A")
    floor_1 = await _create_location(client, headers, "Floor 1", parent_id=building_a["id"])
    room_101 = await _create_location(client, headers, "Room 101", parent_id=floor_1["id"])
    building_b = await _create_location(client, headers, "Building B")  # sibling root, not under Building A
    floor_x = await _create_location(client, headers, "Floor X", parent_id=building_b["id"])

    asset_building_a = await _create_asset(client, headers, "Asset In Building A", building_a["id"])
    asset_floor_1 = await _create_asset(client, headers, "Asset In Floor 1", floor_1["id"])
    asset_room_101 = await _create_asset(client, headers, "Asset In Room 101", room_101["id"])
    asset_building_b = await _create_asset(client, headers, "Asset In Building B", building_b["id"])
    asset_floor_x = await _create_asset(client, headers, "Asset In Floor X", floor_x["id"])
    asset_unlocated = await _create_asset(client, headers, "Asset With No Location")

    return {
        "building_a": building_a,
        "assets_under_building_a": {asset_building_a["id"], asset_floor_1["id"], asset_room_101["id"]},
        "assets_outside_building_a": {asset_building_b["id"], asset_floor_x["id"], asset_unlocated["id"]},
        "all_asset_ids": {
            asset_building_a["id"],
            asset_floor_1["id"],
            asset_room_101["id"],
            asset_building_b["id"],
            asset_floor_x["id"],
            asset_unlocated["id"],
        },
    }


async def test_root_location_none_resolves_to_every_tenant_asset(client, db):
    tenant = await make_tenant(db, subdomain="inventory-scope-all-assets")
    _user, token = await _make_scope_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    fixtures = await _build_tree_and_assets(client, headers)

    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "All Assets Cycle"}, headers=headers)).json()["data"]
    report = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=headers)
    assert report.status_code == 200, report.text
    assert set(report.json()["data"]["expected_asset_ids"]) == fixtures["all_asset_ids"]


async def test_location_scoped_cycle_includes_descendants_and_excludes_siblings(client, db):
    tenant = await make_tenant(db, subdomain="inventory-scope-subtree")
    _user, token = await _make_scope_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    fixtures = await _build_tree_and_assets(client, headers)

    cycle = (
        await client.post(
            "/api/v1/inventory/cycles",
            json={"name": "Building A Cycle", "root_location_id": fixtures["building_a"]["id"]},
            headers=headers,
        )
    ).json()["data"]
    report = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=headers)
    assert report.status_code == 200, report.text
    expected_ids = set(report.json()["data"]["expected_asset_ids"])

    assert expected_ids == fixtures["assets_under_building_a"]
    # The sibling branch (Building B/Floor X) and the unlocated asset must NOT leak in.
    assert expected_ids.isdisjoint(fixtures["assets_outside_building_a"])
