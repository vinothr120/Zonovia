"""Two-layer decision authorization: the router gates /approve and /reject on the broad
workflow.decide permission (most roles hold it), but the service independently checks the
actor is the step's actual assignee — by user id match, or by membership in the assigned role —
and raises PermissionDeniedError (403) if not. Also covers the already-decided 409 distinct
from the wrong-actor 403."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email, *, role=None):
    if role is None:
        role = await make_role_with_permissions(db, tenant_id=None, name=f"AuthUser-{email}", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def test_user_assigned_step_rejects_a_different_user_holding_decide_permission(client, db):
    tenant = await make_tenant(db, subdomain="workflow-auth-user-assigned")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-auth-test.example")
    real_assignee, real_assignee_token = await _make_user(db, tenant, "assignee@workflow-auth-test.example")
    bystander, bystander_token = await _make_user(db, tenant, "bystander@workflow-auth-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Single user-assigned step",
                "steps": [{"sequence_order": 1, "approver_user_id": str(real_assignee.id)}],
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

    # Holds workflow.decide, but is not the assignee — must be a 403 from the service layer,
    # not the router's broad permission gate.
    wrong_actor = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/approve", headers=_headers(bystander_token))
    assert wrong_actor.status_code == 403

    correct_actor = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/approve", headers=_headers(real_assignee_token))
    assert correct_actor.status_code == 200, correct_actor.text

    # Already decided — a second approve from the real assignee is a 409, not a 403.
    already_decided = await client.post(
        f"/api/v1/workflow/instance-steps/{step_id}/approve", headers=_headers(real_assignee_token)
    )
    assert already_decided.status_code == 409


async def test_role_assigned_step_authorizes_by_role_membership(client, db):
    tenant = await make_tenant(db, subdomain="workflow-auth-role-assigned")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-auth-role-test.example")

    approver_role = await make_role_with_permissions(
        db, tenant_id=None, name="RoleAssignedApprovers", permission_keys=_ALL_WORKFLOW_PERMS
    )
    role_member, role_member_token = await _make_user(db, tenant, "member@workflow-auth-role-test.example", role=approver_role)
    non_member, non_member_token = await _make_user(db, tenant, "nonmember@workflow-auth-role-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Single role-assigned step",
                "steps": [{"sequence_order": 1, "approver_role_key": "RoleAssignedApprovers"}],
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

    non_member_attempt = await client.post(
        f"/api/v1/workflow/instance-steps/{step_id}/reject", headers=_headers(non_member_token)
    )
    assert non_member_attempt.status_code == 403

    member_attempt = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/reject", headers=_headers(role_member_token))
    assert member_attempt.status_code == 200, member_attempt.text
