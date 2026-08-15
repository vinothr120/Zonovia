from app.core.module_registry import register_module


def register_all_modules() -> None:
    """Imported once at app startup (and by the seed script) so every module's permission
    catalog and module-registry entry exists before anything queries it. Adding a new module
    later means adding one import here — nothing else changes."""
    from app.asset_core.permissions import MODULE as asset_core_module
    from app.audit.permissions import MODULE as audit_module
    from app.entitlements.permissions import MODULE as entitlements_module
    from app.flow.permissions import MODULE as flow_module
    from app.inventory.permissions import MODULE as inventory_module
    from app.maintenance.permissions import MODULE as maintenance_module
    from app.tenants.permissions import MODULE as platform_module
    from app.tracking.permissions import MODULE as tracking_module
    from app.users.permissions import MODULE as users_module

    for module in (
        platform_module,
        users_module,
        audit_module,
        entitlements_module,
        asset_core_module,
        flow_module,
        tracking_module,
        inventory_module,
        maintenance_module,
    ):
        register_module(module)


def register_all_tracking_providers() -> None:
    """Imported once at app startup — registers every built-in TrackingProvider before any
    scan request can look one up. Mirrors register_all_modules's shape and reasoning: adding
    a new provider later (e.g. Phase 6's track_rfid module registering an RFIDProvider) means
    adding one import here, without app/tracking/ ever importing from the new module."""
    from app.tracking.providers.barcode import BarcodeProvider
    from app.tracking.providers.qr import QRProvider
    from app.tracking.providers.registry import register_provider

    register_provider(QRProvider())
    register_provider(BarcodeProvider())
