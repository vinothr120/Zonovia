import uuid

from fastapi import APIRouter, Depends, Form, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.schemas import (
    AssetCategoryCreate,
    AssetCategoryRead,
    AssetCategoryUpdate,
    AssetCreate,
    AssetDocumentRead,
    AssetIdentifierCreate,
    AssetIdentifierRead,
    AssetLocationCreate,
    AssetLocationRead,
    AssetLocationUpdate,
    AssetRead,
    AssetTypeCreate,
    AssetTypeRead,
    AssetTypeUpdate,
    AssetUpdate,
    VendorCreate,
    VendorRead,
    VendorUpdate,
)
from app.asset_core.service import _UNSET, AssetCatalogService, AssetLocationService, AssetService
from app.core.deps import TokenPayload, get_current_user, get_db, get_token_payload, require_module, require_permission
from app.core.pagination import PageParams, page_params
from app.core.response import PageMeta, ok
from app.users.models import User

_module_gate = Depends(require_module("asset-core"))

router = APIRouter(prefix="/assets", tags=["assets"], dependencies=[_module_gate])


@router.get("")
async def list_assets(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    assets = await service.list_assets(offset=pagination.offset, limit=pagination.limit)
    total = await service.assets.count()
    return ok(
        [AssetRead.model_validate(a).model_dump() for a in assets],
        meta=PageMeta(page=pagination.page, page_size=pagination.page_size, total=total),
    )


@router.post("", status_code=201)
async def create_asset(
    body: AssetCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.create")),
):
    service = AssetService(db, payload.tenant_id)
    asset = await service.create_asset(
        name=body.name,
        asset_type_id=body.asset_type_id,
        current_location_id=body.current_location_id,
        current_custodian_id=body.current_custodian_id,
        vendor_id=body.vendor_id,
        purchase_date=body.purchase_date,
        purchase_price=body.purchase_price,
        purchase_order_ref=body.purchase_order_ref,
        actor_user_id=actor.id,
    )
    return ok(AssetRead.model_validate(asset).model_dump())


@router.get("/{asset_id}")
async def get_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    asset = await service.get_asset_or_404(asset_id)
    return ok(AssetRead.model_validate(asset).model_dump())


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: uuid.UUID,
    body: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.edit")),
):
    service = AssetService(db, payload.tenant_id)
    asset = await service.update_asset(
        asset_id=asset_id,
        name=body.name,
        asset_type_id=body.asset_type_id,
        vendor_id=body.vendor_id,
        purchase_date=body.purchase_date,
        purchase_price=body.purchase_price,
        purchase_order_ref=body.purchase_order_ref,
        actor_user_id=actor.id,
    )
    return ok(AssetRead.model_validate(asset).model_dump())


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.delete")),
):
    service = AssetService(db, payload.tenant_id)
    await service.delete_asset(asset_id=asset_id, actor_user_id=actor.id)


