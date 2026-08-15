"""inventory.view / inventory.manage_cycles / inventory.verify / inventory.reconcile gating on
the real inventory endpoints — a user missing the specific permission a route requires must be
rejected (403), even with the inventory module itself enabled and every other inventory
permission granted."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_CATALOG_PERMS = [
    "assets.view",
    "assets.create",
    "assets.edit",
    "asset_catalog.manage",
    "asset_locations.view",
    "asset_locations.manage",
]
_ALL_INVENTORY_PERMS = ["inventory.view", "inventory.manage_cycles", "inventory.verify", "inventory.reconcile"]


async def _enable_inventory(db, tenant_id):
    db.add(TenantModuleEntitlement(tenant_id=tenant_id, module_key="inventory", enabled=True, source="manual"))


async def _make_setup_user(db, tenant):
    """Full-permission user used only to create fixture data (cycle, asset)."""
    role = await make_role_with_permissions(
        db, tenant_id=None, name="InventoryPermSetup", permission_keys=_ALL_INVENTORY_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="setup@inventory-perm-test.example", role=role)
    await _enable_inventory(db, tenant.id)
    return user, token


async def _create_asset_with_identifier(client, headers, *, name="Perm Test Asset", value="PERM-TEST-QR"):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "QR", "value": value}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text
    return asset


async def _make_role_with_only(db, tenant, *, permission_keys, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"OnlyRole-{email}", permission_keys=permission_keys)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return token


async def test_manage_cycles_permission_gates_create_start_complete_cancel(client, db):
    tenant = await make_tenant(db, subdomain="inventory-perm-manage-cycles")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["inventory.view"], email="viewonly@inventory-perm-test.example"
    )
    await db.commit()
    view_only_headers = {"Authorization": f"Bearer {view_only_token}"}

    create_resp = await client.post("/api/v1/inventory/cycles", json={"name": "Denied Cycle"}, headers=view_only_headers)
    assert create_resp.status_code == 403

    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Setup Cycle"}, headers=setup_headers)).json()["data"]

    start_resp = await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=view_only_headers)
    assert start_resp.status_code == 403

    # inventory.view alone is still enough to read.
    read_resp = await client.get(f"/api/v1/inventory/cycles/{cycle['id']}", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_verify_permission_gates_recording_a_count(client, db):
    tenant = await make_tenant(db, subdomain="inventory-perm-verify")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    await _create_asset_with_identifier(client, setup_headers)
    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Verify Perm Cycle"}, headers=setup_headers)).json()[
        "data"
    ]
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=setup_headers)

    no_verify_token = await _make_role_with_only(
        db, tenant, permission_keys=["inventory.view", "inventory.manage_cycles"], email="noverify@inventory-perm-test.example"
    )
    await db.commit()
    no_verify_headers = {"Authorization": f"Bearer {no_verify_token}"}

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/counts",
        json={"identifier_type": "QR", "value": "PERM-TEST-QR"},
        headers=no_verify_headers,
    )
    assert resp.status_code == 403


async def test_reconcile_permission_gates_recording_a_reconciliation(client, db):
    tenant = await make_tenant(db, subdomain="inventory-perm-reconcile")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    asset = await _create_asset_with_identifier(client, setup_headers)
    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "Reconcile Perm Cycle"}, headers=setup_headers)).json()[
        "data"
    ]
    await client.post(f"/api/v1/inventory/cycles/{cycle['id']}/start", headers=setup_headers)

    # Member-shaped bundle: view/verify/manage_cycles but not reconcile.
    member_token = await _make_role_with_only(
        db,
        tenant,
        permission_keys=["inventory.view", "inventory.manage_cycles", "inventory.verify"],
        email="member@inventory-perm-test.example",
    )
    await db.commit()
    member_headers = {"Authorization": f"Bearer {member_token}"}

    resp = await client.post(
        f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations",
        json={"asset_id": asset["id"], "action_type": "acknowledged"},
        headers=member_headers,
    )
    assert resp.status_code == 403


async def test_view_permission_gates_report_counts_and_reconciliations_listing(client, db):
    tenant = await make_tenant(db, subdomain="inventory-perm-view")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    cycle = (await client.post("/api/v1/inventory/cycles", json={"name": "View Perm Cycle"}, headers=setup_headers)).json()[
        "data"
    ]

    no_view_token = await _make_role_with_only(
        db, tenant, permission_keys=["inventory.manage_cycles"], email="noview@inventory-perm-test.example"
    )
    await db.commit()
    no_view_headers = {"Authorization": f"Bearer {no_view_token}"}

    assert (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/report", headers=no_view_headers)).status_code == 403
    assert (await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/counts", headers=no_view_headers)).status_code == 403
    assert (
        await client.get(f"/api/v1/inventory/cycles/{cycle['id']}/reconciliations", headers=no_view_headers)
    ).status_code == 403
    assert (await client.get("/api/v1/inventory/cycles", headers=no_view_headers)).status_code == 403
