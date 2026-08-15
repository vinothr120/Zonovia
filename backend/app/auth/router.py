from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import ChangePasswordRequest, LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from app.auth.service import AuthService
from app.core.deps import TokenPayload, get_current_user, get_db, get_public_db, get_token_payload
from app.core.rate_limit import rate_limit_login
from app.core.response import ok
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=None, dependencies=[Depends(rate_limit_login)])
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_public_db)):
    service = AuthService(db)
    access_token, refresh_token, expires_in = await service.login(
        tenant_slug=body.tenant_slug,
        email=body.email,
        password=body.password,
        ip_address=request.client.host if request.client else None,
    )
    return ok(TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in).model_dump())


@router.post("/refresh", response_model=None)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_public_db)):
    service = AuthService(db)
    access_token, refresh_token, expires_in = await service.refresh(refresh_token=body.refresh_token)
    return ok(TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in).model_dump())


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_public_db)):
    service = AuthService(db)
    await service.logout(refresh_token=body.refresh_token)


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    user: User = Depends(get_current_user),
):
    service = AuthService(db)
    await service.change_password(
        user=user, tenant_id=payload.tenant_id, current_password=body.current_password, new_password=body.new_password
    )
