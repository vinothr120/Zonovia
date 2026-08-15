"""app.users.service's user CRUD and role assign/revoke, including the guard against a
non-platform-admin escalating themselves to a system role (Platform Admin) via roles.manage
alone — see UserService.assign_role and docs/authorization.md."""

from app.core.security import create_access_token
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def test_create_user_requires_permission_and_rejects_duplicate_email(client, db):
    tenant = await make_tenant(db, subdomain="user-create")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="UserCreator", permission_keys=["users.create"])
    _admin, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="usercreator@example.com", role=admin_role)
    plain_role = await make_role_with_permissions(db, tenant_id=None, name="NoUserCreatePerm", permission_keys=[])
    _plain, plain_token = await make_user_with_role(db, tenant_id=tenant.id, email="nocreateperm@example.com", role=plain_role)
    await db.commit()

    denied = await client.post(
        "/api/v1/users",
        json={"email": "new1@example.com", "password": "Passw0rd!2026"},
        headers={"Authorization": f"Bearer {plain_token}"},
    )
    assert denied.status_code == 403

    headers = {"Authorization": f"Bearer {admin_token}"}
    created = await client.post("/api/v1/users", json={"email": "new1@example.com", "password": "Passw0rd!2026"}, headers=headers)
    assert created.status_code == 201, created.text

    duplicate = await client.post(
        "/api/v1/users", json={"email": "new1@example.com", "password": "Passw0rd!2026"}, headers=headers
    )
    assert duplicate.status_code == 409


