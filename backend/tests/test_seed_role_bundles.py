"""Regression guard for app/seed.py::DEFAULT_ROLE_BUNDLES's Phase 1/2 extensions — the exact
permission-to-bundle table from the implementation plan: Viewer gets every *.view key only;
Member gets everything except asset_lifecycle.configure; Tenant Admin gets everything
including asset_lifecycle.configure; Platform Admin is unaffected (still the None sentinel,
meaning every registered permission). Phase 2 — Tracking Baseline extends this the same way:
Viewer gets tracking.view only, Member and Tenant Admin both get tracking.scan and
tracking.view (no "configure"-style permission to reserve here, unlike asset_lifecycle)."""

from app.asset_core.permissions import MODULE as asset_core_module
from app.flow.permissions import MODULE as flow_module
from app.seed import DEFAULT_ROLE_BUNDLES
from app.tracking.permissions import MODULE as tracking_module

_ASSET_CORE_AND_FLOW_KEYS = {p.key for p in asset_core_module.permissions} | {p.key for p in flow_module.permissions}
_TRACKING_KEYS = {p.key for p in tracking_module.permissions}


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
