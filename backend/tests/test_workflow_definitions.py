"""WorkflowDefinition/ApprovalStepDefinition CRUD and every create/update guard clause: XOR
violation, zero-step create, delete-last-step, unknown role/user, partial condition, unsupported
condition_operator, and update_step's deliberate both-fields-together XOR PATCH deviation."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


async def _make_user(db, tenant, *, email="user@workflow-def-test.example", permission_keys=None):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"WorkflowDefUser-{email}", permission_keys=permission_keys or _ALL_WORKFLOW_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def _ensure_approver_role(db) -> None:
    """The default step in _one_step_body references this role by name — since tests don't
    run app.seed's sync_system_roles, it must be created explicitly first."""
    await make_role_with_permissions(db, tenant_id=None, name="ApproverRole", permission_keys=_ALL_WORKFLOW_PERMS)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _one_step_body(**overrides) -> dict:
    body = {
        "entity_type": "maintenance_ticket",
        "name": "High cost tickets need approval",
        "steps": [{"sequence_order": 1, "approver_role_key": "ApproverRole"}],
    }
    body.update(overrides)
    return body


async def test_create_definition_requires_at_least_one_step(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-zero-steps")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json={"entity_type": "maintenance_ticket", "name": "No steps", "steps": []},
        headers=_headers(token),
    )
    assert resp.status_code == 422


async def test_create_definition_step_xor_violation_both_set_rejected(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-xor-both")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(
            steps=[
                {
                    "sequence_order": 1,
                    "approver_user_id": str(uuid.uuid4()),
                    "approver_role_key": "Tenant Admin",
                }
            ]
        ),
        headers=_headers(token),
    )
    assert resp.status_code == 422


async def test_create_definition_step_xor_violation_neither_set_rejected(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-xor-neither")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(steps=[{"sequence_order": 1}]),
        headers=_headers(token),
    )
    assert resp.status_code == 422


async def test_create_definition_unknown_approver_user_returns_404(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-unknown-user")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(steps=[{"sequence_order": 1, "approver_user_id": str(uuid.uuid4())}]),
        headers=_headers(token),
    )
    assert resp.status_code == 404


async def test_create_definition_unknown_approver_role_returns_404(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-unknown-role")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(steps=[{"sequence_order": 1, "approver_role_key": "Not A Real Role"}]),
        headers=_headers(token),
    )
    assert resp.status_code == 404


async def test_create_definition_partial_condition_rejected(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-partial-condition")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(condition_attribute="cost"),
        headers=_headers(token),
    )
    assert resp.status_code == 422


async def test_create_definition_unsupported_condition_operator_rejected(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-bad-operator")
    _user, token = await _make_user(db, tenant)
    await db.commit()

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(condition_attribute="cost", condition_operator="between", condition_value=100),
        headers=_headers(token),
    )
    assert resp.status_code == 422


async def test_create_definition_happy_path_then_list_steps(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-happy-path")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    resp = await client.post(
        "/api/v1/workflow/definitions",
        json=_one_step_body(condition_attribute="cost", condition_operator="gt", condition_value=500),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    definition = resp.json()["data"]
    assert definition["entity_type"] == "maintenance_ticket"
    assert definition["is_active"] is True
    assert definition["condition_operator"] == "gt"

    steps_resp = await client.get(f"/api/v1/workflow/definitions/{definition['id']}/steps", headers=headers)
    assert steps_resp.status_code == 200
    steps = steps_resp.json()["data"]
    assert len(steps) == 1
    assert steps[0]["approver_role_key"] == "ApproverRole"


async def test_update_definition_patches_name_and_is_active(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-update")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    definition = (await client.post("/api/v1/workflow/definitions", json=_one_step_body(), headers=headers)).json()["data"]

    resp = await client.patch(
        f"/api/v1/workflow/definitions/{definition['id']}",
        json={"name": "Renamed", "is_active": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()["data"]
    assert updated["name"] == "Renamed"
    assert updated["is_active"] is False


async def test_delete_definition_soft_deletes(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-delete")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    definition = (await client.post("/api/v1/workflow/definitions", json=_one_step_body(), headers=headers)).json()["data"]

    delete_resp = await client.delete(f"/api/v1/workflow/definitions/{definition['id']}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/workflow/definitions/{definition['id']}", headers=headers)
    assert get_resp.status_code == 404


async def test_delete_step_blocks_removing_the_last_remaining_step(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-delete-last-step")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await make_role_with_permissions(db, tenant_id=None, name="SecondApproverRole", permission_keys=_ALL_WORKFLOW_PERMS)
    await db.commit()
    headers = _headers(token)

    definition = (await client.post("/api/v1/workflow/definitions", json=_one_step_body(), headers=headers)).json()["data"]
    steps = (await client.get(f"/api/v1/workflow/definitions/{definition['id']}/steps", headers=headers)).json()["data"]
    only_step_id = steps[0]["id"]

    # Add a second step so the definition has two, then delete one — should succeed.
    second = (
        await client.post(
            f"/api/v1/workflow/definitions/{definition['id']}/steps",
            json={"sequence_order": 2, "approver_role_key": "SecondApproverRole"},
            headers=headers,
        )
    ).json()["data"]

    first_delete = await client.delete(f"/api/v1/workflow/definitions/{definition['id']}/steps/{only_step_id}", headers=headers)
    assert first_delete.status_code == 204

    # Now only `second` remains — deleting it must be blocked.
    last_delete = await client.delete(f"/api/v1/workflow/definitions/{definition['id']}/steps/{second['id']}", headers=headers)
    assert last_delete.status_code == 409


async def test_update_step_rejects_only_one_of_the_xor_pair_sent(client, db):
    """The deliberate both-fields-together deviation: sending only approver_user_id (without
    approver_role_key in the same PATCH body) must be rejected, even though approver_role_key
    would ordinarily be optional."""
    tenant = await make_tenant(db, subdomain="workflow-def-update-step-xor")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    definition = (await client.post("/api/v1/workflow/definitions", json=_one_step_body(), headers=headers)).json()["data"]
    steps = (await client.get(f"/api/v1/workflow/definitions/{definition['id']}/steps", headers=headers)).json()["data"]
    step_id = steps[0]["id"]

    resp = await client.patch(
        f"/api/v1/workflow/definitions/{definition['id']}/steps/{step_id}",
        json={"approver_user_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_update_step_switches_role_to_user_when_both_fields_sent_together(client, db):
    tenant = await make_tenant(db, subdomain="workflow-def-update-step-switch")
    setup_user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    definition = (await client.post("/api/v1/workflow/definitions", json=_one_step_body(), headers=headers)).json()["data"]
    steps = (await client.get(f"/api/v1/workflow/definitions/{definition['id']}/steps", headers=headers)).json()["data"]
    step_id = steps[0]["id"]

    resp = await client.patch(
        f"/api/v1/workflow/definitions/{definition['id']}/steps/{step_id}",
        json={"approver_user_id": str(setup_user.id), "approver_role_key": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()["data"]
    assert updated["approver_user_id"] == str(setup_user.id)
    assert updated["approver_role_key"] is None
