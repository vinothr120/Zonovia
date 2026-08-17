"""Sequential approval groups (steps with distinct sequence_order): approving the sole step in
the current group advances current_sequence_order to the next group and notifies its
approver(s); approving the final group resolves the instance as approved and notifies the
original requester."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"SeqUser-{email}", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def test_sequential_two_step_flow_resolves_approved_and_notifies_requester(client, db):
    tenant = await make_tenant(db, subdomain="workflow-approve-sequential")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-seq-test.example")
    approver_a, approver_a_token = await _make_user(db, tenant, "approvera@workflow-seq-test.example")
    approver_b, approver_b_token = await _make_user(db, tenant, "approverb@workflow-seq-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Two step sequential",
                "steps": [
                    {"sequence_order": 1, "approver_user_id": str(approver_a.id)},
                    {"sequence_order": 2, "approver_user_id": str(approver_b.id)},
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
    step_by_order = {s["sequence_order"]: s for s in instance["steps"]}
    assert step_by_order[1]["status"] == "pending"
    assert step_by_order[2]["status"] == "pending"

    # Step 2's approver has nothing to do yet.
    early_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_by_order[2]['id']}/approve", headers=_headers(approver_b_token)
    )
    assert early_approve.status_code == 409

    first_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_by_order[1]['id']}/approve", headers=_headers(approver_a_token)
    )
    assert first_approve.status_code == 200, first_approve.text
    assert first_approve.json()["data"]["status"] == "approved"

    mid_instance = (await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=requester_headers)).json()["data"]
    assert mid_instance["status"] == "pending"
    assert mid_instance["current_sequence_order"] == 2

    # Step 1's approver can no longer act (already decided, and no longer the current group).
    second_attempt_on_step1 = await client.post(
        f"/api/v1/workflow/instance-steps/{step_by_order[1]['id']}/approve", headers=_headers(approver_a_token)
    )
    assert second_attempt_on_step1.status_code == 409

    second_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_by_order[2]['id']}/approve", headers=_headers(approver_b_token)
    )
    assert second_approve.status_code == 200, second_approve.text

    final_instance = (await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=requester_headers)).json()["data"]
    assert final_instance["status"] == "approved"
    assert final_instance["current_sequence_order"] is None
    assert final_instance["resolved_at"] is not None

    requester_notifications = (await client.get("/api/v1/workflow/notifications", headers=requester_headers)).json()["data"]
    assert any(n["type"] == "approval_resolved" and n["entity_id"] == entity_id for n in requester_notifications)
