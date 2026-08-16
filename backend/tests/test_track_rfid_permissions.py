"""track_rfid.manage_tags / track_rfid.view gating on the real /rfid/tags and /rfid/read-events
endpoints — mirrors test_maintenance_permissions.py's shape: a user missing the specific
permission a route requires must be rejected (403), even with the track-rfid module itself
enabled and the OTHER track_rfid permission granted."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]
_ALL_RFID_PERMS = ["track_rfid.manage_tags", "track_rfid.view"]


async def _enable_track_rfid(db, tenant_id):
    db.add(TenantModuleEntitlement(tenant_id=tenant_id, module_key="track-rfid", enabled=True, source="manual"))


async def _make_setup_user(db, tenant):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="RfidPermSetup", permission_keys=_ALL_RFID_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="setup@track-rfid-perm-test.example", role=role)
    await _enable_track_rfid(db, tenant.id)
    return user, token


async def _create_asset(client, headers, name="Perm Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def test_manage_tags_permission_gates_registration_but_not_read(client, db):
    tenant = await make_tenant(db, subdomain="track-rfid-perm-manage-tags")
    _setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = {"Authorization": f"Bearer {setup_token}"}

    asset = await _create_asset(client, setup_headers)

    view_only_role = await make_role_with_permissions(
        db, tenant_id=None, name="RfidViewOnly", permission_keys=["track_rfid.view"]
    )
    _user, view_only_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="viewonly@track-rfid-perm-test.example", role=view_only_role
    )
    await db.commit()
    view_only_headers = {"Authorization": f"Bearer {view_only_token}"}

    register_resp = await client.post(
        "/api/v1/rfid/tags", json={"asset_id": asset["id"], "epc": "E200001A"}, headers=view_only_headers
    )
    assert register_resp.status_code == 403

    setup_register = await client.post(
        "/api/v1/rfid/tags", json={"asset_id": asset["id"], "epc": "E200001A"}, headers=setup_headers
    )
    assert setup_register.status_code == 201, setup_register.text

    # track_rfid.view alone is still enough to read.
    read_resp = await client.get(f"/api/v1/rfid/tags/{asset['id']}", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_view_permission_gates_listing_reads_and_events(client, db):
    tenant = await make_tenant(db, subdomain="track-rfid-perm-view")
    _setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()

    no_view_role = await make_role_with_permissions(
        db, tenant_id=None, name="RfidManageOnly", permission_keys=["track_rfid.manage_tags"]
    )
    _user, no_view_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="noview@track-rfid-perm-test.example", role=no_view_role
    )
    await db.commit()
    no_view_headers = {"Authorization": f"Bearer {no_view_token}"}

    assert (await client.get("/api/v1/rfid/tags", headers=no_view_headers)).status_code == 403
    assert (await client.get("/api/v1/rfid/read-events", headers=no_view_headers)).status_code == 403
