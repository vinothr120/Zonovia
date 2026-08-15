from pydantic import BaseModel


class ModuleEntitlementRead(BaseModel):
    module_key: str
    display_name: str
    always_on: bool
    enabled: bool
    source: str  # "seed" | "manual" | "default" (no row exists yet — falls back to the
    # module's own ModuleDefinition.default_enabled, see EntitlementService.is_enabled)


class ModuleEntitlementUpdate(BaseModel):
    enabled: bool
