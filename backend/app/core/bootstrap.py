from app.core.module_registry import register_module


def register_all_modules() -> None:
    """Imported once at app startup (and by the seed script) so every module's permission
    catalog and module-registry entry exists before anything queries it. Adding a new module
    later means adding one import here — nothing else changes."""
    from app.asset_core.permissions import MODULE as asset_core_module
    from app.audit.permissions import MODULE as audit_module
    from app.entitlements.permissions import MODULE as entitlements_module
    from app.flow.permissions import MODULE as flow_module
    from app.tenants.permissions import MODULE as platform_module
    from app.users.permissions import MODULE as users_module

    for module in (platform_module, users_module, audit_module, entitlements_module, asset_core_module, flow_module):
        register_module(module)
