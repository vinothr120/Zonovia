import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_permission
from app.core.exceptions import NotFoundError
from app.core.pagination import PageParams, page_params
from app.core.response import PageMeta, ok
from app.users.models import User
from app.users.repository import PermissionRepository, RoleRepository
from app.users.schemas import (
    AssignRoleRequest,
    MeRead,
    PermissionRead,
    RoleCreate,
    RoleDetailRead,
    RolePermissionsUpdate,
    RoleRead,
    UserCreate,
    UserRead,
    UserRoleRead,
)
from app.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _to_role_read(role, is_platform_admin: bool) -> RoleRead:
    return RoleRead(
        id=role.id, name=role.name, is_system_role=role.is_system_role, grantable=(not role.is_system_role) or is_platform_admin
    )


async def _to_user_read(service: UserService, user: User) -> UserRead:
    assignments = await service.user_roles.list_for_user(user.id)
    role_reads: list[UserRoleRead] = []
    for a in assignments:
        role = await service.roles.get_by_id(a.role_id)
        role_reads.append(
            UserRoleRead(
                id=a.id,
                role_id=a.role_id,
                role_name=role.name if role else "unknown",
                scope_type=a.scope_type,
                scope_id=a.scope_id,
            )
        )
    return UserRead(
        id=user.id,
        email=user.email,
        phone=user.phone,
        status=user.status,
        mfa_enabled=user.mfa_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        roles=role_reads,
    )


@router.get("")
async def list_users(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("users.view")),
):
    service = UserService(db, payload.tenant_id)
    users = await service.users.list(offset=pagination.offset, limit=pagination.limit)
    total = await service.users.count()
    items = [await _to_user_read(service, u) for u in users]
    return ok([i.model_dump() for i in items], meta=PageMeta(page=pagination.page, page_size=pagination.page_size, total=total))


@router.post("", status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("users.create")),
):
    service = UserService(db, payload.tenant_id)
    user = await service.create_user(email=body.email, phone=body.phone, password=body.password, actor_user_id=actor.id)
    data = await _to_user_read(service, user)
    return ok(data.model_dump())


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    user: User = Depends(get_current_user),
):
    service = UserService(db, payload.tenant_id)
    base = await _to_user_read(service, user)
    grants = await service.get_effective_grants(user.id)
    permissions = sorted({g.permission_key for g in grants})
    data = MeRead(**base.model_dump(), is_platform_admin=payload.is_platform_admin, permissions=permissions)
    return ok(data.model_dump())


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("users.view")),
):
    service = UserService(db, payload.tenant_id)
    user = await service.get_user_or_404(user_id)
    data = await _to_user_read(service, user)
    return ok(data.model_dump())


@router.post("/{user_id}/roles", status_code=201)
async def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("roles.manage")),
):
    service = UserService(db, payload.tenant_id)
    assignment = await service.assign_role(
        user_id=user_id,
        role_id=body.role_id,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        actor_user_id=actor.id,
        actor_is_platform_admin=payload.is_platform_admin,
    )
    return ok({"id": assignment.id, "role_id": assignment.role_id, "scope_type": assignment.scope_type})


@router.delete("/{user_id}/roles/{user_role_id}", status_code=204)
async def revoke_role(
    user_id: uuid.UUID,  # noqa: ARG001 — must match the {user_id} path segment; unused beyond routing
    user_role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("roles.manage")),
):
    service = UserService(db, payload.tenant_id)
    await service.revoke_role(user_role_id=user_role_id, actor_user_id=actor.id)


roles_router = APIRouter(prefix="/roles", tags=["roles"])


@roles_router.get("")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("roles.view")),
):
    repo = RoleRepository(db, payload.tenant_id)
    roles = await repo.list_available()
    return ok([_to_role_read(r, payload.is_platform_admin).model_dump() for r in roles])


@roles_router.post("", status_code=201)
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("roles.manage")),
):
    service = UserService(db, payload.tenant_id)
    role = await service.create_role(name=body.name, permission_keys=body.permission_keys, actor_user_id=actor.id)
    permissions = await service.permissions.list_for_role(role.id)
    data = RoleDetailRead(
        **_to_role_read(role, payload.is_platform_admin).model_dump(), permission_keys=[p.key for p in permissions]
    )
    return ok(data.model_dump())


@roles_router.get("/{role_id}")
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("roles.view")),
):
    service = UserService(db, payload.tenant_id)
    role = await service.roles.get_by_id(role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    permissions = await service.permissions.list_for_role(role.id)
    data = RoleDetailRead(
        **_to_role_read(role, payload.is_platform_admin).model_dump(), permission_keys=[p.key for p in permissions]
    )
    return ok(data.model_dump())


@roles_router.put("/{role_id}/permissions")
async def update_role_permissions(
    role_id: uuid.UUID,
    body: RolePermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("roles.manage")),
):
    service = UserService(db, payload.tenant_id)
    role = await service.update_role_permissions(role_id=role_id, permission_keys=body.permission_keys, actor_user_id=actor.id)
    permissions = await service.permissions.list_for_role(role.id)
    data = RoleDetailRead(
        id=role.id, name=role.name, is_system_role=role.is_system_role, permission_keys=[p.key for p in permissions]
    )
    return ok(data.model_dump())


permissions_router = APIRouter(prefix="/permissions", tags=["permissions"])


@permissions_router.get("")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("roles.view")),
):
    """Self-service-adjacent: gated by roles.view (same permission that lets a caller see
    the role catalog) rather than a separate key — this is reference data needed only to
    build a role's permission checklist, not sensitive on its own."""
    repo = PermissionRepository(db)
    permissions = await repo.list_all()
    return ok([PermissionRead.model_validate(p).model_dump() for p in permissions])
