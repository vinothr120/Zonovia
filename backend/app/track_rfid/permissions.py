from app.core.module_registry import ModuleDefinition, PermissionDef

MODULE = ModuleDefinition(
    key="track-rfid",
    display_name="Zonovia RFID",
    always_on=False,
    default_enabled=False,  # "Zonovia RFID" license tier, distinct from "Zonovia Manage"
    # (inventory/maintenance) and from the base "Zonovia Core" edition (asset-core/flow/
    # tracking-engine) — a tenant needs an explicit TenantModuleEntitlement row (enabled=True)
    # before any /rfid/* endpoint is reachable, including gateway-authenticated ingest (see
    # app/tracking/deps.py::require_module_for_gateway); see app/seed.py's acme-demo
    # entitlement seed row.
    permissions=(
        PermissionDef("track_rfid.manage_tags", "Register and manage RFID tags on assets"),
        PermissionDef("track_rfid.view", "View RFID tags and raw read-event history"),
        # No manage_gateways/manage_devices permission here — Device/DeviceGateway are shared
        # tracking-engine infrastructure, not RFID-specific; their permissions live in
        # app.tracking.permissions instead. See that module's comment for the full reasoning.
    ),
)
