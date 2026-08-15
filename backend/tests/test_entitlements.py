"""app.entitlements — the module-entitlement stub (implementation plan's one genuine design
addition beyond a straight SchoolAssist port, per ADR-007). Covers both the service-level
fallback behavior (EntitlementService.is_enabled) and the actual gate a route would use
(core.deps.require_module), via a throwaway route mounted on the real app for the duration
of these tests — there's no real non-always_on module to gate yet in Phase 0 (Phase 1's
asset-core is the first genuine caller), so this is the dedicated exercise the implementation
plan calls for."""

import pytest
from fastapi import Depends

from app.core.deps import TokenPayload, get_db, get_token_payload, require_module
from app.core.module_registry import ModuleDefinition, register_module
from app.core.response import ok
from app.entitlements.models import TenantModuleEntitlement
from app.entitlements.service import EntitlementService
from app.main import app
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_FAKE_MODULE_KEY = "test-gated-module"
_FAKE_ROUTE_PATH = "/api/v1/_test/gated"


async def _gated_endpoint(
    _db=Depends(get_db),
    _payload: TokenPayload = Depends(get_token_payload),
    _gate=Depends(require_module(_FAKE_MODULE_KEY)),
):
    return ok({"ok": True})


async def _always_on_gated_endpoint(
    _db=Depends(get_db),
    _payload: TokenPayload = Depends(get_token_payload),
    _gate=Depends(require_module("users")),
):
    return ok({"ok": True})


@pytest.fixture
def fake_gated_module():
    """Registers a throwaway, non-always_on, default-disabled module and mounts a route
    behind require_module(that module's key) for the duration of one test, then tears both
    down — mirrors the implementation plan's verification step 8 exactly."""
    register_module(
        ModuleDefinition(key=_FAKE_MODULE_KEY, display_name="Test Gated Module", always_on=False, default_enabled=False)
    )
    app.add_api_route(_FAKE_ROUTE_PATH, _gated_endpoint, methods=["GET"])
    yield _FAKE_MODULE_KEY
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != _FAKE_ROUTE_PATH]


async def test_require_module_denies_when_no_entitlement_row_and_default_disabled(client, db, fake_gated_module):  # noqa: ARG001 — fixture used for its setup/teardown side effect
    tenant = await make_tenant(db, subdomain="entitlement-gate-denied")
    role = await make_role_with_permissions(db, tenant_id=None, name="GateDeniedRole", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gatedenied@example.com", role=role)
    await db.commit()

    resp = await client.get(_FAKE_ROUTE_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


async def test_require_module_allows_once_an_enabled_entitlement_row_exists(client, db, fake_gated_module):
    tenant = await make_tenant(db, subdomain="entitlement-gate-allowed")
    role = await make_role_with_permissions(db, tenant_id=None, name="GateAllowedRole", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="gateallowed@example.com", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key=fake_gated_module, enabled=True, source="manual"))
    await db.commit()

    resp = await client.get(_FAKE_ROUTE_PATH, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_require_module_no_ops_for_an_always_on_module(client, db):
    tenant = await make_tenant(db, subdomain="entitlement-always-on")
    role = await make_role_with_permissions(db, tenant_id=None, name="AlwaysOnRole", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="alwayson@example.com", role=role)
    await db.commit()

    app.add_api_route("/api/v1/_test/always-on", _always_on_gated_endpoint, methods=["GET"])
    try:
        resp = await client.get("/api/v1/_test/always-on", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/api/v1/_test/always-on"]


async def test_entitlement_service_falls_back_to_module_default_enabled(db, fake_gated_module):
    tenant = await make_tenant(db, subdomain="entitlement-service-fallback")
    await db.commit()

    service = EntitlementService(db, tenant.id)
    assert await service.is_enabled(fake_gated_module) is False  # default_enabled=False, no row yet


async def test_entitlement_service_set_enabled_creates_a_manual_row(db, fake_gated_module):
    tenant = await make_tenant(db, subdomain="entitlement-service-set")
    await db.commit()

    service = EntitlementService(db, tenant.id)
    await service.set_enabled(module_key=fake_gated_module, enabled=True, actor_user_id=None)
    await db.commit()

    assert await service.is_enabled(fake_gated_module) is True


async def test_list_modules_requires_entitlements_view_permission(client, db):
    tenant = await make_tenant(db, subdomain="entitlement-list-guard")
    role = await make_role_with_permissions(db, tenant_id=None, name="NoEntitlementsView", permission_keys=[])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="noview@example.com", role=role)
    await db.commit()

    denied = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403


async def test_list_modules_includes_every_registered_always_on_module(client, db):
    tenant = await make_tenant(db, subdomain="entitlement-list-ok")
    role = await make_role_with_permissions(db, tenant_id=None, name="EntitlementsViewer", permission_keys=["entitlements.view"])
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="entview@example.com", role=role)
    await db.commit()

    resp = await client.get("/api/v1/admin/modules", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    modules_by_key = {m["module_key"]: m for m in resp.json()["data"]}
    assert modules_by_key["users"]["always_on"] is True
    assert modules_by_key["users"]["enabled"] is True


async def test_only_platform_admin_can_toggle_an_entitlement(client, db, fake_gated_module):
    tenant = await make_tenant(db, subdomain="entitlement-toggle-guard")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="EntitlementsManagerNotPlatform", permission_keys=["entitlements.manage"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="notplatform@example.com", role=role)
    await db.commit()

    # Holds entitlements.manage but the JWT isn't platform_admin — must still be denied.
    resp = await client.put(
        f"/api/v1/admin/modules/{fake_gated_module}", json={"enabled": True}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
