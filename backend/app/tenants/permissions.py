from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="platform",
    display_name="Platform Administration",
    always_on=True,
    permissions=(
        PermissionDef("platform.manage_tenants", "Create and manage tenants — Platform Admin only"),
        PermissionDef("tenants.view_settings", "View this tenant's configuration settings"),
        PermissionDef("tenants.manage_settings", "Create/update this tenant's configuration settings"),
    ),
)
