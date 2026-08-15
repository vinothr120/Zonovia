from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import TenantScopedBase


class TenantModuleEntitlement(TenantScopedBase):
    """Zonovia's first-class Licensing & Entitlements bounded context (blueprint §6/§18,
    ADR-007), built deliberately small for Phase 0: one row per (tenant, module) recording
    whether that module is licensed on. No signed license files, grace periods, hardware
    binding, or usage counters yet — those are Phase 9 (blueprint §30). See
    app.entitlements.service.EntitlementService for the fallback behavior when no row exists
    for a given (tenant, module) pair yet."""

    __tablename__ = "tenant_module_entitlements"
    __table_args__ = (UniqueConstraint("tenant_id", "module_key", name="uq_tenant_module_entitlements_tenant_module"),)

    module_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="seed")  # seed|manual
