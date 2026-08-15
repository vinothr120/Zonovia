import uuid
from contextvars import ContextVar

_tenant_id_var: ContextVar[uuid.UUID | None] = ContextVar("tenant_id", default=None)
_user_id_var: ContextVar[uuid.UUID | None] = ContextVar("user_id", default=None)
_is_platform_admin_var: ContextVar[bool] = ContextVar("is_platform_admin", default=False)


def set_tenant_id(tenant_id: uuid.UUID | None) -> None:
    _tenant_id_var.set(tenant_id)


def get_tenant_id() -> uuid.UUID | None:
    return _tenant_id_var.get()


def set_current_user_id(user_id: uuid.UUID | None) -> None:
    _user_id_var.set(user_id)


def get_current_user_id() -> uuid.UUID | None:
    return _user_id_var.get()


def set_is_platform_admin(value: bool) -> None:
    _is_platform_admin_var.set(value)


def is_platform_admin() -> bool:
    return _is_platform_admin_var.get()
