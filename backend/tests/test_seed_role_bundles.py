"""Regression guard for app/seed.py::DEFAULT_ROLE_BUNDLES's Phase 1/2/3 extensions — the exact
permission-to-bundle table from the implementation plan: Viewer gets every *.view key only;
Member gets everything except asset_lifecycle.configure; Tenant Admin gets everything
including asset_lifecycle.configure; Platform Admin is unaffected (still the None sentinel,
meaning every registered permission). Phase 2 — Tracking Baseline extends this the same way:
Viewer gets tracking.view only, Member and Tenant Admin both get tracking.scan and
tracking.view (no "configure"-style permission to reserve here, unlike asset_lifecycle). Phase
3 — Inventory & Audit: Viewer gets inventory.view only; Member gets view/verify/manage_cycles
but NOT reconcile (reserved the same way asset_lifecycle.configure is); Tenant Admin gets all
four including inventory.reconcile."""

from app.asset_core.permissions import MODULE as asset_core_module
from app.flow.permissions import MODULE as flow_module
from app.inventory.permissions import MODULE as inventory_module
from app.maintenance.permissions import MODULE as maintenance_module
from app.seed import DEFAULT_ROLE_BUNDLES
from app.tracking.permissions import MODULE as tracking_module

_ASSET_CORE_AND_FLOW_KEYS = {p.key for p in asset_core_module.permissions} | {p.key for p in flow_module.permissions}
_TRACKING_KEYS = {p.key for p in tracking_module.permissions}
_INVENTORY_KEYS = {p.key for p in inventory_module.permissions}
_MAINTENANCE_KEYS = {p.key for p in maintenance_module.permissions}


def test_platform_admin_bundle_is_still_the_none_sentinel():
    assert DEFAULT_ROLE_BUNDLES["Platform Admin"] is None


def test_tenant_admin_gets_every_asset_core_and_flow_permission_including_configure():
    tenant_admin_keys = set(DEFAULT_ROLE_BUNDLES["Tenant Admin"])
    assert _ASSET_CORE_AND_FLOW_KEYS <= tenant_admin_keys
    assert "asset_lifecycle.configure" in tenant_admin_keys


def test_member_gets_every_asset_core_and_flow_permission_except_configure():
    member_keys = set(DEFAULT_ROLE_BUNDLES["Member"])
    expected = _ASSET_CORE_AND_FLOW_KEYS - {"asset_lifecycle.configure"}
    assert expected <= member_keys
    assert "asset_lifecycle.configure" not in member_keys


def test_viewer_only_gets_view_permission_keys():
    viewer_keys = DEFAULT_ROLE_BUNDLES["Viewer"]
    assert all(key.endswith(".view") for key in viewer_keys)
    # Every *.view key from asset-core/flow must be present.
    expected_view_keys = {k for k in _ASSET_CORE_AND_FLOW_KEYS if k.endswith(".view")}
    assert expected_view_keys <= set(viewer_keys)


def test_viewer_does_not_get_any_mutating_asset_core_or_flow_permission():
    viewer_keys = set(DEFAULT_ROLE_BUNDLES["Viewer"])
    mutating_keys = _ASSET_CORE_AND_FLOW_KEYS - {k for k in _ASSET_CORE_AND_FLOW_KEYS if k.endswith(".view")}
    assert viewer_keys.isdisjoint(mutating_keys)


def test_tenant_admin_and_member_both_get_every_tracking_permission():
    assert _TRACKING_KEYS <= set(DEFAULT_ROLE_BUNDLES["Tenant Admin"])
    assert _TRACKING_KEYS <= set(DEFAULT_ROLE_BUNDLES["Member"])


def test_viewer_gets_only_tracking_view_not_tracking_scan():
    viewer_keys = set(DEFAULT_ROLE_BUNDLES["Viewer"])
    assert "tracking.view" in viewer_keys
    assert "tracking.scan" not in viewer_keys


def test_tenant_admin_gets_every_inventory_permission_including_reconcile():
    tenant_admin_keys = set(DEFAULT_ROLE_BUNDLES["Tenant Admin"])
    assert _INVENTORY_KEYS <= tenant_admin_keys
    assert "inventory.reconcile" in tenant_admin_keys


def test_member_gets_inventory_view_verify_manage_cycles_but_not_reconcile():
    member_keys = set(DEFAULT_ROLE_BUNDLES["Member"])
    expected = _INVENTORY_KEYS - {"inventory.reconcile"}
    assert expected <= member_keys
    assert "inventory.reconcile" not in member_keys


def test_viewer_gets_only_inventory_view():
    viewer_keys = set(DEFAULT_ROLE_BUNDLES["Viewer"])
    assert "inventory.view" in viewer_keys
    assert viewer_keys.isdisjoint(_INVENTORY_KEYS - {"inventory.view"})


def test_tenant_admin_gets_every_maintenance_permission():
    tenant_admin_keys = set(DEFAULT_ROLE_BUNDLES["Tenant Admin"])
    assert _MAINTENANCE_KEYS <= tenant_admin_keys


def test_member_gets_every_maintenance_permission_same_as_tenant_admin():
    """Unlike asset_lifecycle.configure/inventory.reconcile, no permission is reserved
    Tenant-Admin-only this phase — Member gets all four maintenance permissions too."""
    member_keys = set(DEFAULT_ROLE_BUNDLES["Member"])
    assert _MAINTENANCE_KEYS <= member_keys


def test_viewer_gets_only_maintenance_view():
    viewer_keys = set(DEFAULT_ROLE_BUNDLES["Viewer"])
    assert "maintenance.view" in viewer_keys
    assert viewer_keys.isdisjoint(_MAINTENANCE_KEYS - {"maintenance.view"})
