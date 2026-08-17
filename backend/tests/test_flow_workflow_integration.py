"""FlowService.transition_asset's one deliberate write-dependency into another module: an
in-transaction call to WorkflowService.evaluate_and_maybe_open, purely to optionally open an
ApprovalInstance for visibility. Proves the *opposite* property from
test_maintenance_flow_boundary.py's static test — that the write is safe and narrow, not that no
write happens.

Mirrors test_maintenance_workflow_integration.py's structure and helper style. The one
substantively different test here is #6
(test_two_matching_transitions_on_the_same_asset_each_get_independent_approval_instances): it
validates the module implementation plan's central design decision that entity_id must be the
transition row's own id (history.id), not asset.id — if it had been asset.id, the second matching
transition's evaluate_and_maybe_open call would have been silently swallowed by the duplicate-open
guard (see WorkflowService.evaluate_and_maybe_open / ApprovalInstanceRepository.get_open_for_entity)
instead of opening its own independent instance."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_FLOW_PERMS = ["asset_lifecycle.view", "assets.transition_lifecycle"]
_WORKFLOW_PERMS = ["workflow.view", "workflow.manage_definitions", "workflow.decide"]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


async def _make_user(db, tenant, *, email="user@flow-workflow-test.example"):
    # flow and asset-core are both default_enabled=True (bundled in the base edition) — unlike
    # maintenance, no explicit TenantModuleEntitlement row is needed, same as
    # test_maintenance_flow_boundary.py's flow-side users.
    role = await make_role_with_permissions(
        db,
        tenant_id=None,
        name=f"FlowWorkflowUser-{email}",
        permission_keys=_FLOW_PERMS + _WORKFLOW_PERMS + _CATALOG_PERMS,
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    return user, token


async def _ensure_approver_role(db) -> None:
    """The default definition's step references this role by name — since tests don't run
    app.seed's sync_system_roles, it must be created explicitly first (same pattern as
    test_maintenance_workflow_integration.py's _ensure_approver_role)."""
    await make_role_with_permissions(db, tenant_id=None, name="Tenant Admin", permission_keys=_WORKFLOW_PERMS)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_asset(client, headers, name="Workflow Integration Asset", purchase_price=None):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    body = {"name": name, "asset_type_id": asset_type["id"]}
    if purchase_price is not None:
        body["purchase_price"] = purchase_price
    asset = (await client.post("/api/v1/assets", json=body, headers=headers)).json()["data"]
    return asset


async def _states_by_key(client, headers) -> dict:
    resp = await client.get("/api/v1/asset-lifecycle/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return {s["key"]: s for s in resp.json()["data"]}


async def _create_definition(client, headers, **overrides) -> dict:
    body = {
        "entity_type": "asset_lifecycle_transition",
        "name": "Purchase price threshold approval",
        "condition_attribute": "purchase_price",
        "condition_operator": "gte",
        "condition_value": 500,
        "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
    }
    body.update(overrides)
    resp = await client.post("/api/v1/workflow/definitions", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _transition(client, headers, asset_id, to_state_id) -> dict:
    resp = await client.post(f"/api/v1/assets/{asset_id}/transition", json={"to_state_id": to_state_id}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _instances_for_transition(client, headers, transition_id) -> list[dict]:
    resp = await client.get(
        "/api/v1/workflow/instances",
        params={"entity_type": "asset_lifecycle_transition", "entity_id": transition_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_transition_succeeds_identically_with_no_matching_workflow_definition(client, db):
    tenant = await make_tenant(db, subdomain="flow-workflow-no-definition")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = _headers(token)

    asset = await _create_asset(client, headers, purchase_price="600.00")
    states_by_key = await _states_by_key(client, headers)
    transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])
    assert transition["to_state_id"] == states_by_key["procured"]["id"]

    instances = await _instances_for_transition(client, headers, transition["id"])
    assert instances == []


async def test_transition_opens_an_approval_instance_when_a_matching_definition_exists(client, db):
    """The test that would catch a Decimal-serialization regression: the only case here that
    exercises the actual persistence path with a non-empty, matching purchase_price."""
    tenant = await make_tenant(db, subdomain="flow-workflow-matching-definition")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers, purchase_price="600.00")
    states_by_key = await _states_by_key(client, headers)
    transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])

    instances = await _instances_for_transition(client, headers, transition["id"])
    assert len(instances) == 1
    instance = instances[0]
    assert instance["status"] == "pending"
    assert instance["context"] == {"purchase_price": 600.0, "to_state_key": "procured", "from_state_key": None}


async def test_transition_succeeds_below_threshold_no_instance_opens(client, db):
    tenant = await make_tenant(db, subdomain="flow-workflow-below-threshold")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers, purchase_price="100.00")
    states_by_key = await _states_by_key(client, headers)
    transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])

    instances = await _instances_for_transition(client, headers, transition["id"])
    assert instances == []


