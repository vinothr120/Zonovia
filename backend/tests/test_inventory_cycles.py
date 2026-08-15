"""app.inventory's InventoryCycle lifecycle: draft -> in_progress -> completed/cancelled, a
plain string status + hand-written guard-clause validation (not a generic engine — see
app/inventory/models.py's InventoryCycle docstring). Illegal transitions get an explicit
rejected-not-just-happy-path test per the implementation plan's verification checklist, plus
404 on a bad root_location_id."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]


async def _enable_inventory(db, tenant_id):
    db.add(TenantModuleEntitlement(tenant_id=tenant_id, module_key="inventory", enabled=True, source="manual"))


async def _make_inventory_user(db, tenant, *, email="cycles@inventory-cycles-test.example"):
    role = await make_role_with_permissions(db, tenant_id=None, name="InventoryCycleUser", permission_keys=_INVENTORY_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    await _enable_inventory(db, tenant.id)
    return user, token


async def _create_cycle(client, headers, name="Q1 Walkthrough", root_location_id=None):
    resp = await client.post(
        "/api/v1/inventory/cycles", json={"name": name, "root_location_id": root_location_id}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_create_cycle_defaults_to_draft(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-create")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    assert cycle["status"] == "draft"
    assert cycle["started_at"] is None
    assert cycle["completed_at"] is None
    assert cycle["root_location_id"] is None


async def test_create_cycle_with_bad_root_location_is_404(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-bad-root")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/inventory/cycles",
        json={"name": "Bad Root", "root_location_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_full_lifecycle_draft_to_in_progress_to_completed(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-full-lifecycle")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)

    start_resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    assert start_resp.status_code == 200, start_resp.text
    assert start_resp.json()["data"]["status"] == "in_progress"
    assert start_resp.json()["data"]["started_at"] is not None

    complete_resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/complete", headers=headers)
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["data"]["status"] == "completed"
    assert complete_resp.json()["data"]["completed_at"] is not None

    fetched = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}", headers=headers)
    assert fetched.json()["data"]["status"] == "completed"


async def test_draft_cycle_can_be_cancelled(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-cancel-draft")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"


async def test_in_progress_cycle_can_be_cancelled(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-cancel-in-progress")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"


async def test_completing_a_draft_cycle_is_rejected(client, db):
    """Guard-clause: only an in_progress cycle can be completed."""
    tenant = await make_tenant(db, subdomain="inventory-cycle-complete-draft-rejected")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/complete", headers=headers)
    assert resp.status_code == 409

    unchanged = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}", headers=headers)
    assert unchanged.json()["data"]["status"] == "draft"


async def test_starting_an_already_started_cycle_is_rejected(client, db):
    """Guard-clause: only a draft cycle can be started."""
    tenant = await make_tenant(db, subdomain="inventory-cycle-double-start-rejected")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    assert resp.status_code == 409


async def test_cancelling_a_completed_cycle_is_rejected(client, db):
    """Guard-clause: a completed (or already-cancelled) cycle cannot be cancelled."""
    tenant = await make_tenant(db, subdomain="inventory-cycle-cancel-completed-rejected")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/complete", headers=headers)

    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/cancel", headers=headers)
    assert resp.status_code == 409


async def test_starting_a_cancelled_cycle_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-start-cancelled-rejected")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle = await _create_cycle(client, headers)
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/cancel", headers=headers)

    resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=headers)
    assert resp.status_code == 409


async def test_get_and_list_cycles(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-list")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    cycle_a = await _create_cycle(client, headers, name="Cycle A")
    cycle_b = await _create_cycle(client, headers, name="Cycle B")

    listing = await client.get("/api/v1/inventory/cycles", headers=headers)
    assert listing.status_code == 200
    ids = {c["id"] for c in listing.json()["data"]}
    assert {cycle_a["id"], cycle_b["id"]} <= ids

    fetched = await client.get(f"/api/v1/inventory/cycles/{cycle_a['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["name"] == "Cycle A"


async def test_get_missing_cycle_is_404(client, db):
    tenant = await make_tenant(db, subdomain="inventory-cycle-missing")
    _user, token = await _make_inventory_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/inventory/cycles/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404
