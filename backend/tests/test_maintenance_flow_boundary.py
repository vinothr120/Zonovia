"""The core 'read-only, not write-through' boundary the whole module is built around, same
style as test_inventory_reconciliation.py's asset-unchanged assertion: completing or cancelling
a MaintenanceTicket must never touch the asset's own current_lifecycle_state_id —
MaintenanceService never calls app.flow.service.FlowService.transition_asset. The flip side is
the one real read capability Maintenance does get: GET /maintenance/tickets?
lifecycle_state_key=under_maintenance, resolved via the read-only
LifecycleStateDefinitionRepository, correctly picks up an asset that was manually moved to
under_maintenance via Flow's own /assets/{id}/transition endpoint."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]
_FLOW_PERMS = ["asset_lifecycle.view", "assets.transition_lifecycle"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]

# procured -> received -> registered -> tagged -> available -> assigned -> under_maintenance,
# every edge confirmed present in app.flow.service._DEFAULT_TRANSITIONS.
_PATH_TO_UNDER_MAINTENANCE = ["procured", "received", "registered", "tagged", "available", "assigned", "under_maintenance"]


async def _make_user(db, tenant, *, email="user@maintenance-flow-boundary-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"MaintFlowUser-{email}", permission_keys=_MAINTENANCE_PERMS + _FLOW_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _states_by_key(client, headers) -> dict:
    resp = await client.get("/api/v1/asset-lifecycle/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return {s["key"]: s for s in resp.json()["data"]}


async def _transition_through(client, headers, asset_id, keys, states_by_key):
    for key in keys:
        resp = await client.post(
            f"/api/v1/assets/{asset_id}/transition", json={"to_state_id": states_by_key[key]["id"]}, headers=headers
        )
        assert resp.status_code == 200, resp.text
    return states_by_key[keys[-1]]["id"]


async def _create_ticket(client, headers, asset_id, title="Repair"):
    resp = await client.post("/api/v1/maintenance/tickets", json={"asset_id": asset_id, "title": title}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_completing_a_ticket_never_changes_the_assets_lifecycle_state(client, db):
    tenant = await make_tenant(db, subdomain="maint-flow-boundary-complete")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Boundary Complete Asset")
    states_by_key = await _states_by_key(client, headers)
    expected_state_id = await _transition_through(client, headers, asset["id"], ["procured", "received"], states_by_key)

    before = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert before["current_lifecycle_state_id"] == expected_state_id

    ticket = await _create_ticket(client, headers, asset["id"])
    await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    complete_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={}, headers=headers)
    assert complete_resp.status_code == 200, complete_resp.text

    after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert after["current_lifecycle_state_id"] == before["current_lifecycle_state_id"] == expected_state_id


async def test_cancelling_a_ticket_never_changes_the_assets_lifecycle_state(client, db):
    tenant = await make_tenant(db, subdomain="maint-flow-boundary-cancel")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Boundary Cancel Asset")
    states_by_key = await _states_by_key(client, headers)
    expected_state_id = await _transition_through(client, headers, asset["id"], ["procured"], states_by_key)

    ticket = await _create_ticket(client, headers, asset["id"])
    cancel_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/cancel", json={}, headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text

    after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert after["current_lifecycle_state_id"] == expected_state_id


async def test_ticket_list_filter_picks_up_an_asset_manually_moved_to_under_maintenance(client, db):
    """The positive read-path: an asset moved to under_maintenance purely through Flow's own
    endpoint (never anything in app.maintenance) is correctly surfaced by the
    lifecycle_state_key filter, while an asset never moved there is excluded."""
    tenant = await make_tenant(db, subdomain="maint-flow-boundary-read-path")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    under_maintenance_asset = await _create_asset(client, headers, "Under Maintenance Asset")
    available_asset = await _create_asset(client, headers, "Still Available Asset")
    states_by_key = await _states_by_key(client, headers)

    await _transition_through(client, headers, under_maintenance_asset["id"], _PATH_TO_UNDER_MAINTENANCE, states_by_key)
    await _transition_through(
        client, headers, available_asset["id"], ["procured", "received", "registered", "tagged", "available"], states_by_key
    )

    ticket_on_under_maintenance = await _create_ticket(client, headers, under_maintenance_asset["id"], title="Fix it")
    await _create_ticket(client, headers, available_asset["id"], title="Unrelated ticket")

    resp = await client.get("/api/v1/maintenance/tickets?lifecycle_state_key=under_maintenance", headers=headers)
    assert resp.status_code == 200, resp.text
    ticket_ids = [t["id"] for t in resp.json()["data"]]
    assert ticket_ids == [ticket_on_under_maintenance["id"]]


async def test_ticket_list_filter_with_unknown_lifecycle_state_key_returns_empty_not_an_error(client, db):
    tenant = await make_tenant(db, subdomain="maint-flow-boundary-unknown-key")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Unknown Key Asset")
    await _create_ticket(client, headers, asset["id"])

    resp = await client.get("/api/v1/maintenance/tickets?lifecycle_state_key=not_a_real_state", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_maintenance_module_never_imports_flow_service_or_calls_transition_asset():
    """Static grep-style check, run as part of the suite: the Flow read-only boundary is a
    file-level property, not just a runtime behavior — app/maintenance/ must never import
    app.flow.service.FlowService nor call transition_asset(...) anywhere. Matches actual
    import/instantiation/call syntax (not prose that merely *mentions* FlowService/
    transition_asset while explaining the boundary, which several docstrings in this module
    deliberately do)."""
    import pathlib
    import re

    _real_usage_patterns = [
        re.compile(r"from app\.flow\.service import"),
        re.compile(r"import app\.flow\.service"),
        re.compile(r"FlowService\("),
        re.compile(r"\.transition_asset\("),
    ]

    maintenance_dir = pathlib.Path(__file__).resolve().parent.parent / "app" / "maintenance"
    offenders = []
    for path in maintenance_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in _real_usage_patterns):
            offenders.append(path.name)
    assert offenders == []
