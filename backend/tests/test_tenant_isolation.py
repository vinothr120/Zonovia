"""A user in one tenant must never be able to read or write another tenant's data — not even
by guessing a valid ID. This tier exercises the APPLICATION-LAYER half of the guarantee
(TenantScopedRepository's explicit tenant_id filtering, run here against SQLite).

Postgres Row-Level Security is the other, independent half of the guarantee and can only be
verified against real Postgres — see test_tenant_isolation_postgres.py, which requires
`docker compose up -d postgres` and is marked `@pytest.mark.postgres`.
"""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def test_user_get_by_id_is_scoped_to_own_tenant(client, db):
    tenant_a = await make_tenant(db, subdomain="tenant-a-user")
    tenant_b = await make_tenant(db, subdomain="tenant-b-user")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="IsolationAdmin", permission_keys=["users.view"])
    _admin_a, token_a = await make_user_with_role(db, tenant_id=tenant_a.id, email="admin@tenant-a-user.test", role=admin_role)
    user_b, _token_b = await make_user_with_role(db, tenant_id=tenant_b.id, email="admin@tenant-b-user.test", role=admin_role)
    await db.commit()

    # Tenant A's admin can read their own tenant's users...
    own = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token_a}"})
    assert own.status_code == 200

    # ...but not tenant B's user by ID, even though they have the same "users.view" permission —
    # TenantScopedRepository.get_by_id filters by tenant_id before checking existence at all.
    other = await client.get(f"/api/v1/users/{user_b.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert other.status_code == 404  # not 403 — existence in another tenant is not revealed


async def test_user_list_is_scoped_to_own_tenant(client, db):
    tenant_a = await make_tenant(db, subdomain="tenant-a-list")
    tenant_b = await make_tenant(db, subdomain="tenant-b-list")
    admin_role = await make_role_with_permissions(db, tenant_id=None, name="IsolationListAdmin", permission_keys=["users.view"])
    _, token_a = await make_user_with_role(db, tenant_id=tenant_a.id, email="a@tenant-a-list.test", role=admin_role)
    _, token_b = await make_user_with_role(db, tenant_id=tenant_b.id, email="b@tenant-b-list.test", role=admin_role)
    await db.commit()

    response = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 200
    emails = {u["email"] for u in response.json()["data"]}
    assert "a@tenant-a-list.test" in emails
    assert "b@tenant-b-list.test" not in emails


async def test_tenant_settings_are_scoped_to_own_tenant(client, db):
    tenant_a = await make_tenant(db, subdomain="tenant-a-settings")
    tenant_b = await make_tenant(db, subdomain="tenant-b-settings")
    admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="IsolationSettingsAdmin", permission_keys=["tenants.view_settings", "tenants.manage_settings"]
    )
    _, token_a = await make_user_with_role(db, tenant_id=tenant_a.id, email="a@tenant-a-settings.test", role=admin_role)
    _, token_b = await make_user_with_role(db, tenant_id=tenant_b.id, email="b@tenant-b-settings.test", role=admin_role)
    await db.commit()

    put_resp = await client.put(
        "/api/v1/tenants/me/settings/branding.theme",
        json={"value": "dark"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert put_resp.status_code == 200, put_resp.text

    # Tenant B never sees tenant A's setting, even at the identical key.
    get_resp = await client.get("/api/v1/tenants/me/settings/branding.theme", headers={"Authorization": f"Bearer {token_b}"})
    assert get_resp.status_code == 404


async def test_missing_permission_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="no-perms")
    powerless_role = await make_role_with_permissions(db, tenant_id=None, name="Powerless", permission_keys=[])
    _, token = await make_user_with_role(db, tenant_id=tenant.id, email="nobody@no-perms.test", role=powerless_role)
    await db.commit()

    response = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_missing_token_is_rejected(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
