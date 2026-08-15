from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="audit",
    display_name="Audit Log",
    always_on=True,
    permissions=(PermissionDef("audit_logs.view", "View the audit log"),),
)
