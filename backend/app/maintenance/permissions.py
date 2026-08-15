from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="maintenance",
    display_name="Zonovia Maintenance & Warranty",
    always_on=False,
    default_enabled=False,  # "Zonovia Manage" license tier, same treatment as inventory — a
    # tenant needs an explicit TenantModuleEntitlement row (enabled=True) before any
    # maintenance/warranty endpoint is reachable; see app/seed.py's acme-demo entitlement seed
    # row.
    permissions=(
        PermissionDef("maintenance.view", "View maintenance tickets, warranty records, and service schedules"),
        PermissionDef("maintenance.manage_tickets", "Create, edit, start, complete, and cancel maintenance tickets"),
        PermissionDef("maintenance.manage_warranty", "Upsert an asset's warranty record"),
        PermissionDef("maintenance.manage_schedules", "Create, edit, delete service schedules, and record a service"),
        # No permission reserved for Tenant-Admin-only this phase — unlike
        # asset_lifecycle.configure/inventory.reconcile, nothing here rewrites a shared graph
        # or makes a permanent write-off determination. Member gets all four; Viewer gets
        # maintenance.view only. See the module's implementation plan.
    ),
)
