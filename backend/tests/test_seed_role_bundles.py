"""Regression guard for app/seed.py::DEFAULT_ROLE_BUNDLES's Phase 1 extension — the exact
permission-to-bundle table from the implementation plan: Viewer gets every *.view key only;
Member gets everything except asset_lifecycle.configure; Tenant Admin gets everything
including asset_lifecycle.configure; Platform Admin is unaffected (still the None sentinel,
meaning every registered permission)."""

from app.asset_core.permissions import MODULE as asset_core_module
from app.flow.permissions import MODULE as flow_module
from app.seed import DEFAULT_ROLE_BUNDLES

_ASSET_CORE_AND_FLOW_KEYS = {p.key for p in asset_core_module.permissions} | {p.key for p in flow_module.permissions}


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
