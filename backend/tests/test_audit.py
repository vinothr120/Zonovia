"""The audit module's router is read-only (GET /audit-logs); every write action across the
app calls core/audit.py::write_audit_log directly rather than going through an AuditService,
so this exercises the permission gate on the read side and confirms entries show up
end-to-end through the API (as opposed to just being present in the DB)."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


async def test_list_audit_logs_requires_permission(client, db):
    tenant = await make_tenant(db, subdomain="audit-permission")
    viewer_role = await make_role_with_permissions(db, tenant_id=None, name="AuditViewer", permission_keys=["audit_logs.view"])
    _viewer, viewer_token = await make_user_with_role(db, tenant_id=tenant.id, email="auditviewer@example.com", role=viewer_role)
    plain_role = await make_role_with_permissions(db, tenant_id=None, name="NoAuditPerm", permission_keys=[])
    _plain, plain_token = await make_user_with_role(db, tenant_id=tenant.id, email="noauditperm@example.com", role=plain_role)
    await db.commit()

    denied = await client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {plain_token}"})
    assert denied.status_code == 403

    allowed = await client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {viewer_token}"})
    assert allowed.status_code == 200


async def test_audit_log_records_actor_action_and_entity_for_a_real_write(client, db):
    """Exercises the audit trail end-to-end through a real write (user creation) rather than
    calling write_audit_log directly — confirms the whole path (service -> DB -> GET
    /audit-logs -> response shape) actually works, not just that the function was called."""
    tenant = await make_tenant(db, subdomain="audit-end-to-end")
    admin_role = await make_role_with_permissions(
        db, tenant_id=None, name="AuditEndToEndAdmin", permission_keys=["users.create", "audit_logs.view"]
    )
    admin_user, admin_token = await make_user_with_role(db, tenant_id=tenant.id, email="auditadmin@example.com", role=admin_role)
    await db.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post(
        "/api/v1/users", json={"email": "brandnew@example.com", "password": "Passw0rd!2026"}, headers=headers
    )
    assert create_resp.status_code == 201, create_resp.text
    new_user_id = create_resp.json()["data"]["id"]

    logs_resp = await client.get("/api/v1/audit-logs", headers=headers)
    assert logs_resp.status_code == 200
    entries = logs_resp.json()["data"]
    created_entry = next(e for e in entries if e["action"] == "user.created" and e["entity_id"] == new_user_id)
    assert created_entry["actor_user_id"] == str(admin_user.id)
    assert created_entry["entity_type"] == "user"
    assert created_entry["new_value"]["email"] == "brandnew@example.com"


async def test_audit_logs_are_scoped_to_tenant(client, db):
    tenant_a = await make_tenant(db, subdomain="audit-tenant-a")
    tenant_b = await make_tenant(db, subdomain="audit-tenant-b")

    role_a = await make_role_with_permissions(
        db, tenant_id=None, name="AuditTenantA", permission_keys=["users.create", "audit_logs.view"]
    )
    _admin_a, token_a = await make_user_with_role(db, tenant_id=tenant_a.id, email="admina@example.com", role=role_a)

    role_b = await make_role_with_permissions(db, tenant_id=None, name="AuditTenantB", permission_keys=["audit_logs.view"])
    _admin_b, token_b = await make_user_with_role(db, tenant_id=tenant_b.id, email="adminb@example.com", role=role_b)
    await db.commit()

    await client.post(
        "/api/v1/users",
        json={"email": "tenanta-user@example.com", "password": "Passw0rd!2026"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    tenant_b_logs = await client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {token_b}"})
    actions = [e["action"] for e in tenant_b_logs.json()["data"]]
    assert "user.created" not in actions
