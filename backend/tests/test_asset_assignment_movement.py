"""app.flow's AssetAssignment (custody) and AssetMovement. The single-active-assignment guard
gets an explicit illegal-operation-rejected test (double-assign without unassigning first),
per the implementation plan's verification checklist, not just the happy path."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_FLOW_PERMS = ["assets.assign", "assets.move", "asset_lifecycle.view"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage", "asset_locations.view", "asset_locations.manage"]


async def _make_flow_user(db, tenant, *, email="flowuser@assignment-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="AssignMoveUser", permission_keys=_FLOW_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def _create_asset(client, headers, name="Custody Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Tablet"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _create_location(client, headers, name):
    resp = await client.post("/api/v1/asset-locations", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_assign_and_unassign_custodian_happy_path(client, db):
    tenant = await make_tenant(db, subdomain="assignment-happy-path")
    user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    assign_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/assign", json={"custodian_user_id": str(user.id)}, headers=headers
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assert assign_resp.json()["data"]["unassigned_at"] is None

    asset_after_assign = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after_assign["current_custodian_id"] == str(user.id)

    unassign_resp = await client.post(f"/api/v1/assets/{asset['id']}/unassign", json={}, headers=headers)
    assert unassign_resp.status_code == 200, unassign_resp.text
    assert unassign_resp.json()["data"]["unassigned_at"] is not None

    asset_after_unassign = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after_unassign["current_custodian_id"] is None


async def test_double_assign_without_unassigning_is_rejected(client, db):
    """The single-active-assignment guard: FlowService.assign_custodian must reject a second
    assignment while one is still active (unassigned_at IS NULL), enforced in the service
    layer rather than a DB partial index (see AssetAssignment's docstring)."""
    tenant = await make_tenant(db, subdomain="assignment-double-assign-guard")
    user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    first = await client.post(f"/api/v1/assets/{asset['id']}/assign", json={"custodian_user_id": str(user.id)}, headers=headers)
    assert first.status_code == 201

    second = await client.post(f"/api/v1/assets/{asset['id']}/assign", json={"custodian_user_id": str(user.id)}, headers=headers)
    assert second.status_code == 409

    # Unassigning first frees it up for a new assignment.
    await client.post(f"/api/v1/assets/{asset['id']}/unassign", json={}, headers=headers)
    third = await client.post(f"/api/v1/assets/{asset['id']}/assign", json={"custodian_user_id": str(user.id)}, headers=headers)
    assert third.status_code == 201


async def test_unassigning_with_no_active_assignment_is_404(client, db):
    tenant = await make_tenant(db, subdomain="assignment-unassign-404")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(f"/api/v1/assets/{asset['id']}/unassign", json={}, headers=headers)
    assert resp.status_code == 404


async def test_move_asset_between_locations(client, db):
    tenant = await make_tenant(db, subdomain="movement-happy-path")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    warehouse = await _create_location(client, headers, "Warehouse")
    office = await _create_location(client, headers, "Office")

    first_move = await client.post(
        f"/api/v1/assets/{asset['id']}/move", json={"to_location_id": warehouse["id"]}, headers=headers
    )
    assert first_move.status_code == 200, first_move.text
    assert first_move.json()["data"]["from_location_id"] is None
    assert first_move.json()["data"]["to_location_id"] == warehouse["id"]

    second_move = await client.post(f"/api/v1/assets/{asset['id']}/move", json={"to_location_id": office["id"]}, headers=headers)
    assert second_move.status_code == 200
    assert second_move.json()["data"]["from_location_id"] == warehouse["id"]
    assert second_move.json()["data"]["to_location_id"] == office["id"]

    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_location_id"] == office["id"]

    history = await client.get(f"/api/v1/assets/{asset['id']}/history", headers=headers)
    movement_entries = [e for e in history.json()["data"] if e["entry_type"] == "movement"]
    assert len(movement_entries) == 2


async def test_move_to_a_missing_location_is_404(client, db):
    tenant = await make_tenant(db, subdomain="movement-missing-location")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(
        f"/api/v1/assets/{asset['id']}/move",
        json={"to_location_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_assign_and_move_endpoints_require_permission(client, db):
    tenant = await make_tenant(db, subdomain="assignment-movement-perm-guard")
    role = await make_role_with_permissions(db, tenant_id=None, name="NoAssignMovePerms", permission_keys=[])
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noperm@assignment-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    fake_asset_id = "00000000-0000-0000-0000-000000000000"
    assign_resp = await client.post(
        f"/api/v1/assets/{fake_asset_id}/assign", json={"custodian_user_id": str(user.id)}, headers=headers
    )
    assert assign_resp.status_code == 403

    move_resp = await client.post(f"/api/v1/assets/{fake_asset_id}/move", json={"to_location_id": fake_asset_id}, headers=headers)
    assert move_resp.status_code == 403
