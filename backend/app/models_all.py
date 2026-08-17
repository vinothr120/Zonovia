"""Imports every ORM model module so Base.metadata is fully populated — used by Alembic's
env.py for autogenerate support going forward, and by tests that build a SQLite schema
directly from the models."""

from app.asset_core.models import (  # noqa: F401
    Asset,
    AssetCategory,
    AssetDocument,
    AssetIdentifier,
    AssetLocation,
    AssetType,
    Vendor,
)
from app.audit.models import AuditLog  # noqa: F401
from app.auth.models import RefreshToken  # noqa: F401
from app.core.base_model import Base  # noqa: F401
from app.entitlements.models import TenantModuleEntitlement  # noqa: F401
from app.flow.models import (  # noqa: F401
    AssetAssignment,
    AssetLifecycleTransition,
    AssetMovement,
    LifecycleStateDefinition,
    LifecycleTransitionDefinition,
)
from app.inventory.models import InventoryCount, InventoryCycle, ReconciliationAction  # noqa: F401
from app.maintenance.models import MaintenanceTicket, ServiceSchedule, Warranty  # noqa: F401
from app.tenants.models import Tenant, TenantConnectionRoute, TenantSetting  # noqa: F401
from app.track_rfid.models import RfidReadEvent, RfidTag  # noqa: F401
from app.tracking.models import Device, DeviceGateway, TrackingEvent  # noqa: F401
from app.users.models import Permission, Role, RolePermission, User, UserRole  # noqa: F401
from app.workflow.models import (  # noqa: F401
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalStepDefinition,
    Notification,
    WorkflowDefinition,
)