async def test_get_me_returns_effective_permissions_and_platform_admin_flag(client, db):
    tenant = await make_tenant(db, subdomain="user-me")
    role = await make_role_with_permissions(db, tenant_id=None, name="MeRole", permission_keys=["users.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="meuser@example.com", role=role)
    await db.commit()

    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_platform_admin"] is False
    assert "users.view" in data["permissions"]


async def test_list_users_requires_permission(client, db):
    tenant = await make_tenant(db, subdomain="user-list")
    viewer_role = await make_role_with_permissions(db, tenant_id=None, name="UserViewer", permission_keys=["users.view"])
    _viewer, viewer_token = await make_user_with_role(db, tenant_id=tenant.id, email="userviewer@example.com", role=viewer_role)
    plain_role = await make_role_with_permissions(db, tenant_id=None, name="NoUserViewPerm", permission_keys=[])
    _plain, plain_token = await make_user_with_role(db, tenant_id=tenant.id, email="nouserviewperm@example.com", role=plain_role)
    await db.commit()

    denied = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {plain_token}"})
    assert denied.status_code == 403

    allowed = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {viewer_token}"})
    assert allowed.status_code == 200
    assert len(allowed.json()["data"]) >= 2  # at least the viewer and the plain-role user


async def test_assign_and_revoke_custom_role(client, db):
    tenant = await make_tenant(db, subdomain="user-role-assign")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="RoleAssignAdmin", permission_keys=["roles.manage"])
    _admin, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="roleassignadmin@example.com", role=admin_role)
    custom_role = await make_role_with_permissions(
        db, tenant_id=tenant.id, name="CustomStaff", permission_keys=["audit_logs.view"]
    )
    target_role = await make_role_with_permissions(db, tenant_id=None, name="TargetRole", permission_keys=[])
    target_user, target_token = await make_user_with_role(db, tenant_id=tenant.id, email="target@example.com", role=target_role)
    await db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    assign_resp = await client.post(
        f"/api/v1/users/{target_user.id}/roles", json={"role_id": str(custom_role.id), "scope_type": "tenant"}, headers=headers
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assignment_id = assign_resp.json()["data"]["id"]

    me_after_assign = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {target_token}"})
    assert "audit_logs.view" in me_after_assign.json()["data"]["permissions"]

    revoke_resp = await client.delete(f"/api/v1/users/{target_user.id}/roles/{assignment_id}", headers=headers)
    assert revoke_resp.status_code == 204

    me_after_revoke = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {target_token}"})
    assert "audit_logs.view" not in me_after_revoke.json()["data"]["permissions"]


async def test_non_platform_admin_cannot_grant_a_system_role(client, db):
    """roles.manage alone (held by any Tenant Admin) must not be enough to assign a system
    role (e.g. Platform Admin) to anyone, including the actor themselves."""
    tenant = await make_tenant(db, subdomain="user-role-escalation")
    tenant_admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="EscalationTenantAdmin", permission_keys=["roles.manage"]
    )
    _admin, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="escadmin@example.com", role=tenant_admin_role)

    platform_admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="Platform Admin", permission_keys=["platform.manage_tenants"]
    )
    plain_role = await make_role_with_permissions(db, tenant_id=None, name="EscalationTarget", permission_keys=[])
    target_user, _target_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="esctarget@example.com", role=plain_role
    )
    await db.commit()

    resp = await client.post(
        f"/api/v1/users/{target_user.id}/roles",
        json={"role_id": str(platform_admin_role.id), "scope_type": "tenant"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403, resp.text


async def test_platform_admin_can_grant_a_system_role(client, db):
    tenant = await make_tenant(db, subdomain="user-role-platform-grant")
    platform_admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="Platform Admin Grantable", permission_keys=["platform.manage_tenants"]
    )
    plain_role = await make_role_with_permissions(db, tenant_id=None, name="PlatformGrantTarget", permission_keys=[])
    target_user, _target_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="platformtarget@example.com", role=plain_role
    )
    await db.commit()

    # A platform-admin token, bypassing login — same pattern test_security.py already uses
    # to construct a token carrying the platform_admin claim directly.
    platform_role = await make_role_with_permissions(
        db, tenant_id=None, name="PlatformOperator", permission_keys=["roles.manage"]
    )
    platform_user, _ = await make_user_with_role(db, tenant_id=tenant.id, email="platformop@example.com", role=platform_role)
    await db.commit()
    platform_token = create_access_token(user_id=platform_user.id, tenant_id=tenant.id, is_platform_admin=True)

    resp = await client.post(
        f"/api/v1/users/{target_user.id}/roles",
        json={"role_id": str(platform_admin_role.id), "scope_type": "tenant"},
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert resp.status_code == 201, resp.text


async def test_roles_list_marks_system_roles_not_grantable_for_non_platform_admin(client, db):
    tenant = await make_tenant(db, subdomain="user-role-grantable-flag")
    role = await make_role_with_permissions(db, tenant_id=None, name="GrantableFlagRole", permission_keys=["roles.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="grantableflag@example.com", role=role)
    await make_role_with_permissions(db, tenant_id=tenant.id, name="GrantableFlagCustomRole", permission_keys=[])
    await db.commit()

    resp = await client.get("/api/v1/roles", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    roles = resp.json()["data"]
    system_roles = [r for r in roles if r["is_system_role"]]
    assert system_roles  # the seeded-in-this-test system roles above should show up
    assert all(r["grantable"] is False for r in system_roles)

    custom = next(r for r in roles if not r["is_system_role"])
    assert custom["grantable"] is True


async def test_assign_role_with_non_tenant_scope_is_rejected(client, db):
    """Phase 0 only implements tenant-wide role scope — see UserRole's docstring."""
    tenant = await make_tenant(db, subdomain="user-role-scope-guard")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="ScopeGuardAdmin", permission_keys=["roles.manage"])
    _admin, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="scopeguard@example.com", role=admin_role)
    target_role = await make_role_with_permissions(db, tenant_id=None, name="ScopeGuardTarget", permission_keys=[])
    target_user, _ = await make_user_with_role(db, tenant_id=tenant.id, email="scopeguardtarget@example.com", role=target_role)
    await db.commit()

    resp = await client.post(
        f"/api/v1/users/{target_user.id}/roles",
        json={"role_id": str(target_role.id), "scope_type": "school"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422
