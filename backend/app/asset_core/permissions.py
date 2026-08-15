from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="asset-core",
    display_name="Asset Core",
    always_on=False,
    default_enabled=True,  # bundled in the base "Zonovia Core" edition per blueprint §29 —
    # still genuinely gated through require_module, not always_on.
    permissions=(
        PermissionDef("assets.view", "View assets"),
        PermissionDef("assets.create", "Create assets"),
        PermissionDef("assets.edit", "Edit assets"),
        PermissionDef("assets.delete", "Delete assets"),
        PermissionDef("assets.manage_documents", "Upload/delete documents attached to an asset"),
        PermissionDef("asset_catalog.manage", "Manage asset categories, types, and vendors"),
        PermissionDef("asset_locations.view", "View the location hierarchy"),
        PermissionDef("asset_locations.manage", "Create/edit/delete locations"),
    ),
)
