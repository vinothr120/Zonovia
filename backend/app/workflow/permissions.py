from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="workflow",
    display_name="Zonovia Workflow & Approvals",
    always_on=True,  # Platform Core infrastructure, not a paid module — blueprint §6/§7 list
    # workflow_* under Identity & Tenancy / "included in every tier", even though §29's
    # packaging prose loosely mentions "advanced lifecycle/workflow" under paid "Zonovia
    # Manage." Resolved the same way the Warranty module-placement ambiguity was resolved:
    # structural dependency table wins over packaging prose. See the module's implementation
    # plan for the full citation trail.
    permissions=(
        PermissionDef("workflow.view", "View workflow definitions, approval instances, and their steps"),
        PermissionDef("workflow.decide", "Approve or reject an approval step assigned to you or your role"),
        PermissionDef(
            "workflow.manage_definitions",
            "Create, edit, and delete workflow definitions and their approval steps; manually evaluate "
            "and cancel approval instances",
        ),
        # workflow.manage_definitions is Tenant-Admin-only — mirrors asset_lifecycle.configure/
        # inventory.reconcile's existing reservation pattern (editing the approval-routing graph
        # is a shared-config edit with tenant-wide consequences), not Maintenance's flat
        # Member-parity pattern. See app/seed.py's DEFAULT_ROLE_BUNDLES for the exact split.
    ),
)
