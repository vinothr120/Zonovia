"""app.tenants's Configuration deliverable — a flat, schemaless tenant-level key -> JSON
store (/tenants/me/settings). Confirms CRUD + the audit-logging convention together (proves
Configuration and the audit convention work end-to-end, matching the implementation plan's
verification step 10)."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def test_upsert_and_read_back_a_setting(client, db):
    tenant = await make_tenant(db, subdomain="settings-crud")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="SettingsCrudAdmin", permission_keys=["tenants.view_settings", "tenants.manage_settings"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="settingsadmin@example.com", role=role)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    put_resp = await client.put("/api/v1/tenants/me/settings/notifications.digest_enabled", json={"value": True}, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["data"]["value"] is True

    get_resp = await client.get("/api/v1/tenants/me/settings/notifications.digest_enabled", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["value"] is True

    list_resp = await client.get("/api/v1/tenants/me/settings", headers=headers)
    assert list_resp.status_code == 200
    keys = {s["key"] for s in list_resp.json()["data"]}
    assert "notifications.digest_enabled" in keys


async def test_updating_a_setting_overwrites_the_previous_value(client, db):
    tenant = await make_tenant(db, subdomain="settings-overwrite")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="SettingsOverwriteAdmin", permission_keys=["tenants.view_settings", "tenants.manage_settings"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="overwriteadmin@example.com", role=role)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    await client.put("/api/v1/tenants/me/settings/theme.color", json={"value": "blue"}, headers=headers)
    second = await client.put("/api/v1/tenants/me/settings/theme.color", json={"value": "green"}, headers=headers)
    assert second.status_code == 200
    assert second.json()["data"]["value"] == "green"

    get_resp = await client.get("/api/v1/tenants/me/settings/theme.color", headers=headers)
    assert get_resp.json()["data"]["value"] == "green"


async def test_getting_an_unknown_setting_key_is_404(client, db):
    tenant = await make_tenant(db, subdomain="settings-404")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="Settings404Admin", permission_keys=["tenants.view_settings"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="settings404@example.com", role=role)
    await db.commit()

    resp = await client.get("/api/v1/tenants/me/settings/does.not.exist", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


async def test_upserting_a_setting_requires_manage_permission(client, db):
    tenant = await make_tenant(db, subdomain="settings-perm-guard")
    view_only_role = await make_role_with_permissions(
        db, tenant_id=None, name="SettingsViewOnly", permission_keys=["tenants.view_settings"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="viewonly@example.com", role=view_only_role)
    await db.commit()

    resp = await client.put(
        "/api/v1/tenants/me/settings/some.key", json={"value": "x"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


async def test_upserting_a_setting_writes_an_audit_log_entry(client, db):
    tenant = await make_tenant(db, subdomain="settings-audit")
    role = await make_role_with_permissions(
        db,
        tenant_id=None,
        name="SettingsAuditAdmin",
        permission_keys=["tenants.view_settings", "tenants.manage_settings", "audit_logs.view"],
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="settingsaudit@example.com", role=role)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    put_resp = await client.put("/api/v1/tenants/me/settings/feature.beta", json={"value": "on"}, headers=headers)
    assert put_resp.status_code == 200

    logs_resp = await client.get("/api/v1/audit-logs", headers=headers)
    actions = [e["action"] for e in logs_resp.json()["data"]]
    assert "tenant_setting.upserted" in actions
