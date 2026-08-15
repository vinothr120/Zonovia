from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="entitlements",
    display_name="Licensing & Entitlements",
    always_on=True,
    permissions=(
        PermissionDef("entitlements.view", "View which modules are licensed for this tenant"),
        PermissionDef("entitlements.manage", "Toggle a tenant's module entitlements — Platform Admin only, a commercial action"),
    ),
)
