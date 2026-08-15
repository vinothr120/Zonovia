"""InventoryService.record_reconciliation: action recorded + audited; action_type allow-list
enforced (422 on garbage); guarded against draft/cancelled cycles (409); and — the core
"record, don't execute" boundary the whole module is built around — explicitly asserts the
asset's own current_location_id/current_lifecycle_state_id are UNCHANGED after reconciling.
record_reconciliation never calls app.flow.service.FlowService."""

from sqlalchemy import select

from app.audit.models import AuditLog
from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]
_CATALOG_PERMS = [
    "assets.view",
    "assets.create",
    "asset_catalog.manage",
    "asset_locations.view",
    "asset_locations.manage",
    "assets.move",
    "asset_lifecycle.view",
    "assets.transition_lifecycle",
]


async def _make_reconcile_user(db, tenant, *, email="reconcile@inventory-reconcile-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryReconcileUser", permission_keys=_INVENTORY_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="inventory", enabled=True, source="manual"))
    return user, token


async def _create_location(client, headers, name):
    resp = await client.post("/api/v1/asset-locations", json={"name": name}, headers=headers)
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


async def _start_cycle(client, headers, name="Reconcile Cycle"):
    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": name}, headers=headers)).json()["data"]
    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    assert resp.status_code == 200, resp.text
    return cycle


async def test_reconciliation_is_recorded_and_audited(client, db):
    tenant = await make_tenant(db, subdomain="inventory-reconcile-happy-path")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Reconciled Asset")
    cycle = await _start_cycle(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "acknowledged", "note": "Confirmed present, ledger updated manually."},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    action = resp.json()["data"]
    assert action["asset_id"] == asset["id"]
    assert action["action_type"] == "acknowledged"

    listing = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations", headers=headers)
    assert listing.status_code == 200
    assert [a["id"] for a in listing.json()["data"]] == [action["id"]]

    logs = (
        (
            await db.execute(
                select(AuditLog).where(AuditLog.tenant_id == tenant.id, AuditLog.action == "inventory_reconciliation.recorded")
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].new_value["asset_id"] == asset["id"]


async def test_reconciliation_of_a_never_scanned_missing_asset_is_allowed(client, db):
    """ReconciliationAction is keyed by (cycle_id, asset_id), not an InventoryCount FK — a
    'missing' asset with zero counts must still be reconcilable (e.g. marked_lost)."""
    tenant = await make_tenant(db, subdomain="inventory-reconcile-missing-asset")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Never Scanned Asset")
    cycle = await _start_cycle(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "marked_lost", "note": "Not found during walkthrough."},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["action_type"] == "marked_lost"


async def test_invalid_action_type_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="inventory-reconcile-bad-action-type")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Bad Action Asset")
    cycle = await _start_cycle(client, headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "not_a_real_action"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_reconciliation_against_a_draft_cycle_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="inventory-reconcile-draft-rejected")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Draft Cycle Asset")
    draft_cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Still Draft"}, headers=headers)).json()["data"]

    resp = await client.post(
        f"/api/v1/inventory/cycles/{draft_cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "acknowledged"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_reconciliation_against_a_cancelled_cycle_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="inventory-reconcile-cancelled-rejected")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Cancelled Cycle Asset")
    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Will Be Cancelled"}, headers=headers)).json()["data"]
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/cancel", headers=headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "acknowledged"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_reconciliation_against_a_completed_cycle_is_allowed(client, db):
    tenant = await make_tenant(db, subdomain="inventory-reconcile-completed-allowed")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers, "Completed Cycle Asset")
    cycle = await _start_cycle(client, headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/complete", headers=headers)

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "other", "note": "Resolved after cycle closed."},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def test_reconciliation_does_not_change_the_assets_own_location_or_lifecycle_state(client, db):
    """The core 'record, don't execute' boundary: record_reconciliation persists a decision
    but never calls FlowService, so the asset's own current_location_id/
    current_lifecycle_state_id must be exactly what they were before reconciling, even for a
    'location_corrected' decision."""
    tenant = await make_tenant(db, subdomain="inventory-reconcile-no-side-effects")
    _user, token = await _make_reconcile_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    warehouse = await _create_location(client, headers, "Warehouse")
    office = await _create_location(client, headers, "Office")
    asset = await _create_asset(client, headers, "Untouched Asset", location_id=warehouse["id"])

    # Give the asset a real lifecycle state too, so there's something non-null to prove
    # unchanged.
    states_resp = await client.get("/api/v1/asset-lifecycle/states", headers=headers)
    assert states_resp.status_code == 200, states_resp.text
    initial_state = next(s for s in states_resp.json()["data"] if s["is_initial"])
    transition_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/transition", json={"to_state_id": initial_state["id"]}, headers=headers
    )
    assert transition_resp.status_code == 200, transition_resp.text

    before = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert before["current_location_id"] == warehouse["id"]
    assert before["current_lifecycle_state_id"] == initial_state["id"]

    cycle = await _start_cycle(client, headers)
    reconcile_resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={
            "asset_id": asset["id"],
            "action_type": "location_corrected",
            "note": f"Actually found in {office['name']}, not {warehouse['name']}.",
        },
        headers=headers,
    )
    assert reconcile_resp.status_code == 201, reconcile_resp.text

    after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert after["current_location_id"] == before["current_location_id"] == warehouse["id"]
    assert after["current_lifecycle_state_id"] == before["current_lifecycle_state_id"] == initial_state["id"]
