from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="tracking-engine",
    display_name="Tracking Engine",
    always_on=False,
    default_enabled=True,  # bundled in the base "Zonovia Core" edition per blueprint §29 —
    # still genuinely gated through require_module, not always_on. Same treatment as
    # asset-core/flow.
    permissions=(
        PermissionDef("tracking.scan", "Record a QR/barcode scan against an asset"),
        PermissionDef("tracking.view", "View an asset's scan history"),
    ),
)
