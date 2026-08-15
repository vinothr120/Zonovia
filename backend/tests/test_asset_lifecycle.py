"""app.flow's configurable lifecycle engine: lazy default-graph seeding, legal transitions
(via LifecycleTransitionDefinition or the is_initial bootstrap path), and the explicit
illegal-transition-rejected case the implementation plan's verification checklist calls for."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_FLOW_PERMS = ["asset_lifecycle.view", "assets.transition_lifecycle", "asset_lifecycle.configure"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


async def _make_flow_user(db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="FlowUser", permission_keys=_FLOW_PERMS + _CATALOG_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="flowuser@asset-lifecycle-test.example", role=role)
    return user, token


async def _create_asset(client, headers):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post(
            "/api/v1/assets", json={"name": "Lifecycle Test Asset", "asset_type_id": asset_type["id"]}, headers=headers
        )
    ).json()["data"]
    return asset


async def _states_by_key(client, headers) -> dict:
    resp = await client.get("/api/v1/asset-lifecycle/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return {s["key"]: s for s in resp.json()["data"]}


async def test_default_lifecycle_is_lazily_seeded_with_13_states(client, db):
    tenant = await make_tenant(db, subdomain="asset-lifecycle-seed-states")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    states = await _states_by_key(client, headers)
    assert len(states) == 13
    assert states["procured"]["is_initial"] is True
    assert states["disposed"]["is_terminal"] is True
    # Every other state is neither initial nor terminal.
    assert all(s["is_initial"] is False for k, s in states.items() if k != "procured")
    assert all(s["is_terminal"] is False for k, s in states.items() if k != "disposed")


async def test_default_transitions_are_seeded(client, db):
    tenant = await make_tenant(db, subdomain="asset-lifecycle-seed-transitions")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    states = await _states_by_key(client, headers)
    resp = await client.get("/api/v1/asset-lifecycle/transitions", headers=headers)
    assert resp.status_code == 200
    edges = {(t["from_state_id"], t["to_state_id"]) for t in resp.json()["data"]}
    assert len(edges) == 24
    assert (states["procured"]["id"], states["received"]["id"]) in edges
    assert (states["retired"]["id"], states["disposed"]["id"]) in edges
    # No direct edge exists straight from procured to disposed.
    assert (states["procured"]["id"], states["disposed"]["id"]) not in edges


async def test_first_transition_must_target_an_initial_state(client, db):
    tenant = await make_tenant(db, subdomain="asset-lifecycle-bootstrap")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    states = await _states_by_key(client, headers)

    illegal = await client.post(
        f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": states["available"]["id"]}, headers=headers
    )
    assert illegal.status_code == 409

    legal = await client.post(
        f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": states["procured"]["id"]}, headers=headers
    )
    assert legal.status_code == 200, legal.text

    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_lifecycle_state_id"] == states["procured"]["id"]


async def test_transition_with_no_matching_definition_is_rejected(client, db):
    """A transition whose (from_state, to_state) pair has no LifecycleTransitionDefinition
    row must be rejected, even though both states individually exist."""
    tenant = await make_tenant(db, subdomain="asset-lifecycle-illegal-edge")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    states = await _states_by_key(client, headers)

    await client.post(f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": states["procured"]["id"]}, headers=headers)

    # procured -> disposed has no seeded edge.
    resp = await client.post(
        f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": states["disposed"]["id"]}, headers=headers
    )
    assert resp.status_code == 409

    # Asset must still be sitting in "procured" — the rejected attempt made no change.
    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_lifecycle_state_id"] == states["procured"]["id"]


async def test_valid_transition_chain_updates_asset_state_and_history(client, db):
    tenant = await make_tenant(db, subdomain="asset-lifecycle-chain")
    _user, token = await _make_flow_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    states = await _states_by_key(client, headers)

    for key in ("procured", "received", "registered", "tagged", "available"):
        resp = await client.post(
            f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": states[key]["id"]}, headers=headers
        )
        assert resp.status_code == 200, resp.text

    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_lifecycle_state_id"] == states["available"]["id"]

    history = await client.get(f"/api/v1/assets/{asset['id']}/history", headers=headers)
    assert history.status_code == 200
    transition_entries = [e for e in history.json()["data"] if e["entry_type"] == "lifecycle_transition"]
    assert len(transition_entries) == 5


async def test_lifecycle_endpoints_require_permission(client, db):
    tenant = await make_tenant(db, subdomain="asset-lifecycle-perm-guard")
    role = await make_role_with_permissions(db, tenant_id=None, name="NoFlowPerms", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noflow@asset-lifecycle-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/asset-lifecycle/states", headers=headers)
    assert resp.status_code == 403
