"""Parallel approval groups (steps sharing the same sequence_order): the instance must not
advance/resolve until every step in the group is individually approved."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"ParUser-{email}", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def test_parallel_group_requires_all_steps_approved_before_advancing(client, db):
    tenant = await make_tenant(db, subdomain="workflow-approve-parallel")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-par-test.example")
    approver_a, approver_a_token = await _make_user(db, tenant, "approvera@workflow-par-test.example")
    approver_b, approver_b_token = await _make_user(db, tenant, "approverb@workflow-par-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "One parallel group",
                "steps": [
                    {"sequence_order": 1, "approver_user_id": str(approver_a.id)},
                    {"sequence_order": 1, "approver_user_id": str(approver_b.id)},
                ],
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
    assert instance["current_sequence_order"] == 1
    steps = instance["steps"]
    step_a = next(s for s in steps if s["approver_user_id"] == str(approver_a.id))
    step_b = next(s for s in steps if s["approver_user_id"] == str(approver_b.id))

    first_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_a['id']}/approve", headers=_headers(approver_a_token)
    )
    assert first_approve.status_code == 200, first_approve.text

    mid_instance = (await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=requester_headers)).json()["data"]
    assert mid_instance["status"] == "pending"
    assert mid_instance["current_sequence_order"] == 1  # still the same group — B hasn't approved yet

    second_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_b['id']}/approve", headers=_headers(approver_b_token)
    )
    assert second_approve.status_code == 200, second_approve.text

    final_instance = (await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=requester_headers)).json()["data"]
    assert final_instance["status"] == "approved"
    assert final_instance["current_sequence_order"] is None
