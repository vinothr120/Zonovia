import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.models import Asset, AssetCategory, AssetDocument, AssetIdentifier, AssetLocation, AssetType, Vendor
from app.asset_core.repository import (
    AssetCategoryRepository,
    AssetDocumentRepository,
    AssetIdentifierRepository,
    AssetLocationRepository,
    AssetRepository,
    AssetTypeRepository,
    VendorRepository,
)
from app.config import settings
from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.storage import get_storage_backend, new_storage_key

_IDENTIFIER_TYPES = ("QR", "BARCODE", "SERIAL")


class AssetCatalogService:
    """Category / type / vendor CRUD — a tenant's own reference data, no lifecycle
    involvement."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.categories = AssetCategoryRepository(session, tenant_id)
        self.types = AssetTypeRepository(session, tenant_id)
        self.vendors = VendorRepository(session, tenant_id)

    # -- categories -----------------------------------------------------------------
    async def create_category(self, *, name: str, description: str | None, actor_user_id: uuid.UUID | None) -> AssetCategory:
        if await self.categories.get_by_name(name) is not None:
            raise ConflictError(f"An asset category named '{name}' already exists.")
        category = self.categories.add(AssetCategory(name=name, description=description))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_category.created",
            entity_type="asset_category",
            entity_id=category.id,
            new_value={"name": name, "description": description},
        )
        return category

    async def get_category_or_404(self, category_id: uuid.UUID) -> AssetCategory:
        category = await self.categories.get_by_id(category_id)
        if category is None:
            raise NotFoundError("Asset category not found.")
        return category

    async def update_category(
        self, *, category_id: uuid.UUID, name: str | None, description: str | None, actor_user_id: uuid.UUID | None
    ) -> AssetCategory:
        category = await self.get_category_or_404(category_id)
        old_value = {"name": category.name, "description": category.description}
        if name is not None and name != category.name:
            if await self.categories.get_by_name(name) is not None:
                raise ConflictError(f"An asset category named '{name}' already exists.")
            category.name = name
        if description is not None:
            category.description = description
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_category.updated",
            entity_type="asset_category",
            entity_id=category.id,
            old_value=old_value,
            new_value={"name": category.name, "description": category.description},
        )
        return category

    async def delete_category(self, *, category_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        category = await self.get_category_or_404(category_id)
        if await self.types.list_by_category(category.id):
            raise ConflictError("Cannot delete a category that still has asset types under it.")
        await self.categories.soft_delete(category, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_category.deleted",
            entity_type="asset_category",
            entity_id=category.id,
            old_value={"name": category.name},
        )

    async def list_categories(self, *, offset: int = 0, limit: int = 20) -> list[AssetCategory]:
        return await self.categories.list(offset=offset, limit=limit)

    # -- types ------------------------------------------------------------------------
    async def create_type(
        self, *, category_id: uuid.UUID, name: str, description: str | None, actor_user_id: uuid.UUID | None
    ) -> AssetType:
        await self.get_category_or_404(category_id)
        if await self.types.get_by_name(name) is not None:
            raise ConflictError(f"An asset type named '{name}' already exists.")
        asset_type = self.types.add(AssetType(category_id=category_id, name=name, description=description))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_type.created",
            entity_type="asset_type",
            entity_id=asset_type.id,
            new_value={"category_id": str(category_id), "name": name},
        )
        return asset_type

    async def get_type_or_404(self, type_id: uuid.UUID) -> AssetType:
        asset_type = await self.types.get_by_id(type_id)
        if asset_type is None:
            raise NotFoundError("Asset type not found.")
        return asset_type

    async def update_type(
        self,
        *,
        type_id: uuid.UUID,
        category_id: uuid.UUID | None,
        name: str | None,
        description: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> AssetType:
        asset_type = await self.get_type_or_404(type_id)
        old_value = {"category_id": str(asset_type.category_id), "name": asset_type.name}
        if category_id is not None:
            await self.get_category_or_404(category_id)
            asset_type.category_id = category_id
        if name is not None and name != asset_type.name:
            if await self.types.get_by_name(name) is not None:
                raise ConflictError(f"An asset type named '{name}' already exists.")
            asset_type.name = name
        if description is not None:
            asset_type.description = description
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_type.updated",
            entity_type="asset_type",
            entity_id=asset_type.id,
            old_value=old_value,
            new_value={"category_id": str(asset_type.category_id), "name": asset_type.name},
        )
        return asset_type

    async def delete_type(self, *, type_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        asset_type = await self.get_type_or_404(type_id)
        await self.types.soft_delete(asset_type, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_type.deleted",
            entity_type="asset_type",
            entity_id=asset_type.id,
            old_value={"name": asset_type.name},
        )

    async def list_types(self, *, offset: int = 0, limit: int = 20) -> list[AssetType]:
        return await self.types.list(offset=offset, limit=limit)

    # -- vendors ------------------------------------------------------------------------
    async def create_vendor(
        self,
        *,
        name: str,
        contact_name: str | None,
        email: str | None,
        phone: str | None,
        address: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Vendor:
        vendor = self.vendors.add(Vendor(name=name, contact_name=contact_name, email=email, phone=phone, address=address))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="vendor.created",
            entity_type="vendor",
            entity_id=vendor.id,
            new_value={"name": name},
        )
        return vendor

    async def get_vendor_or_404(self, vendor_id: uuid.UUID) -> Vendor:
        vendor = await self.vendors.get_by_id(vendor_id)
        if vendor is None:
            raise NotFoundError("Vendor not found.")
        return vendor

    async def update_vendor(
        self,
        *,
        vendor_id: uuid.UUID,
        name: str | None,
        contact_name: str | None,
        email: str | None,
        phone: str | None,
        address: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Vendor:
        vendor = await self.get_vendor_or_404(vendor_id)
        old_value = {"name": vendor.name}
        if name is not None:
            vendor.name = name
        if contact_name is not None:
            vendor.contact_name = contact_name
        if email is not None:
            vendor.email = email
        if phone is not None:
            vendor.phone = phone
        if address is not None:
            vendor.address = address
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="vendor.updated",
            entity_type="vendor",
            entity_id=vendor.id,
            old_value=old_value,
            new_value={"name": vendor.name},
        )
        return vendor

    async def delete_vendor(self, *, vendor_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        vendor = await self.get_vendor_or_404(vendor_id)
        await self.vendors.soft_delete(vendor, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="vendor.deleted",
            entity_type="vendor",
            entity_id=vendor.id,
            old_value={"name": vendor.name},
        )

    async def list_vendors(self, *, offset: int = 0, limit: int = 20) -> list[Vendor]:
        return await self.vendors.list(offset=offset, limit=limit)


class AssetLocationService:
    """Adjacency-list location hierarchy: create/update-with-cycle-guard/delete-if-empty plus
    the recursive-CTE-backed children/descendants/ancestors reads."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.locations = AssetLocationRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)

    async def get_location_or_404(self, location_id: uuid.UUID) -> AssetLocation:
        location = await self.locations.get_by_id(location_id)
        if location is None:
            raise NotFoundError("Asset location not found.")
        return location

    async def create_location(
        self,
        *,
        name: str,
        parent_location_id: uuid.UUID | None,
        location_type: str | None,
        sort_order: int,
        actor_user_id: uuid.UUID | None,
    ) -> AssetLocation:
        if parent_location_id is not None:
            await self.get_location_or_404(parent_location_id)
        if await self.locations.get_by_name_under_parent(parent_location_id=parent_location_id, name=name) is not None:
            raise ConflictError(f"A location named '{name}' already exists under this parent.")

        location = self.locations.add(
            AssetLocation(name=name, parent_location_id=parent_location_id, location_type=location_type, sort_order=sort_order)
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_location.created",
            entity_type="asset_location",
            entity_id=location.id,
            new_value={"name": name, "parent_location_id": str(parent_location_id) if parent_location_id else None},
        )
        return location

    async def update_location(
        self,
        *,
        location_id: uuid.UUID,
        name: str | None,
        parent_location_id: uuid.UUID | None | object,
        location_type: str | None,
        sort_order: int | None,
        actor_user_id: uuid.UUID | None,
    ) -> AssetLocation:
        """`parent_location_id` uses the router's `Unset` sentinel convention to distinguish
        "not provided" (leave as-is) from "explicitly set to null" (move to root) — see
        app/asset_core/router.py."""
        location = await self.get_location_or_404(location_id)
        old_value = {
            "name": location.name,
            "parent_location_id": str(location.parent_location_id) if location.parent_location_id else None,
        }

        new_parent_id = location.parent_location_id
        reparenting = parent_location_id is not _UNSET
        if reparenting:
            new_parent_id = parent_location_id  # type: ignore[assignment]
            if new_parent_id == location.id:
                raise ConflictError("A location cannot be its own parent.")
            if new_parent_id is not None:
                await self.get_location_or_404(new_parent_id)
                descendant_ids = {loc.id for loc in await self.locations.list_descendants(location.id)}
                if new_parent_id in descendant_ids:
                    raise ConflictError("Cannot move a location into one of its own descendants.")

        new_name = name if name is not None else location.name
        if reparenting or (name is not None and name != location.name):
            existing = await self.locations.get_by_name_under_parent(parent_location_id=new_parent_id, name=new_name)
            if existing is not None and existing.id != location.id:
                raise ConflictError(f"A location named '{new_name}' already exists under this parent.")

        location.name = new_name
        if reparenting:
            location.parent_location_id = new_parent_id
        if location_type is not None:
            location.location_type = location_type
        if sort_order is not None:
            location.sort_order = sort_order

        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_location.updated",
            entity_type="asset_location",
            entity_id=location.id,
            old_value=old_value,
            new_value={
                "name": location.name,
                "parent_location_id": str(location.parent_location_id) if location.parent_location_id else None,
            },
        )
        return location

    async def delete_location(self, *, location_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        location = await self.get_location_or_404(location_id)
        if await self.locations.has_children(location.id):
            raise ConflictError("Cannot delete a location that has child locations — move or delete them first.")
        if await self.assets.list_by_location(location.id):
            raise ConflictError("Cannot delete a location that still has assets assigned to it.")
        await self.locations.soft_delete(location, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_location.deleted",
            entity_type="asset_location",
            entity_id=location.id,
            old_value={"name": location.name},
        )

    async def list_children(self, parent_location_id: uuid.UUID | None) -> list[AssetLocation]:
        return await self.locations.list_children(parent_location_id)

    async def list_descendants(self, location_id: uuid.UUID) -> list[AssetLocation]:
        await self.get_location_or_404(location_id)
        return await self.locations.list_descendants(location_id)

    async def list_ancestors(self, location_id: uuid.UUID) -> list[AssetLocation]:
        await self.get_location_or_404(location_id)
        return await self.locations.list_ancestors(location_id)


class _Unset:
    """Sentinel distinguishing 'field not sent' from 'field explicitly sent as null' for
    AssetLocationService.update_location's parent_location_id — see AssetLocationUpdate in
    schemas.py, which uses Pydantic's own unset-detection instead at the router boundary."""


_UNSET = _Unset()


class AssetService:
    """Asset CRUD leaving lifecycle NULL (see Asset's docstring — only app.flow.service ever
    sets current_lifecycle_state_id); identifier add/remove with allow-list validation and
    single-primary-per-asset enforcement; document upload/download/delete via the ported
    storage module, mirroring SchoolAssist's FileService.upload exactly."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.assets = AssetRepository(session, tenant_id)
        self.identifiers = AssetIdentifierRepository(session, tenant_id)
        self.documents = AssetDocumentRepository(session, tenant_id)
        self.categories = AssetCategoryRepository(session, tenant_id)
        self.types = AssetTypeRepository(session, tenant_id)
        self.vendors = VendorRepository(session, tenant_id)
        self.locations = AssetLocationRepository(session, tenant_id)
        self.storage = get_storage_backend()

    async def get_asset_or_404(self, asset_id: uuid.UUID) -> Asset:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return asset

    async def list_assets(self, *, offset: int = 0, limit: int = 20) -> list[Asset]:
        return await self.assets.list(offset=offset, limit=limit)

    async def create_asset(
        self,
        *,
        name: str,
        asset_type_id: uuid.UUID,
        current_location_id: uuid.UUID | None,
        current_custodian_id: uuid.UUID | None,
        vendor_id: uuid.UUID | None,
        purchase_date,
        purchase_price,
        purchase_order_ref: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Asset:
        if await self.types.get_by_id(asset_type_id) is None:
            raise NotFoundError("Asset type not found.")
        if current_location_id is not None and await self.locations.get_by_id(current_location_id) is None:
            raise NotFoundError("Asset location not found.")
        if vendor_id is not None and await self.vendors.get_by_id(vendor_id) is None:
            raise NotFoundError("Vendor not found.")

        asset = self.assets.add(
            Asset(
                name=name,
                asset_type_id=asset_type_id,
                current_location_id=current_location_id,
                current_custodian_id=current_custodian_id,
                current_lifecycle_state_id=None,  # never set here — see Asset's docstring
                vendor_id=vendor_id,
                purchase_date=purchase_date,
                purchase_price=purchase_price,
                purchase_order_ref=purchase_order_ref,
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.created",
            entity_type="asset",
            entity_id=asset.id,
            new_value={"name": name, "asset_type_id": str(asset_type_id)},
        )
        return asset

    async def update_asset(
        self,
        *,
        asset_id: uuid.UUID,
        name: str | None,
        asset_type_id: uuid.UUID | None,
        vendor_id: uuid.UUID | None,
        purchase_date,
        purchase_price,
        purchase_order_ref: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> Asset:
        asset = await self.get_asset_or_404(asset_id)
        old_value = {"name": asset.name, "asset_type_id": str(asset.asset_type_id)}

        if asset_type_id is not None:
            if await self.types.get_by_id(asset_type_id) is None:
                raise NotFoundError("Asset type not found.")
            asset.asset_type_id = asset_type_id
        if vendor_id is not None:
            if await self.vendors.get_by_id(vendor_id) is None:
                raise NotFoundError("Vendor not found.")
            asset.vendor_id = vendor_id
        if name is not None:
            asset.name = name
        if purchase_date is not None:
            asset.purchase_date = purchase_date
        if purchase_price is not None:
            asset.purchase_price = purchase_price
        if purchase_order_ref is not None:
            asset.purchase_order_ref = purchase_order_ref

        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.updated",
            entity_type="asset",
            entity_id=asset.id,
            old_value=old_value,
            new_value={"name": asset.name, "asset_type_id": str(asset.asset_type_id)},
        )
        return asset

    async def delete_asset(self, *, asset_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        asset = await self.get_asset_or_404(asset_id)
        await self.assets.soft_delete(asset, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.deleted",
            entity_type="asset",
            entity_id=asset.id,
            old_value={"name": asset.name},
        )

    # -- identifiers --------------------------------------------------------------------
    async def list_identifiers(self, asset_id: uuid.UUID) -> list[AssetIdentifier]:
        await self.get_asset_or_404(asset_id)
        return await self.identifiers.list_for_asset(asset_id)

    async def add_identifier(
        self, *, asset_id: uuid.UUID, identifier_type: str, value: str, is_primary: bool, actor_user_id: uuid.UUID | None
    ) -> AssetIdentifier:
        await self.get_asset_or_404(asset_id)
        if identifier_type not in _IDENTIFIER_TYPES:
            raise ValidationAppError(f"Unsupported identifier type '{identifier_type}'. Allowed: {', '.join(_IDENTIFIER_TYPES)}.")
        if await self.identifiers.get_by_type_value(identifier_type=identifier_type, value=value) is not None:
            raise ConflictError(f"Identifier {identifier_type}:{value} is already in use.")

        if is_primary:
            # Single-primary-per-asset enforcement: setting a new primary demotes any
            # previous one rather than rejecting the request — a re-tag always wins.
            current_primary = await self.identifiers.get_primary_for_asset(asset_id)
            if current_primary is not None:
                current_primary.is_primary = False

        identifier = self.identifiers.add(
            AssetIdentifier(asset_id=asset_id, identifier_type=identifier_type, value=value, is_primary=is_primary)
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_identifier.added",
            entity_type="asset_identifier",
            entity_id=identifier.id,
            new_value={"asset_id": str(asset_id), "identifier_type": identifier_type, "value": value, "is_primary": is_primary},
        )
        return identifier

    async def remove_identifier(self, *, identifier_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        identifier = await self.identifiers.get_by_id(identifier_id)
        if identifier is None:
            raise NotFoundError("Asset identifier not found.")
        await self.identifiers.soft_delete(identifier, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_identifier.removed",
            entity_type="asset_identifier",
            entity_id=identifier.id,
            old_value={"identifier_type": identifier.identifier_type, "value": identifier.value},
        )

    # -- documents ----------------------------------------------------------------------
    async def list_documents(self, asset_id: uuid.UUID) -> list[AssetDocument]:
        await self.get_asset_or_404(asset_id)
        return await self.documents.list_for_asset(asset_id)

    async def get_document_or_404(self, document_id: uuid.UUID) -> AssetDocument:
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise NotFoundError("Asset document not found.")
        return document

    async def upload_document(
        self,
        *,
        asset_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
        document_type: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> AssetDocument:
        await self.get_asset_or_404(asset_id)
        if content_type not in settings.file_allowed_content_types:
            raise ValidationAppError(f"File type '{content_type}' is not allowed.")
        if len(content) > settings.file_max_size_bytes:
            raise ValidationAppError(f"File exceeds the maximum size of {settings.file_max_size_bytes // (1024 * 1024)} MB.")
        if len(content) == 0:
            raise ValidationAppError("Uploaded file is empty.")

        storage_key = new_storage_key(self.tenant_id, filename)
        await self.storage.save(storage_key=storage_key, content=content)

        document = self.documents.add(
            AssetDocument(
                asset_id=asset_id,
                document_type=document_type,
                storage_provider="local",
                storage_key=storage_key,
                original_filename=filename[:255],
                content_type=content_type,
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                uploaded_by=actor_user_id,
            )
        )
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_document.uploaded",
            entity_type="asset_document",
            entity_id=document.id,
            new_value={
                "asset_id": str(asset_id),
                "original_filename": document.original_filename,
                "content_type": content_type,
                "size_bytes": document.size_bytes,
            },
        )
        return document

    async def read_document_content(self, document: AssetDocument) -> bytes:
        return await self.storage.read(storage_key=document.storage_key)

    async def delete_document(self, *, document_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        document = await self.get_document_or_404(document_id)
        await self.storage.delete(storage_key=document.storage_key)
        await self.documents.soft_delete(document, deleted_by=actor_user_id)
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset_document.deleted",
            entity_type="asset_document",
            entity_id=document.id,
            old_value={"original_filename": document.original_filename},
        )
