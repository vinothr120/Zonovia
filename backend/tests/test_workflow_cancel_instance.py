"""ApprovalInstance cancellation: only from 'pending', bulk-skips every remaining pending step,
notifies requested_by. Admin-reserved via workflow.manage_definitions — no self-service
cancel-your-own-request path this round."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]
_DECIDE_ONLY_PERMS = ["workflow.view", "workflow.decide"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email, *, permission_keys=None):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"CancelUser-{email}", permission_keys=permission_keys or _ALL_WORKFLOW_PERMS
    )
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def test_cancel_from_pending_bulk_skips_steps_and_notifies_requester(client, db):
    tenant = await make_tenant(db, subdomain="workflow-cancel-happy")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-cancel-test.example")
    approver, _approver_token = await _make_user(db, tenant, "approver@workflow-cancel-test.example")
    admin, admin_token = await _make_user(db, tenant, "admin@workflow-cancel-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Cancellable flow",
                "steps": [{"sequence_order": 1, "approver_user_id": str(approver.id)}],
            },
            headers=requester_headers,
        )
    ).json()["data"]
    assert definition is not None

    entity_id = str(uuid.uuid4())
    instance = (
        await client.post(
            "/api/v1/workflow/instances/evaluate",
            json={"entity_type": "maintenance_ticket", "entity_id": entity_id, "context": {}},
            headers=requester_headers,
        )
    ).json()["data"]

    cancel_resp = await client.post(f"/api/v1/workflow/instances/{instance['id']}/cancel", headers=_headers(admin_token))
    assert cancel_resp.status_code == 200, cancel_resp.text
    cancelled = cancel_resp.json()["data"]
    assert cancelled["status"] == "cancelled"
    assert cancelled["current_sequence_order"] is None
    assert all(s["status"] == "skipped" for s in cancelled["steps"])

    requester_notifications = (await client.get("/api/v1/workflow/notifications", headers=requester_headers)).json()["data"]
    assert any(n["type"] == "approval_resolved" and n["entity_id"] == entity_id for n in requester_notifications)


async def test_cancel_rejected_when_already_resolved(client, db):
    tenant = await make_tenant(db, subdomain="workflow-cancel-terminal")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-cancel-terminal.example")
    approver, approver_token = await _make_user(db, tenant, "approver@workflow-cancel-terminal.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Cancel after resolve",
                "steps": [{"sequence_order": 1, "approver_user_id": str(approver.id)}],
            },
            headers=requester_headers,
        )
    ).json()["data"]
    assert definition is not None

    instance = (
        await client.post(
            "/api/v1/workflow/instances/evaluate",
            json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
            headers=requester_headers,
        )
    ).json()["data"]
    step_id = instance["steps"][0]["id"]
    approve_resp = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/approve", headers=_headers(approver_token))
    assert approve_resp.status_code == 200

    cancel_resp = await client.post(f"/api/v1/workflow/instances/{instance['id']}/cancel", headers=requester_headers)
    assert cancel_resp.status_code == 409


async def test_cancel_requires_manage_definitions_permission(client, db):
    tenant = await make_tenant(db, subdomain="workflow-cancel-permission-guard")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-cancel-perm.example")
    approver, approver_token = await _make_user(db, tenant, "approver@workflow-cancel-perm.example")
    decide_only, decide_only_token = await _make_user(
        db, tenant, "decideonly@workflow-cancel-perm.example", permission_keys=_DECIDE_ONLY_PERMS
    )
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Cancel permission guard",
                "steps": [{"sequence_order": 1, "approver_user_id": str(approver.id)}],
            },
            headers=requester_headers,
        )
    ).json()["data"]
    assert definition is not None

    instance = (
        await client.post(
            "/api/v1/workflow/instances/evaluate",
            json={"entity_type": "maintenance_ticket", "entity_id": str(uuid.uuid4()), "context": {}},
            headers=requester_headers,
        )
    ).json()["data"]

    resp = await client.post(f"/api/v1/workflow/instances/{instance['id']}/cancel", headers=_headers(decide_only_token))
    assert resp.status_code == 403
