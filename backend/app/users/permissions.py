from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="users",
    display_name="User & Role Management",
    always_on=True,
    permissions=(
        PermissionDef("users.view", "View users"),
        PermissionDef("users.create", "Create users"),
        PermissionDef("users.edit", "Edit users"),
        PermissionDef("users.delete", "Deactivate or delete users"),
        PermissionDef("roles.view", "View roles"),
        PermissionDef("roles.manage", "Create/edit roles, assign permissions, grant/revoke user role assignments"),
    ),
)
