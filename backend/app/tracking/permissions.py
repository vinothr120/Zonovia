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
        # Phase 6 — Device/DeviceGateway are shared tracking-engine infrastructure (not
        # RFID-specific — a tenant with only track-sense licensed would still need these for
        # its BLE beacons), so their management permissions live here, not in track_rfid.
        # Tenant-Admin-only, one tier — a leaked API key is a real security surface, and
        # there's no view-only audience for infrastructure objects like these.
        PermissionDef("tracking.manage_gateways", "Create, list, view, and revoke device gateways"),
        PermissionDef("tracking.manage_devices", "Register and list devices under a gateway"),
    ),
)
