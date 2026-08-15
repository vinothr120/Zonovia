from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="inventory",
    display_name="Zonovia Inventory & Audit",
    always_on=False,
    default_enabled=False,  # "Zonovia Manage" license tier, distinct from asset-core/flow/
    # tracking-engine's "Zonovia Core" — the first module in the project that isn't bundled by
    # default. A tenant needs an explicit TenantModuleEntitlement row (enabled=True) before
    # any inventory endpoint is reachable; see app/seed.py's acme-demo entitlement seed row.
    permissions=(
        PermissionDef("inventory.view", "View inventory cycles, counts, and reconciliation history"),
        PermissionDef("inventory.manage_cycles", "Create, start, complete, and cancel inventory cycles"),
        PermissionDef("inventory.verify", "Record a verification (scan) during an active inventory cycle"),
        PermissionDef("inventory.reconcile", "Record a reconciliation decision for a cycle"),
    ),
)
