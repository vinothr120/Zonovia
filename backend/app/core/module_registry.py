from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionDef:
    key: str  # e.g. "users.create" — namespaced module.action
    description: str


@dataclass(frozen=True)
class ModuleDefinition:
    """A self-contained business domain. Each module declares its own permission keys and
    whether it can be toggled off per tenant — this is what lets a future module (asset-core,
    track-rfid, ...) be added by registering a new ModuleDefinition, without touching any
    other module's code. See docs/authorization.md."""

    key: str
    display_name: str
    permissions: tuple[PermissionDef, ...] = field(default_factory=tuple)
    always_on: bool = False  # Platform Core modules (identity, audit, ...) can't be disabled,
    # and are never gated by app.entitlements.require_module — see docs/authorization.md.
    default_enabled: bool = True  # whether a NEW tenant starts with this module entitled —
    # this is what app.entitlements.EntitlementService falls back to when no
    # TenantModuleEntitlement row exists yet for a tenant. Independent of always_on: a module
    # can default on but still be togglable off (a licensing decision), or vice versa.


_registry: dict[str, ModuleDefinition] = {}


def register_module(module: ModuleDefinition) -> None:
    _registry[module.key] = module


def get_module(key: str) -> ModuleDefinition | None:
    return _registry.get(key)


def get_registered_modules() -> dict[str, ModuleDefinition]:
    return dict(_registry)


def all_permission_defs() -> list[PermissionDef]:
    perms: list[PermissionDef] = []
    for module in _registry.values():
        perms.extend(module.permissions)
    return perms
