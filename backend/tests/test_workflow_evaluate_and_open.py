"""WorkflowService.evaluate_and_maybe_open: condition matching (including the "missing context
key or type mismatch never raises, just never matches" guarantee via _condition_matches), the
duplicate-open guard, and per-group notification creation for every approver."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


async def _make_user(db, tenant, *, email="user@workflow-eval-test.example", permission_keys=None):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"WorkflowEvalUser-{email}", permission_keys=permission_keys or _ALL_WORKFLOW_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def _ensure_approver_role(db) -> None:
    """_create_definition's default step references this role by name — since tests don't run
    app.seed's sync_system_roles, it must be created explicitly first."""
    await make_role_with_permissions(db, tenant_id=None, name="Tenant Admin", permission_keys=_ALL_WORKFLOW_PERMS)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_definition(client, headers, **overrides) -> dict:
    body = {
        "entity_type": "maintenance_ticket",
        "name": "Approval needed",
        "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
    }
    body.update(overrides)
    resp = await client.post("/api/v1/workflow/definitions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_evaluate_with_no_matching_definition_returns_null(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-no-match")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = _headers(token)

    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "some_unconfigured_entity", "entity_id": str(uuid.uuid4()), "context": {}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is None


async def test_evaluate_condition_gt_matches_and_opens_instance(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-gt-match")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers, condition_attribute="cost", condition_operator="gt", condition_value=500)

    entity_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": entity_id, "context": {"cost": 900}},
        headers=headers,
    )
    assert resp.status_code == 200
    instance = resp.json()["data"]
    assert instance is not None
    assert instance["status"] == "pending"
    assert instance["entity_id"] == entity_id
    assert len(instance["steps"]) == 1
    assert instance["current_sequence_order"] == 1


async def test_evaluate_condition_gt_below_threshold_does_not_match(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-gt-below")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers, condition_attribute="cost", condition_operator="gt", condition_value=500)

    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {"cost": 100}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is None


async def test_evaluate_missing_context_key_never_matches(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-missing-key")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers, condition_attribute="cost", condition_operator="gt", condition_value=500)

    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {"unrelated": "value"}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is None


async def test_evaluate_type_mismatch_never_raises_just_does_not_match(client, db):
    """actual="expensive" (str) compared with > 500 (int) raises TypeError inside
    _condition_matches — must be caught and treated as no-match, not surfaced as a 500."""
    tenant = await make_tenant(db, subdomain="workflow-eval-type-mismatch")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers, condition_attribute="cost", condition_operator="gt", condition_value=500)

    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {"cost": "expensive"}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is None


async def test_evaluate_no_condition_always_matches(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-no-condition")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)

    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is not None


async def test_evaluate_duplicate_open_guard_returns_null_second_time(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-duplicate-guard")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    entity_id = str(uuid.uuid4())

    first = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": entity_id, "context": {}},
        headers=headers,
    )
    assert first.json()["data"] is not None

    second = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": entity_id, "context": {}},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["data"] is None


async def test_evaluate_notifies_every_approver_in_the_first_group(client, db):
    tenant = await make_tenant(db, subdomain="workflow-eval-notify-group")
    setup_user, setup_token = await _make_user(db, tenant, email="setup@workflow-eval-notify.example")

    approver_role = await make_role_with_permissions(
        db, tenant_id=None, name="TicketApprovers", permission_keys=_ALL_WORKFLOW_PERMS
    )
    approver_one, approver_one_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="approver1@workflow-eval-notify.example", role=approver_role
    )
    approver_two, approver_two_token = await make_user_with_role(
        db, tenant_id=tenant.id, email="approver2@workflow-eval-notify.example", role=approver_role
    )
    await db.commit()
    setup_headers = _headers(setup_token)

    await _create_definition(client, setup_headers, steps=[{"sequence_order": 1, "approver_role_key": "TicketApprovers"}])

    entity_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": entity_id, "context": {}},
        headers=setup_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] is not None

    for token in (approver_one_token, approver_two_token):
        notif_resp = await client.get("/api/v1/workflow/notifications", headers=_headers(token))
        assert notif_resp.status_code == 200
        notifications = notif_resp.json()["data"]
        assert any(n["type"] == "approval_pending" and n["entity_id"] == entity_id for n in notifications)
