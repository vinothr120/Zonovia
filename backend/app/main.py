from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.asset_core.router import catalog_router as asset_catalog_router
from app.asset_core.router import locations_router as asset_locations_router
from app.asset_core.router import router as assets_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.config import settings
from app.core.bootstrap import register_all_modules, register_all_tracking_providers
from app.core.exceptions import AppError
from app.core.middleware import install_security_headers
from app.entitlements.router import router as entitlements_router
from app.flow.router import lifecycle_config_router
from app.flow.router import router as flow_router
from app.tenants.router import router as tenants_router
from app.tenants.router import settings_router as tenant_settings_router
from app.tracking.router import events_router as tracking_events_router
from app.tracking.router import router as tracking_router
from app.users.router import permissions_router, roles_router
from app.users.router import router as users_router

register_all_modules()
register_all_tracking_providers()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_v1_prefix}/docs",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_security_headers(app)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001 — FastAPI's required handler signature
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "data": None,
            "meta": None,
            "error": {"code": exc.error_code, "message": exc.message, "field_errors": exc.field_errors},
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


api_prefix = settings.api_v1_prefix
app.include_router(auth_router, prefix=api_prefix)
app.include_router(tenants_router, prefix=api_prefix)
app.include_router(tenant_settings_router, prefix=api_prefix)
app.include_router(users_router, prefix=api_prefix)
app.include_router(roles_router, prefix=api_prefix)
app.include_router(permissions_router, prefix=api_prefix)
app.include_router(audit_router, prefix=api_prefix)
app.include_router(entitlements_router, prefix=api_prefix)
app.include_router(assets_router, prefix=api_prefix)
app.include_router(asset_catalog_router, prefix=api_prefix)
app.include_router(asset_locations_router, prefix=api_prefix)
app.include_router(flow_router, prefix=api_prefix)
app.include_router(lifecycle_config_router, prefix=api_prefix)
app.include_router(tracking_router, prefix=api_prefix)
app.include_router(tracking_events_router, prefix=api_prefix)
