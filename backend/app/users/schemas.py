import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_system_role: bool
    grantable: bool = True
    """Whether the CALLER (not just anyone) may assign this role via POST /users/{id}/roles —
    system roles are only grantable by a platform admin, computed per-request in the router
    since it depends on the caller's own token, not a static role property."""


class RoleDetailRead(RoleRead):
    permission_keys: list[str] = []


class RoleCreate(BaseModel):
    name: str
    permission_keys: list[str] = []


class RolePermissionsUpdate(BaseModel):
    permission_keys: list[str]


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    module_key: str
    description: str


class UserRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    scope_type: str
    scope_id: uuid.UUID | None


class UserCreate(BaseModel):
    email: EmailStr
    phone: str | None = None
    password: str = Field(min_length=10)


class UserUpdate(BaseModel):
    phone: str | None = None
    status: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    phone: str | None
    status: str
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime
    roles: list[UserRoleRead] = []


class MeRead(UserRead):
    is_platform_admin: bool
    permissions: list[str] = []


class AssignRoleRequest(BaseModel):
    role_id: uuid.UUID
    scope_type: str = Field(default="tenant", pattern="^(tenant)$")
    """Phase 0 only implements/validates tenant-wide role scope — see UserRole's docstring.
    The pattern is deliberately narrower than the column's own shape (which already allows
    future location-scoped values) so Phase 1 widens this by relaxing one regex, not adding
    a migration."""
    scope_id: uuid.UUID | None = None
