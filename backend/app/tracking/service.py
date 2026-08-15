import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.models import Asset
from app.asset_core.repository import AssetIdentifierRepository, AssetRepository
from app.core.audit import write_audit_log
from app.core.exceptions import NotFoundError, ValidationAppError
from app.tracking.models import TrackingEvent
from app.tracking.providers.registry import get_provider
from app.tracking.repository import TrackingEventRepository


class TrackingService:
    """Scan resolution + per-asset scan history. Depends on asset_core
    (AssetRepository, AssetIdentifierRepository.get_by_type_value — reused directly, not
    reimplemented), never the reverse."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.events = TrackingEventRepository(session, tenant_id)
        self.assets = AssetRepository(session, tenant_id)
        self.identifiers = AssetIdentifierRepository(session, tenant_id)

    async def record_scan(
        self, *, identifier_type: str, raw_value: str, note: str | None, actor_user_id: uuid.UUID | None
    ) -> tuple[Asset, TrackingEvent]:
        provider = get_provider(identifier_type)
        if provider is None:
            # Covers both a genuinely unknown identifier_type and asset_core's own SERIAL
            # type, which tracking-engine deliberately has no provider for — a serial number
            # isn't something a camera scans. asset_core's allow-list stays untouched.
            raise ValidationAppError(f"No tracking provider is registered for identifier_type '{identifier_type}'.")

        normalized_value = provider.normalize(raw_value)
        if normalized_value is None:
            raise ValidationAppError(f"'{raw_value}' is not a valid {identifier_type} value.")

        identifier = await self.identifiers.get_by_type_value(identifier_type=identifier_type, value=normalized_value)
        if identifier is None:
            # The rejected request's audit trail still survives — see core/deps.py::get_db's
            # comment: an AppError raised below still lets this write commit.
            await write_audit_log(
                self.session,
                tenant_id=self.tenant_id,
                actor_user_id=actor_user_id,
                action="tracking.scan_unresolved",
                entity_type="tracking_event",
                entity_id=None,
                new_value={"provider_type": identifier_type, "raw_value": raw_value, "normalized_value": normalized_value},
            )
            raise NotFoundError(f"No asset is identified by {identifier_type} value '{normalized_value}'.")

        asset = await self.assets.get_by_id(identifier.asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")

        event = self.events.add(
            TrackingEvent(
                asset_id=asset.id,
                provider_type=identifier_type,
                event_type="scan",
                payload={
                    "raw_value": raw_value,
                    "normalized_value": normalized_value,
                    "identifier_id": str(identifier.id),
                    "note": note,
                },
                scanned_by=actor_user_id,
            )
        )
        await self.session.flush()

        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="asset.scanned",
            entity_type="asset",
            entity_id=asset.id,
            new_value={"provider_type": identifier_type, "tracking_event_id": str(event.id)},
        )
        return asset, event

    async def list_events_for_asset(self, asset_id: uuid.UUID, *, limit: int = 50) -> list[TrackingEvent]:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return await self.events.list_for_asset(asset_id, limit=limit)
