from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="flow",
    display_name="Zonovia Flow",
    always_on=False,
    default_enabled=True,  # bundled in the base "Zonovia Core" edition per blueprint §29 —
    # still genuinely gated through require_module, not always_on.
    permissions=(
        PermissionDef("asset_lifecycle.view", "View lifecycle states, transitions, and an asset's history"),
        PermissionDef("assets.transition_lifecycle", "Move an asset through its lifecycle"),
        PermissionDef("assets.assign", "Assign/unassign an asset's custodian"),
        PermissionDef("assets.move", "Move an asset between locations"),
        PermissionDef("asset_lifecycle.configure", "Edit the tenant-wide lifecycle state/transition definitions"),
    ),
)
