"""app.asset_core's adjacency-list location hierarchy: create/update-with-cycle-guard/
delete-if-empty, plus the recursive-CTE-backed children/descendants/ancestors reads. The
cycle guard and delete-if-empty guard each get an explicit illegal-operation-rejected test,
not just the happy path, per the implementation plan's verification checklist."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_LOCATION_PERMS = ["asset_locations.view", "asset_locations.manage", "assets.view", "assets.create", "asset_catalog.manage"]


async def _make_location_user(db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="LocationAdmin", permission_keys=_LOCATION_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="locadmin@asset-locations-test.example", role=role)
    return user, token


async def _create_location(client, headers, name, parent_id=None):
    resp = await client.post("/api/v1/asset-locations", json={"name": name, "parent_location_id": parent_id}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_location_hierarchy_crud_and_reads(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-hierarchy")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    building = await _create_location(client, headers, "Building A")
    floor = await _create_location(client, headers, "Floor 1", parent_id=building["id"])
    room = await _create_location(client, headers, "Room 101", parent_id=floor["id"])

    roots_resp = await client.get("/api/v1/asset-locations", headers=headers)
    assert roots_resp.status_code == 200
    assert any(loc["id"] == building["id"] for loc in roots_resp.json()["data"])

    children_resp = await client.get(f"/api/v1/asset-locations/{building['id']}/children", headers=headers)
    assert children_resp.status_code == 200
    assert [loc["id"] for loc in children_resp.json()["data"]] == [floor["id"]]

    descendants_resp = await client.get(f"/api/v1/asset-locations/{building['id']}/descendants", headers=headers)
    assert descendants_resp.status_code == 200
    descendant_ids = {loc["id"] for loc in descendants_resp.json()["data"]}
    assert descendant_ids == {floor["id"], room["id"]}

    ancestors_resp = await client.get(f"/api/v1/asset-locations/{room['id']}/ancestors", headers=headers)
    assert ancestors_resp.status_code == 200
    ancestor_ids = [loc["id"] for loc in ancestors_resp.json()["data"]]
    assert ancestor_ids == [floor["id"], building["id"]]  # nearest first


async def test_duplicate_sibling_name_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-dup-sibling")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    await _create_location(client, headers, "Warehouse")
    dup = await client.post("/api/v1/asset-locations", json={"name": "Warehouse"}, headers=headers)
    assert dup.status_code == 409


async def test_reparenting_a_location_into_its_own_descendant_is_rejected(client, db):
    """The cycle guard: AssetLocationService.update_location must reject moving a location
    into one of its own descendants (which would create an unreachable cycle in the
    adjacency-list hierarchy)."""
    tenant = await make_tenant(db, subdomain="asset-locations-cycle-guard")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    building = await _create_location(client, headers, "Campus")
    floor = await _create_location(client, headers, "Wing B", parent_id=building["id"])
    room = await _create_location(client, headers, "Suite 9", parent_id=floor["id"])

    # Attempt to move "Campus" (the root ancestor) to become a child of "Suite 9" (its own
    # grandchild) — must be rejected, not silently accepted.
    resp = await client.patch(
        f"/api/v1/asset-locations/{building['id']}", json={"parent_location_id": room["id"]}, headers=headers
    )
    assert resp.status_code == 409

    # A location cannot be its own parent either.
    self_parent = await client.patch(
        f"/api/v1/asset-locations/{floor['id']}", json={"parent_location_id": floor["id"]}, headers=headers
    )
    assert self_parent.status_code == 409

    # The hierarchy must be unchanged after the rejected attempts.
    unchanged = await client.get(f"/api/v1/asset-locations/{building['id']}/ancestors", headers=headers)
    assert unchanged.json()["data"] == []


async def test_valid_reparent_is_accepted(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-reparent-ok")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    building_a = await _create_location(client, headers, "Building A")
    building_b = await _create_location(client, headers, "Building B")
    floor = await _create_location(client, headers, "Floor 1", parent_id=building_a["id"])

    resp = await client.patch(
        f"/api/v1/asset-locations/{floor['id']}", json={"parent_location_id": building_b["id"]}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["parent_location_id"] == building_b["id"]


async def test_deleting_a_location_with_children_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-delete-nonempty")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    building = await _create_location(client, headers, "HQ")
    await _create_location(client, headers, "Ground Floor", parent_id=building["id"])

    resp = await client.delete(f"/api/v1/asset-locations/{building['id']}", headers=headers)
    assert resp.status_code == 409


async def test_deleting_a_location_with_assets_assigned_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-delete-has-assets")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    location = await _create_location(client, headers, "Storage Room")

    category_resp = await client.post("/api/v1/asset-categories", json={"name": "Tools"}, headers=headers)
    category = category_resp.json()["data"]
    type_resp = await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Drill"}, headers=headers)
    asset_type = type_resp.json()["data"]
    await client.post(
        "/api/v1/assets",
        json={"name": "Cordless Drill", "asset_type_id": asset_type["id"], "current_location_id": location["id"]},
        headers=headers,
    )

    resp = await client.delete(f"/api/v1/asset-locations/{location['id']}", headers=headers)
    assert resp.status_code == 409


async def test_empty_leaf_location_can_be_deleted(client, db):
    tenant = await make_tenant(db, subdomain="asset-locations-delete-empty")
    _user, token = await _make_location_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    location = await _create_location(client, headers, "Empty Closet")
    resp = await client.delete(f"/api/v1/asset-locations/{location['id']}", headers=headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/asset-locations/{location['id']}", headers=headers)
    assert get_resp.status_code == 404
