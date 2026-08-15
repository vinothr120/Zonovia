import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str
    subdomain: str = Field(pattern="^[a-z0-9-]{3,100}$")
    subscription_tier: str = "basic"


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    subdomain: str
    subscription_tier: str
    status: str
    created_at: datetime


class TenantSettingUpsert(BaseModel):
    value: Any


class TenantSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    updated_at: datetime
