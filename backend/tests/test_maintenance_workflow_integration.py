"""MaintenanceService.create_ticket's one deliberate write-dependency into another module: an
in-transaction call to WorkflowService.evaluate_and_maybe_open, purely to optionally open an
ApprovalInstance for visibility. Proves the *opposite* property from
test_maintenance_flow_boundary.py's static test — that the write is safe and narrow, not that no
write happens. In particular, test 2 below is the one that would have caught a Decimal
serialization bug: it's the only case that exercises the actual persistence path with a
non-empty, matching `cost` value."""

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = ["maintenance.view", "maintenance.manage_tickets"]
_WORKFLOW_PERMS = ["workflow.view", "workflow.manage_definitions", "workflow.decide"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


async def _make_user(db, tenant, *, email="user@maintenance-workflow-test.example"):
    role = await make_role_with_permissions(
        db,
        tenant_id=None,
        name=f"MaintWorkflowUser-{email}",
        permission_keys=_MAINTENANCE_PERMS + _WORKFLOW_PERMS + _CATALOG_PERMS,
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _ensure_approver_role(db) -> None:
    """The default definition's step references this role by name — since tests don't run
    app.seed's sync_system_roles, it must be created explicitly first (same pattern as
    test_workflow_evaluate_and_open.py's _ensure_approver_role)."""
    await make_role_with_permissions(db, tenant_id=None, name="Tenant Admin", permission_keys=_WORKFLOW_PERMS)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_asset(client, headers, name="Workflow Integration Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _create_definition(client, headers, **overrides) -> dict:
    body = {
        "entity_type": "maintenance_ticket",
        "name": "Cost threshold approval",
        "condition_attribute": "cost",
        "condition_operator": "gte",
        "condition_value": 500,
        "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
    }
    body.update(overrides)
    resp = await client.post("/api/v1/workflow/definitions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_ticket(client, headers, asset_id, *, title="Repair", cost=None, priority=None):
    body = {"asset_id": asset_id, "title": title}
    if cost is not None:
        body["cost"] = cost
    if priority is not None:
        body["priority"] = priority
    resp = await client.post("/api/v1/maintenance/tickets", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _instances_for_ticket(client, headers, ticket_id) -> list[dict]:
    resp = await client.get(
        "/api/v1/workflow/instances", params={"entity_type": "maintenance_ticket", "entity_id": ticket_id}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_ticket_creation_succeeds_identically_with_no_matching_workflow_definition(client, db):
    tenant = await make_tenant(db, subdomain="maint-workflow-no-definition")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = _headers(token)

    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="600.00")
    assert ticket["status"] == "open"

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    assert instances == []


async def test_ticket_creation_opens_an_approval_instance_when_a_matching_definition_exists(client, db):
    """The test that would have caught the Decimal-serialization bug: this is the only case
    that exercises the actual persistence path with a non-empty, matching cost."""
    tenant = await make_tenant(db, subdomain="maint-workflow-matching-definition")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="600.00", priority="high")
    assert ticket["status"] == "open"

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    assert len(instances) == 1
    instance = instances[0]
    assert instance["status"] == "pending"
    assert instance["context"] == {"cost": 600.0, "priority": "high"}


async def test_ticket_creation_succeeds_below_threshold_no_instance_opens(client, db):
    tenant = await make_tenant(db, subdomain="maint-workflow-below-threshold")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="100.00")
    assert ticket["status"] == "open"

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    assert instances == []


async def test_rejected_approval_instance_never_changes_ticket_status(client, db):
    tenant = await make_tenant(db, subdomain="maint-workflow-rejected-instance")
    user, token = await _make_user(db, tenant)
    await db.commit()
    headers = _headers(token)

    # approver_user_id set directly to this test's own user — _is_assignee's user-id branch,
    # avoiding any dependency on role membership just to exercise the reject decision path.
    await _create_definition(client, headers, steps=[{"sequence_order": 1, "approver_user_id": str(user.id)}])
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="600.00")

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    instance = instances[0]
    step_id = instance["steps"][0]["id"]

    reject_resp = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/reject", headers=headers)
    assert reject_resp.status_code == 200, reject_resp.text

    ticket_after = (await client.get(f"/api/v1/maintenance/tickets/{ticket['id']}", headers=headers)).json()["data"]
    assert ticket_after["status"] == "open"


async def test_cancelled_approval_instance_never_changes_ticket_status(client, db):
    tenant = await make_tenant(db, subdomain="maint-workflow-cancelled-instance")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="600.00")

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    instance = instances[0]

    cancel_resp = await client.post(f"/api/v1/workflow/instances/{instance['id']}/cancel", headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text

    ticket_after = (await client.get(f"/api/v1/maintenance/tickets/{ticket['id']}", headers=headers)).json()["data"]
    assert ticket_after["status"] == "open"


async def test_ticket_lifecycle_transitions_still_work_normally_when_an_approval_instance_is_open(client, db):
    """Proves "non-blocking" concretely, not just by absence of code: start/complete succeed
    normally while a pending instance is still open on the same ticket."""
    tenant = await make_tenant(db, subdomain="maint-workflow-lifecycle-unblocked")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"], cost="600.00")

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    assert instances[0]["status"] == "pending"

    start_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/start", headers=headers)
    assert start_resp.status_code == 200, start_resp.text
    assert start_resp.json()["data"]["status"] == "in_progress"

    complete_resp = await client.post(f"/api/v1/maintenance/tickets/{ticket['id']}/complete", json={}, headers=headers)
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["data"]["status"] == "completed"

    # The instance itself is untouched by the ticket's own lifecycle transitions.
    instances_after = await _instances_for_ticket(client, headers, ticket["id"])
    assert instances_after[0]["status"] == "pending"


async def test_ticket_creation_cost_none_and_priority_none_do_not_crash_evaluation(client, db):
    """Exercises the "no match, no crash" path with this integration's actual data shape: both
    cost and priority omitted (None), against a cost-conditioned rule."""
    tenant = await make_tenant(db, subdomain="maint-workflow-none-fields")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    ticket = await _create_ticket(client, headers, asset["id"])
    assert ticket["status"] == "open"
    assert ticket["cost"] is None
    assert ticket["priority"] is None

    instances = await _instances_for_ticket(client, headers, ticket["id"])
    assert instances == []


def test_maintenance_module_may_import_workflow_service_but_only_via_evaluate_and_maybe_open():
    """Static check, opposite polarity from test_maintenance_flow_boundary.py's Flow-boundary
    test: confirms app/maintenance/service.py DOES import WorkflowService (catches an
    accidental revert of this integration) and confirms it never calls any other
    WorkflowService method (approve_step/reject_step/cancel_instance/create_definition/etc.) —
    proves the write this module makes into Workflow stays narrow."""
    import pathlib
    import re

    service_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "maintenance" / "service.py"
    text = service_path.read_text(encoding="utf-8")

    assert re.search(r"from app\.workflow\.service import WorkflowService", text), (
        "app/maintenance/service.py must import WorkflowService — the deliberate, documented " "write-dependency into Workflow."
    )

    # Every method actually defined on WorkflowService, confirmed against app/workflow/
    # service.py — evaluate_and_maybe_open is the only one this module is allowed to call.
    _other_workflow_service_methods = [
        "create_definition",
        "get_definition_or_404",
        "list_definitions",
        "update_definition",
        "delete_definition",
        "list_steps",
        "add_step",
        "get_step_or_404",
        "update_step",
        "delete_step",
        "get_instance_or_404",
        "list_instances",
        "list_instance_steps",
        "approve_step",
        "reject_step",
        "cancel_instance",
        "list_for_user",
        "mark_read",
    ]
    offending_calls = [name for name in _other_workflow_service_methods if re.search(rf"\.{re.escape(name)}\(", text)]
    assert (
        offending_calls == []
    ), f"app/maintenance/service.py must only call WorkflowService.evaluate_and_maybe_open, found: {offending_calls}"

    assert ".evaluate_and_maybe_open(" in text
