"""Rejecting any single step immediately resolves the whole ApprovalInstance as rejected and
bulk-skips every other still-pending step (current group siblings and future groups) — no
partial-continuation semantics. Already-decided (approved) steps are left untouched."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"RejUser-{email}", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def test_reject_in_parallel_group_short_circuits_and_skips_future_group(client, db):
    tenant = await make_tenant(db, subdomain="workflow-reject-short-circuit")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-reject-test.example")
    approver_a, approver_a_token = await _make_user(db, tenant, "approvera@workflow-reject-test.example")
    approver_b, approver_b_token = await _make_user(db, tenant, "approverb@workflow-reject-test.example")
    approver_c, approver_c_token = await _make_user(db, tenant, "approverc@workflow-reject-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Parallel group then a later group",
                "steps": [
                    {"sequence_order": 1, "approver_user_id": str(approver_a.id)},
                    {"sequence_order": 1, "approver_user_id": str(approver_b.id)},
                    {"sequence_order": 2, "approver_user_id": str(approver_c.id)},
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
    steps = instance["steps"]
    step_a = next(s for s in steps if s["approver_user_id"] == str(approver_a.id))
    step_b = next(s for s in steps if s["approver_user_id"] == str(approver_b.id))
    step_c = next(s for s in steps if s["approver_user_id"] == str(approver_c.id))

    # A approves first — B (same group) still pending, C (future group) still pending.
    approve_a = await client.post(f"/api/v1/workflow/instance-steps/{step_a['id']}/approve", headers=_headers(approver_a_token))
    assert approve_a.status_code == 200, approve_a.text

    # B rejects — this must short-circuit the whole instance.
    reject_b = await client.post(f"/api/v1/workflow/instance-steps/{step_b['id']}/reject", headers=_headers(approver_b_token))
    assert reject_b.status_code == 200, reject_b.text
    assert reject_b.json()["data"]["status"] == "rejected"

    final_instance = (await client.get(f"/api/v1/workflow/instances/{instance['id']}", headers=requester_headers)).json()["data"]
    assert final_instance["status"] == "rejected"
    assert final_instance["current_sequence_order"] is None

    final_steps_by_id = {s["id"]: s for s in final_instance["steps"]}
    assert final_steps_by_id[step_a["id"]]["status"] == "approved"  # untouched — was already decided
    assert final_steps_by_id[step_b["id"]]["status"] == "rejected"
    assert final_steps_by_id[step_c["id"]]["status"] == "skipped"  # future group, bulk-skipped

    # C's approver can no longer act — the instance is no longer pending.
    late_approve = await client.post(
        f"/api/v1/workflow/instance-steps/{step_c['id']}/approve", headers=_headers(approver_c_token)
    )
    assert late_approve.status_code == 409

    requester_notifications = (await client.get("/api/v1/workflow/notifications", headers=requester_headers)).json()["data"]
    assert any(n["type"] == "approval_resolved" and n["entity_id"] == entity_id for n in requester_notifications)
