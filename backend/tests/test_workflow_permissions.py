"""workflow.view / workflow.decide / workflow.manage_definitions gating on the real workflow
endpoints — a user missing the specific permission a route requires must be rejected (403).
Mirrors test_maintenance_permissions.py's shape. No module-gate test needed here — workflow is
always_on=True and its router has no require_module dependency (see
test_entitlements.py::test_require_module_no_ops_for_an_always_on_module, which already covers
the always_on mechanism generically)."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_setup_user(db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="WorkflowPermSetup", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email="setup@workflow-perm-test.example", role=role)


async def _make_role_with_only(db, tenant, *, permission_keys, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"OnlyRole-{email}", permission_keys=permission_keys)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return token


async def _ensure_approver_role(db) -> None:
    """_create_definition's step references this role by name — since tests don't run
    app.seed's sync_system_roles, it must be created explicitly first."""
    await make_role_with_permissions(db, tenant_id=None, name="Tenant Admin", permission_keys=_ALL_WORKFLOW_PERMS)


async def _create_definition(client, headers) -> dict:
    resp = await client.post(
        "/api/v1/workflow/definitions",
        json={
            "entity_type": "maintenance_ticket",
            "name": "Perm Test Definition",
            "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_manage_definitions_permission_gates_definition_and_step_writes(client, db):
    tenant = await make_tenant(db, subdomain="workflow-perm-manage-definitions")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    setup_headers = _headers(setup_token)

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["workflow.view"], email="viewonly@workflow-perm-test.example"
    )
    await db.commit()
    view_only_headers = _headers(view_only_token)

    create_resp = await client.post(
        "/api/v1/workflow/definitions",
        json={
            "entity_type": "maintenance_ticket",
            "name": "Denied",
            "steps": [{"sequence_order": 1, "approver_role_key": "Member"}],
        },
        headers=view_only_headers,
    )
    assert create_resp.status_code == 403

    definition = await _create_definition(client, setup_headers)

    patch_resp = await client.patch(
        f"/api/v1/workflow/definitions/{definition['id']}", json={"name": "Still denied"}, headers=view_only_headers
    )
    assert patch_resp.status_code == 403

    delete_resp = await client.delete(f"/api/v1/workflow/definitions/{definition['id']}", headers=view_only_headers)
    assert delete_resp.status_code == 403

    add_step_resp = await client.post(
        f"/api/v1/workflow/definitions/{definition['id']}/steps",
        json={"sequence_order": 2, "approver_role_key": "Member"},
        headers=view_only_headers,
    )
    assert add_step_resp.status_code == 403

    # workflow.view alone is still enough to read.
    read_resp = await client.get(f"/api/v1/workflow/definitions/{definition['id']}", headers=view_only_headers)
    assert read_resp.status_code == 200


async def test_manage_definitions_permission_gates_evaluate_and_cancel(client, db):
    tenant = await make_tenant(db, subdomain="workflow-perm-evaluate-cancel")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    setup_headers = _headers(setup_token)

    await _create_definition(client, setup_headers)

    decide_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["workflow.view", "workflow.decide"], email="decideonly@workflow-perm-test.example"
    )
    await db.commit()
    decide_only_headers = _headers(decide_only_token)

    evaluate_resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
        headers=decide_only_headers,
    )
    assert evaluate_resp.status_code == 403

    instance = (
        await client.post(
            "/api/v1/workflow/instances/evaluate",
            json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
            headers=setup_headers,
        )
    ).json()["data"]

    cancel_resp = await client.post(f"/api/v1/workflow/instances/{instance['id']}/cancel", headers=decide_only_headers)
    assert cancel_resp.status_code == 403


async def test_decide_permission_gates_approve_and_reject(client, db):
    tenant = await make_tenant(db, subdomain="workflow-perm-decide")
    setup_user, setup_token = await _make_setup_user(db, tenant)
    await db.commit()
    setup_headers = _headers(setup_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Decide perm test",
                "steps": [{"sequence_order": 1, "approver_user_id": str(setup_user.id)}],
            },
            headers=setup_headers,
        )
    ).json()["data"]
    assert definition is not None

    instance = (
        await client.post(
            "/api/v1/workflow/instances/evaluate",
            json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
            headers=setup_headers,
        )
    ).json()["data"]
    step_id = instance["steps"][0]["id"]

    view_only_token = await _make_role_with_only(
        db, tenant, permission_keys=["workflow.view"], email="viewonlydecide@workflow-perm-test.example"
    )
    await db.commit()
    view_only_headers = _headers(view_only_token)

    approve_resp = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/approve", headers=view_only_headers)
    assert approve_resp.status_code == 403

    reject_resp = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/reject", headers=view_only_headers)
    assert reject_resp.status_code == 403


async def test_view_permission_gates_listing(client, db):
    tenant = await make_tenant(db, subdomain="workflow-perm-view")
    await _make_setup_user(db, tenant)
    await db.commit()

    no_view_token = await _make_role_with_only(
        db, tenant, permission_keys=["workflow.decide"], email="noview@workflow-perm-test.example"
    )
    await db.commit()
    no_view_headers = _headers(no_view_token)

    assert (await client.get("/api/v1/workflow/definitions", headers=no_view_headers)).status_code == 403
    assert (await client.get("/api/v1/workflow/instances", headers=no_view_headers)).status_code == 403


async def test_notifications_endpoints_require_only_authentication_no_permission_key(client, db):
    tenant = await make_tenant(db, subdomain="workflow-perm-notifications-auth-only")
    no_perms_token = await _make_role_with_only(db, tenant, permission_keys=[], email="noperm@workflow-perm-test.example")
    await db.commit()

    resp = await client.get("/api/v1/workflow/notifications", headers=_headers(no_perms_token))
    assert resp.status_code == 200