async def test_resolved_approval_instance_never_changes_asset_lifecycle_state(client, db):
    tenant = await make_tenant(db, subdomain="flow-workflow-rejected-instance")
    user, token = await _make_user(db, tenant)
    await db.commit()
    headers = _headers(token)

    # approver_user_id set directly to this test's own user — _is_assignee's user-id branch,
    # avoiding any dependency on role membership just to exercise the reject decision path.
    await _create_definition(client, headers, steps=[{"sequence_order": 1, "approver_user_id": str(user.id)}])
    asset = await _create_asset(client, headers, purchase_price="600.00")
    states_by_key = await _states_by_key(client, headers)
    transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])

    instances = await _instances_for_transition(client, headers, transition["id"])
    instance = instances[0]
    step_id = instance["steps"][0]["id"]

    reject_resp = await client.post(f"/api/v1/workflow/instance-steps/{step_id}/reject", headers=headers)
    assert reject_resp.status_code == 200, reject_resp.text

    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_lifecycle_state_id"] == states_by_key["procured"]["id"]


async def test_further_transitions_still_work_normally_when_an_approval_instance_is_open(client, db):
    """Proves "non-blocking" concretely, not just by absence of code: a second, different valid
    transition on the same asset succeeds normally while a pending instance from the first
    transition is still open."""
    tenant = await make_tenant(db, subdomain="flow-workflow-lifecycle-unblocked")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers, purchase_price="600.00")
    states_by_key = await _states_by_key(client, headers)

    first_transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])
    instances = await _instances_for_transition(client, headers, first_transition["id"])
    assert instances[0]["status"] == "pending"

    second_transition = await _transition(client, headers, asset["id"], states_by_key["received"]["id"])
    assert second_transition["to_state_id"] == states_by_key["received"]["id"]

    asset_after = (await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)).json()["data"]
    assert asset_after["current_lifecycle_state_id"] == states_by_key["received"]["id"]

    # The first instance itself is untouched by the second, unrelated transition.
    instances_after = await _instances_for_transition(client, headers, first_transition["id"])
    assert instances_after[0]["status"] == "pending"


async def test_two_matching_transitions_on_the_same_asset_each_get_independent_approval_instances(client, db):
    """The entity_id-design validation test: two separate matching transitions on the same
    asset, neither instance resolved. If entity_id had been asset.id (rejected by the module
    implementation plan's design decision), the second evaluate_and_maybe_open call would have
    been silently swallowed by the duplicate-open guard and only one instance would exist."""
    tenant = await make_tenant(db, subdomain="flow-workflow-independent-instances")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers, purchase_price="600.00")
    states_by_key = await _states_by_key(client, headers)

    first_transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])
    second_transition = await _transition(client, headers, asset["id"], states_by_key["received"]["id"])
    assert first_transition["id"] != second_transition["id"]

    first_instances = await _instances_for_transition(client, headers, first_transition["id"])
    second_instances = await _instances_for_transition(client, headers, second_transition["id"])

    assert len(first_instances) == 1
    assert len(second_instances) == 1
    assert first_instances[0]["id"] != second_instances[0]["id"]
    assert first_instances[0]["status"] == "pending"
    assert second_instances[0]["status"] == "pending"


async def test_transition_with_none_purchase_price_and_no_current_state_does_not_crash_evaluation(client, db):
    """Exercises the "no match, no crash" path with this integration's actual first-transition
    data shape: purchase_price omitted (None) and from_state_key None (the asset's very first
    transition), against a purchase_price-conditioned rule."""
    tenant = await make_tenant(db, subdomain="flow-workflow-none-fields")
    _user, token = await _make_user(db, tenant)
    await _ensure_approver_role(db)
    await db.commit()
    headers = _headers(token)

    await _create_definition(client, headers)
    asset = await _create_asset(client, headers)
    states_by_key = await _states_by_key(client, headers)
    transition = await _transition(client, headers, asset["id"], states_by_key["procured"]["id"])

    instances = await _instances_for_transition(client, headers, transition["id"])
    assert instances == []


def test_flow_module_may_import_workflow_service_but_only_via_evaluate_and_maybe_open():
    """Static check, opposite polarity from test_maintenance_flow_boundary.py's Flow-boundary
    test: confirms app/flow/service.py DOES import WorkflowService (catches an accidental
    revert of this integration) and confirms it never calls any other WorkflowService method
    (approve_step/reject_step/cancel_instance/create_definition/etc.) — proves the write this
    module makes into Workflow stays narrow."""
    import pathlib
    import re

    service_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "flow" / "service.py"
    text = service_path.read_text(encoding="utf-8")

    assert re.search(r"from app\.workflow\.service import WorkflowService", text), (
        "app/flow/service.py must import WorkflowService — the deliberate, documented " "write-dependency into Workflow."
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
    ), f"app/flow/service.py must only call WorkflowService.evaluate_and_maybe_open, found: {offending_calls}"

    assert ".evaluate_and_maybe_open(" in text
