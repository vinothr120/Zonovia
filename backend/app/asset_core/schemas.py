import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AssetCategoryCreate(BaseModel):
    name: str
    description: str | None = None


class AssetCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AssetCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class AssetTypeCreate(BaseModel):
    category_id: uuid.UUID
    name: str
    description: str | None = None


class AssetTypeUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = None
    description: str | None = None


class AssetTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class VendorCreate(BaseModel):
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None


class VendorUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    created_at: datetime


class AssetLocationCreate(BaseModel):
    name: str
    parent_location_id: uuid.UUID | None = None
    location_type: str | None = None
    sort_order: int = 0


class AssetLocationUpdate(BaseModel):
    name: str | None = None
    parent_location_id: uuid.UUID | None = None
    location_type: str | None = None
    sort_order: int | None = None


class AssetLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_location_id: uuid.UUID | None
    location_type: str | None
    sort_order: int
    created_at: datetime


class AssetCreate(BaseModel):
    name: str
    asset_type_id: uuid.UUID
    current_location_id: uuid.UUID | None = None
    current_custodian_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = None
    purchase_order_ref: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    asset_type_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = None
    purchase_order_ref: str | None = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    asset_type_id: uuid.UUID
    current_location_id: uuid.UUID | None
    current_custodian_id: uuid.UUID | None
    current_lifecycle_state_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    purchase_date: date | None
    purchase_price: Decimal | None
    purchase_order_ref: str | None
    created_at: datetime


class AssetIdentifierCreate(BaseModel):
    identifier_type: str = Field(pattern="^(QR|BARCODE|SERIAL)$")
    value: str
    is_primary: bool = False


class AssetIdentifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    identifier_type: str
    value: str
    is_primary: bool
    created_at: datetime


class AssetDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    document_type: str | None
    storage_provider: str
    original_filename: str
    content_type: str
    size_bytes: int
    checksum: str
    uploaded_by: uuid.UUID | None
    created_at: datetime
