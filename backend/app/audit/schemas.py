import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    old_value: dict | None
    new_value: dict | None
    ip_address: str | None
