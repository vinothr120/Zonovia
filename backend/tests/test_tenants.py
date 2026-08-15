"""app.tenants.router's platform-level tenant CRUD (/platform/tenants) — gated by BOTH
require_platform_admin() (the JWT's platform_admin claim) and require_permission
("platform.manage_tenants") (the caller's actual effective grants), per app/tenants/router.py."""

from app.core.security import create_access_token
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def _make_platform_admin(db, tenant):
    role = await make_role_with_permissions(
        db, tenant_id=None, name="PlatformAdminForTenantsTest", permission_keys=["platform.manage_tenants"]
    )
    user, _ = await make_user_with_role(db, tenant_id=tenant.id, email="platformadmin@tenants-test.example", role=role)
    token = create_access_token(user_id=user.id, tenant_id=tenant.id, is_platform_admin=True)
    return user, token


async def test_non_platform_admin_cannot_create_a_tenant(client, db):
    tenant = await make_tenant(db, subdomain="tenants-router-guard")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="NotPlatformAdmin", permission_keys=["platform.manage_tenants"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="notplatform@tenants-test.example", role=role)
    await db.commit()

    # Holds the permission but the JWT itself doesn't carry platform_admin=True — both gates
    # must pass, not just one.
    resp = await client.post(
        "/api/v1/platform/tenants",
        json={"name": "Should Fail Co", "subdomain": "should-fail-co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_platform_admin_can_create_and_list_tenants(client, db):
    tenant = await make_tenant(db, subdomain="tenants-router-create")
    _admin, token = await _make_platform_admin(db, tenant)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await client.post(
        "/api/v1/platform/tenants", json={"name": "Contoso Ltd", "subdomain": "contoso-ltd"}, headers=headers
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()["data"]
    assert created["subdomain"] == "contoso-ltd"
    assert created["subscription_tier"] == "basic"

    list_resp = await client.get("/api/v1/platform/tenants", headers=headers)
    assert list_resp.status_code == 200
    subdomains = {t["subdomain"] for t in list_resp.json()["data"]}
    assert "contoso-ltd" in subdomains


async def test_creating_a_tenant_with_a_duplicate_subdomain_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="tenants-router-dup")
    _admin, token = await _make_platform_admin(db, tenant)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post("/api/v1/platform/tenants", json={"name": "Fabrikam", "subdomain": "fabrikam"}, headers=headers)
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/v1/platform/tenants", json={"name": "Fabrikam Two", "subdomain": "fabrikam"}, headers=headers
    )
    assert duplicate.status_code == 409
