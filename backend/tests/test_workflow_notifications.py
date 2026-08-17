"""Notification inbox: recipient isolation (a user only ever sees their own notifications),
idempotent mark-read, cross-user 403 on mark-read, and the unread_only filter. Gated only by
authentication — no permission key, every user manages their own inbox."""

import uuid

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_ALL_WORKFLOW_PERMS = ["workflow.view", "workflow.decide", "workflow.manage_definitions"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, tenant, email):
    role = await make_role_with_permissions(db, tenant_id=None, name=f"NotifUser-{email}", permission_keys=_ALL_WORKFLOW_PERMS)
    return await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)


async def _open_instance_with_single_approver(client, requester_headers, approver_id, entity_id=None):
    definition = (
        await client.post(
            "/api/v1/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "Single approver flow",
                "steps": [{"sequence_order": 1, "approver_user_id": str(approver_id)}],
            },
            headers=requester_headers,
        )
    ).json()["data"]
    assert definition is not None
    resp = await client.post(
        "/api/v1/workflow/instances/evaluate",
        json={"entity_type": "maintenance_ticket", "entity_id": entity_id or str(uuid.uuid4()), "context": {}},
        headers=requester_headers,
    )
    return resp.json()["data"]


async def test_notification_recipient_isolation(client, db):
    tenant = await make_tenant(db, subdomain="workflow-notif-isolation")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-notif-test.example")
    approver_a, approver_a_token = await _make_user(db, tenant, "approvera@workflow-notif-test.example")
    approver_b, approver_b_token = await _make_user(db, tenant, "approverb@workflow-notif-test.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    await _open_instance_with_single_approver(client, requester_headers, approver_a.id)

    a_notifications = (await client.get("/api/v1/workflow/notifications", headers=_headers(approver_a_token))).json()["data"]
    b_notifications = (await client.get("/api/v1/workflow/notifications", headers=_headers(approver_b_token))).json()["data"]
    assert len(a_notifications) == 1
    assert len(b_notifications) == 0


async def test_mark_read_is_idempotent(client, db):
    tenant = await make_tenant(db, subdomain="workflow-notif-idempotent")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-notif-idempotent.example")
    approver, approver_token = await _make_user(db, tenant, "approver@workflow-notif-idempotent.example")
    await db.commit()
    requester_headers = _headers(requester_token)
    approver_headers = _headers(approver_token)

    await _open_instance_with_single_approver(client, requester_headers, approver.id)
    notif = (await client.get("/api/v1/workflow/notifications", headers=approver_headers)).json()["data"][0]
    assert notif["read_at"] is None

    first = await client.post(f"/api/v1/workflow/notifications/{notif['id']}/read", headers=approver_headers)
    assert first.status_code == 200, first.text
    first_read_at = first.json()["data"]["read_at"]
    assert first_read_at is not None

    second = await client.post(f"/api/v1/workflow/notifications/{notif['id']}/read", headers=approver_headers)
    assert second.status_code == 200, second.text
    # SQLite (unlike Postgres) doesn't preserve tzinfo across a round-trip, so the second
    # response — read back from a fresh session — may render without a "+00:00" suffix even
    # though it's the same instant; compare parsed values, not raw strings.
    from datetime import datetime

    assert datetime.fromisoformat(second.json()["data"]["read_at"]).replace(tzinfo=None) == datetime.fromisoformat(
        first_read_at
    ).replace(tzinfo=None)


async def test_mark_read_rejects_a_different_user(client, db):
    tenant = await make_tenant(db, subdomain="workflow-notif-cross-user")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-notif-cross-user.example")
    approver, approver_token = await _make_user(db, tenant, "approver@workflow-notif-cross-user.example")
    bystander, bystander_token = await _make_user(db, tenant, "bystander@workflow-notif-cross-user.example")
    await db.commit()
    requester_headers = _headers(requester_token)

    await _open_instance_with_single_approver(client, requester_headers, approver.id)
    notif = (await client.get("/api/v1/workflow/notifications", headers=_headers(approver_token))).json()["data"][0]

    resp = await client.post(f"/api/v1/workflow/notifications/{notif['id']}/read", headers=_headers(bystander_token))
    assert resp.status_code == 403


async def test_unread_only_filter_excludes_read_notifications(client, db):
    tenant = await make_tenant(db, subdomain="workflow-notif-unread-filter")
    requester, requester_token = await _make_user(db, tenant, "requester@workflow-notif-unread.example")
    approver, approver_token = await _make_user(db, tenant, "approver@workflow-notif-unread.example")
    await db.commit()
    requester_headers = _headers(requester_token)
    approver_headers = _headers(approver_token)

    await _open_instance_with_single_approver(client, requester_headers, approver.id)
    notif = (await client.get("/api/v1/workflow/notifications", headers=approver_headers)).json()["data"][0]
    await client.post(f"/api/v1/workflow/notifications/{notif['id']}/read", headers=approver_headers)

    unread = (await client.get("/api/v1/workflow/notifications?unread_only=true", headers=approver_headers)).json()["data"]
    assert all(n["id"] != notif["id"] for n in unread)

    everything = (await client.get("/api/v1/workflow/notifications", headers=approver_headers)).json()["data"]
    assert any(n["id"] == notif["id"] for n in everything)