@router.get("/{asset_id}/identifiers")
async def list_identifiers(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    identifiers = await service.list_identifiers(asset_id)
    return ok([AssetIdentifierRead.model_validate(i).model_dump() for i in identifiers])


@router.post("/{asset_id}/identifiers", status_code=201)
async def add_identifier(
    asset_id: uuid.UUID,
    body: AssetIdentifierCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.edit")),
):
    service = AssetService(db, payload.tenant_id)
    identifier = await service.add_identifier(
        asset_id=asset_id,
        identifier_type=body.identifier_type,
        value=body.value,
        is_primary=body.is_primary,
        actor_user_id=actor.id,
    )
    return ok(AssetIdentifierRead.model_validate(identifier).model_dump())


@router.delete("/{asset_id}/identifiers/{identifier_id}", status_code=204)
async def remove_identifier(
    asset_id: uuid.UUID,  # noqa: ARG001 — must match the {asset_id} path segment; unused beyond routing
    identifier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.edit")),
):
    service = AssetService(db, payload.tenant_id)
    await service.remove_identifier(identifier_id=identifier_id, actor_user_id=actor.id)


@router.get("/{asset_id}/documents")
async def list_documents(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    documents = await service.list_documents(asset_id)
    return ok([AssetDocumentRead.model_validate(d).model_dump() for d in documents])


@router.post("/{asset_id}/documents", status_code=201)
async def upload_document(
    asset_id: uuid.UUID,
    upload: UploadFile,
    document_type: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.manage_documents")),
):
    content = await upload.read()
    service = AssetService(db, payload.tenant_id)
    document = await service.upload_document(
        asset_id=asset_id,
        filename=upload.filename or "upload",
        content_type=upload.content_type or "application/octet-stream",
        content=content,
        document_type=document_type,
        actor_user_id=actor.id,
    )
    return ok(AssetDocumentRead.model_validate(document).model_dump())


@router.get("/{asset_id}/documents/{document_id}")
async def get_document_metadata(
    asset_id: uuid.UUID,  # noqa: ARG001 — must match the {asset_id} path segment; unused beyond routing
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    document = await service.get_document_or_404(document_id)
    return ok(AssetDocumentRead.model_validate(document).model_dump())


@router.get("/{asset_id}/documents/{document_id}/content")
async def download_document_content(
    asset_id: uuid.UUID,  # noqa: ARG001 — must match the {asset_id} path segment; unused beyond routing
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetService(db, payload.tenant_id)
    document = await service.get_document_or_404(document_id)
    content = await service.read_document_content(document)
    return Response(content=content, media_type=document.content_type)


@router.delete("/{asset_id}/documents/{document_id}", status_code=204)
async def delete_document(
    asset_id: uuid.UUID,  # noqa: ARG001 — must match the {asset_id} path segment; unused beyond routing
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("assets.manage_documents")),
):
    service = AssetService(db, payload.tenant_id)
    await service.delete_document(document_id=document_id, actor_user_id=actor.id)


catalog_router = APIRouter(tags=["asset-catalog"], dependencies=[_module_gate])


@catalog_router.get("/asset-categories")
async def list_categories(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    categories = await service.list_categories(offset=pagination.offset, limit=pagination.limit)
    return ok([AssetCategoryRead.model_validate(c).model_dump() for c in categories])


@catalog_router.post("/asset-categories", status_code=201)
async def create_category(
    body: AssetCategoryCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    category = await service.create_category(name=body.name, description=body.description, actor_user_id=actor.id)
    return ok(AssetCategoryRead.model_validate(category).model_dump())


@catalog_router.get("/asset-categories/{category_id}")
async def get_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    category = await service.get_category_or_404(category_id)
    return ok(AssetCategoryRead.model_validate(category).model_dump())


@catalog_router.patch("/asset-categories/{category_id}")
async def update_category(
    category_id: uuid.UUID,
    body: AssetCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    category = await service.update_category(
        category_id=category_id, name=body.name, description=body.description, actor_user_id=actor.id
    )
    return ok(AssetCategoryRead.model_validate(category).model_dump())


@catalog_router.delete("/asset-categories/{category_id}", status_code=204)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    await service.delete_category(category_id=category_id, actor_user_id=actor.id)


@catalog_router.get("/asset-types")
async def list_types(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    types = await service.list_types(offset=pagination.offset, limit=pagination.limit)
    return ok([AssetTypeRead.model_validate(t).model_dump() for t in types])


@catalog_router.post("/asset-types", status_code=201)
async def create_type(
    body: AssetTypeCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    asset_type = await service.create_type(
        category_id=body.category_id, name=body.name, description=body.description, actor_user_id=actor.id
    )
    return ok(AssetTypeRead.model_validate(asset_type).model_dump())


@catalog_router.get("/asset-types/{type_id}")
async def get_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    asset_type = await service.get_type_or_404(type_id)
    return ok(AssetTypeRead.model_validate(asset_type).model_dump())


@catalog_router.patch("/asset-types/{type_id}")
async def update_type(
    type_id: uuid.UUID,
    body: AssetTypeUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    asset_type = await service.update_type(
        type_id=type_id, category_id=body.category_id, name=body.name, description=body.description, actor_user_id=actor.id
    )
    return ok(AssetTypeRead.model_validate(asset_type).model_dump())


@catalog_router.delete("/asset-types/{type_id}", status_code=204)
async def delete_type(
    type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    await service.delete_type(type_id=type_id, actor_user_id=actor.id)


@catalog_router.get("/vendors")
async def list_vendors(
    pagination: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    vendors = await service.list_vendors(offset=pagination.offset, limit=pagination.limit)
    return ok([VendorRead.model_validate(v).model_dump() for v in vendors])


@catalog_router.post("/vendors", status_code=201)
async def create_vendor(
    body: VendorCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    vendor = await service.create_vendor(
        name=body.name,
        contact_name=body.contact_name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        actor_user_id=actor.id,
    )
    return ok(VendorRead.model_validate(vendor).model_dump())


@catalog_router.get("/vendors/{vendor_id}")
async def get_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("assets.view")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    vendor = await service.get_vendor_or_404(vendor_id)
    return ok(VendorRead.model_validate(vendor).model_dump())


@catalog_router.patch("/vendors/{vendor_id}")
async def update_vendor(
    vendor_id: uuid.UUID,
    body: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    vendor = await service.update_vendor(
        vendor_id=vendor_id,
        name=body.name,
        contact_name=body.contact_name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        actor_user_id=actor.id,
    )
    return ok(VendorRead.model_validate(vendor).model_dump())


@catalog_router.delete("/vendors/{vendor_id}", status_code=204)
async def delete_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_catalog.manage")),
):
    service = AssetCatalogService(db, payload.tenant_id)
    await service.delete_vendor(vendor_id=vendor_id, actor_user_id=actor.id)


locations_router = APIRouter(prefix="/asset-locations", tags=["asset-locations"], dependencies=[_module_gate])


@locations_router.get("")
async def list_root_locations(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_locations.view")),
):
    service = AssetLocationService(db, payload.tenant_id)
    locations = await service.list_children(None)
    return ok([AssetLocationRead.model_validate(loc).model_dump() for loc in locations])


@locations_router.post("", status_code=201)
async def create_location(
    body: AssetLocationCreate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_locations.manage")),
):
    service = AssetLocationService(db, payload.tenant_id)
    location = await service.create_location(
        name=body.name,
        parent_location_id=body.parent_location_id,
        location_type=body.location_type,
        sort_order=body.sort_order,
        actor_user_id=actor.id,
    )
    return ok(AssetLocationRead.model_validate(location).model_dump())


@locations_router.get("/{location_id}")
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_locations.view")),
):
    service = AssetLocationService(db, payload.tenant_id)
    location = await service.get_location_or_404(location_id)
    return ok(AssetLocationRead.model_validate(location).model_dump())


@locations_router.patch("/{location_id}")
async def update_location(
    location_id: uuid.UUID,
    body: AssetLocationUpdate,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_locations.manage")),
):
    service = AssetLocationService(db, payload.tenant_id)
    fields_set = body.model_fields_set
    location = await service.update_location(
        location_id=location_id,
        name=body.name,
        parent_location_id=body.parent_location_id if "parent_location_id" in fields_set else _UNSET,
        location_type=body.location_type,
        sort_order=body.sort_order,
        actor_user_id=actor.id,
    )
    return ok(AssetLocationRead.model_validate(location).model_dump())


@locations_router.delete("/{location_id}", status_code=204)
async def delete_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    actor: User = Depends(get_current_user),
    _=Depends(require_permission("asset_locations.manage")),
):
    service = AssetLocationService(db, payload.tenant_id)
    await service.delete_location(location_id=location_id, actor_user_id=actor.id)


@locations_router.get("/{location_id}/children")
async def list_child_locations(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_locations.view")),
):
    service = AssetLocationService(db, payload.tenant_id)
    await service.get_location_or_404(location_id)
    children = await service.list_children(location_id)
    return ok([AssetLocationRead.model_validate(loc).model_dump() for loc in children])


@locations_router.get("/{location_id}/descendants")
async def list_descendant_locations(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_locations.view")),
):
    service = AssetLocationService(db, payload.tenant_id)
    descendants = await service.list_descendants(location_id)
    return ok([AssetLocationRead.model_validate(loc).model_dump() for loc in descendants])


@locations_router.get("/{location_id}/ancestors")
async def list_ancestor_locations(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(get_token_payload),
    _=Depends(require_permission("asset_locations.view")),
):
    service = AssetLocationService(db, payload.tenant_id)
    ancestors = await service.list_ancestors(location_id)
    return ok([AssetLocationRead.model_validate(loc).model_dump() for loc in ancestors])
