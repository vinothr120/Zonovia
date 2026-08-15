"""Custom role creation and permission-catalog endpoints: a tenant admin can define a role
beyond the seeded system bundles, edit its permission set, and see the change take effect for
users already holding that role without waiting out the permission cache's TTL."""

from tests.conftest import make_permission, make_role_with_permissions, make_tenant, make_user_with_role


async def test_create_custom_role_and_assign_it_grants_its_permissions(client, db):
    tenant = await make_tenant(db, subdomain="role-create")

    admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="RoleAdmin", permission_keys=["roles.manage", "roles.view"]
    )
    _admin_user, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="roleadmin@example.com", role=admin_role)

    staff_role = await make_role_with_permissions(db, tenant_id=None, name="Staff", permission_keys=[])
    staff_user, staff_token = await make_user_with_role(db, tenant_id=tenant.id, email="staff@example.com", role=staff_role)
    await make_permission(db, "users.view")
    await db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post(
        "/api/v1/roles", json={"name": "Custom Auditor", "permission_keys": ["users.view"]}, headers=headers
    )
    assert create_resp.status_code == 201, create_resp.text
    role_data = create_resp.json()["data"]
    assert role_data["is_system_role"] is False
    assert role_data["permission_keys"] == ["users.view"]
    role_id = role_data["id"]

    get_resp = await client.get(f"/api/v1/roles/{role_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["permission_keys"] == ["users.view"]

    assign_resp = await client.post(
        f"/api/v1/users/{staff_user.id}/roles", json={"role_id": role_id, "scope_type": "tenant"}, headers=headers
    )
    assert assign_resp.status_code == 201, assign_resp.text

    me_resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert "users.view" in me_resp.json()["data"]["permissions"]


async def test_system_roles_cannot_have_permissions_edited(client, db):
    tenant = await make_tenant(db, subdomain="role-system-protect")
    admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="SysProtectAdmin", permission_keys=["roles.manage", "roles.view"]
    )
    _admin_user, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="sysadmin@example.com", role=admin_role)
    await db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    roles_resp = await client.get("/api/v1/roles", headers=headers)
    system_role = next(r for r in roles_resp.json()["data"] if r["is_system_role"])

    resp = await client.put(
        f"/api/v1/roles/{system_role['id']}/permissions", json={"permission_keys": ["users.view"]}, headers=headers
    )
    assert resp.status_code == 422


async def test_updating_role_permissions_invalidates_cache_for_assigned_users(client, db):
    tenant = await make_tenant(db, subdomain="role-cache-invalidate")
    admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="CacheAdmin", permission_keys=["roles.manage", "roles.view"]
    )
    _admin_user, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="cacheadmin@example.com", role=admin_role)

    custom_role = await make_role_with_permissions(db, tenant_id=tenant.id, name="Evolving", permission_keys=["users.view"])
    staff_user, staff_token = await make_user_with_role(db, tenant_id=tenant.id, email="evolving@example.com", role=custom_role)
    await make_permission(db, "audit_logs.view")
    await db.commit()

    staff_headers = {"Authorization": f"Bearer {staff_token}"}
    before = await client.get("/api/v1/users/me", headers=staff_headers)
    assert before.json()["data"]["permissions"] == ["users.view"]

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    update_resp = await client.put(
        f"/api/v1/roles/{custom_role.id}/permissions", json={"permission_keys": ["audit_logs.view"]}, headers=admin_headers
    )
    assert update_resp.status_code == 200, update_resp.text

    after = await client.get("/api/v1/users/me", headers=staff_headers)
    assert after.json()["data"]["permissions"] == ["audit_logs.view"]


async def test_list_permissions_returns_the_catalog(client, db):
    tenant = await make_tenant(db, subdomain="permissions-catalog")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="CatalogAdmin", permission_keys=["roles.view"])
    _admin_user, admin_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="catalogadmin@example.com", role=admin_role
    )
    await make_permission(db, "users.view")
    await make_permission(db, "audit_logs.view")
    await db.commit()

    resp = await client.get("/api/v1/permissions", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()["data"]}
    assert "users.view" in keys
    assert "audit_logs.view" in keys
    assert "roles.view" in keys
