import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.asset_core.repository import AssetIdentifierRepository
from app.asset_core.service import AssetService
from app.config import settings
from app.core.audit import write_audit_log
from app.core.base_model import utcnow
from app.core.exceptions import NotFoundError, ValidationAppError
from app.track_rfid.models import _TAG_TYPES, RfidReadEvent, RfidTag
from app.track_rfid.repository import RfidReadEventRepository, RfidTagRepository
from app.tracking.models import TrackingEvent
from app.tracking.providers.registry import get_provider
from app.tracking.repository import DeviceRepository, TrackingEventRepository


class RfidTagService:
    """Register/read RFID tags. Depends on asset_core.AssetService directly (never
    reimplements identifier creation) — register_tag creates the AssetIdentifier via
    AssetService.add_identifier's own conflict-checked, allow-list-validated path, then the
    1:1 RfidTag row, all inside the caller's existing transaction (one commit at the request
    boundary, per app/core/deps.py::get_db)."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.tags = RfidTagRepository(session, tenant_id)
        self.identifiers = AssetIdentifierRepository(session, tenant_id)
        self.asset_service = AssetService(session, tenant_id)

    async def register_tag(
        self, *, asset_id: uuid.UUID, epc: str, tag_type: str, actor_user_id: uuid.UUID | None
    ) -> tuple[RfidTag, str]:
        """Returns (tag, normalized_epc) — the router needs the normalized form (not the raw
        `epc` argument) to render a response that matches what's actually stored."""
        if tag_type not in _TAG_TYPES:
            raise ValidationAppError(f"Unsupported tag_type '{tag_type}'. Allowed: {', '.join(_TAG_TYPES)}.")

        # Stored NORMALIZED (via RFIDProvider — same function RfidIngestionService.
        # ingest_batch and /tracking/scan both normalize an incoming raw EPC through) so a
        # later raw read/scan resolves against exactly what's stored here, regardless of the
        # case/whitespace it arrives in. asset_core's add_identifier stores values literally —
        # it has no notion of tracking-engine's provider normalization — so this is the one
        # place in the request path responsible for keeping the two in sync.
        provider = get_provider("RFID_EPC")
        normalized_epc = provider.normalize(epc) if provider is not None else epc
        if normalized_epc is None:
            raise ValidationAppError(f"'{epc}' is not a valid RFID_EPC value.")

        # asset_core's own conflict-checked path: raises NotFoundError if asset_id doesn't
        # exist, ConflictError if the EPC is already in use by any identifier (bare or
        # RfidTag-backed) — see the module's implementation plan's "duplicate EPC 409" case.
        identifier = await self.asset_service.add_identifier(
            asset_id=asset_id, identifier_type="RFID_EPC", value=normalized_epc, is_primary=False, actor_user_id=actor_user_id
        )

        tag = self.tags.add(RfidTag(asset_identifier_id=identifier.id, asset_id=asset_id, tag_type=tag_type))
        await self.session.flush()
        await write_audit_log(
            self.session,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            action="rfid_tag.registered",
            entity_type="rfid_tag",
            entity_id=tag.id,
            new_value={"asset_id": str(asset_id), "epc": normalized_epc, "tag_type": tag_type},
        )
        return tag, normalized_epc

    async def get_tag_for_asset(self, asset_id: uuid.UUID) -> RfidTag:
        tag = await self.tags.get_by_asset_id(asset_id)
        if tag is None:
            raise NotFoundError("No RFID tag is registered for this asset.")
        return tag

    async def get_tag_epc(self, tag: RfidTag) -> str:
        """The EPC itself lives on the linked AssetIdentifier, not on RfidTag — see
        RfidTagRead's docstring. Used by the router to merge it into the read shape."""
        identifier = await self.identifiers.get_by_id(tag.asset_identifier_id)
        return identifier.value if identifier is not None else ""

    async def list_tags(self, *, offset: int = 0, limit: int = 20) -> list[RfidTag]:
        return await self.tags.list_all(offset=offset, limit=limit)


class RfidIngestionService:
    """Batched raw-read ingestion — the gateway-auth-only side of Phase 6. Deliberately does
    NOT call TrackingService.record_scan: that method's unresolved-audit-log write and
    human-actor (scanned_by) assumption don't apply to gateway ingestion (see
    RfidReadEvent's docstring and the module's implementation plan's "unresolved raw reads
    never write to audit_logs" design decision). Instead reuses
    AssetIdentifierRepository.get_by_type_value and the TrackingProvider registry directly,
    and writes TrackingEvent rows itself via TrackingEventRepository."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.reads = RfidReadEventRepository(session, tenant_id)
        self.tags = RfidTagRepository(session, tenant_id)
        self.devices = DeviceRepository(session, tenant_id)
        self.identifiers = AssetIdentifierRepository(session, tenant_id)
        self.events = TrackingEventRepository(session, tenant_id)

    async def ingest_batch(
        self, *, gateway_id: uuid.UUID, reads: list, dedup_window_seconds: int | None = None
    ) -> dict[str, int]:
        """`reads` is a list of app.track_rfid.schemas.RfidRawRead. Per read: validate
        device_id belongs to gateway_id (else `invalid`, skip entirely — no RfidReadEvent
        written, since it can't be attributed to a real device on this gateway); resolve
        tag_epc via RFIDProvider.normalize + AssetIdentifierRepository.get_by_type_value;
        ALWAYS insert one RfidReadEvent (resolved or not — the durable forensic record, see
        RfidReadEvent's docstring); if resolved, dedup against a recent TrackingEvent keyed on
        (asset_id, device_id) — NOT asset_id alone (see
        TrackingEventRepository.get_recent_for_asset_device's docstring) — reusing its id if
        found, else inserting a new TrackingEvent directly (never via
        TrackingService.record_scan). Returns live counts, never per-read echoes."""
        window = dedup_window_seconds if dedup_window_seconds is not None else settings.rfid_dedup_window_seconds
        provider = get_provider("RFID_EPC")
        counts = {"resolved": 0, "unresolved": 0, "invalid": 0, "new_tracking_events": 0, "deduped": 0}

        for raw in reads:
            device = await self.devices.get_by_id(raw.device_id)
            if device is None or device.gateway_id != gateway_id:
                counts["invalid"] += 1
                continue

            normalized_epc = provider.normalize(raw.tag_epc) if provider is not None else raw.tag_epc
            identifier = (
                await self.identifiers.get_by_type_value(identifier_type="RFID_EPC", value=normalized_epc)
                if normalized_epc is not None
                else None
            )

            asset_id = identifier.asset_id if identifier is not None else None
            tracking_event_id = None

            if asset_id is not None:
                counts["resolved"] += 1
                since = utcnow() - timedelta(seconds=window)
                existing_event = await self.events.get_recent_for_asset_device(asset_id, raw.device_id, "RFID_EPC", since)
                if existing_event is not None:
                    tracking_event_id = existing_event.id
                    counts["deduped"] += 1
                else:
                    new_event = self.events.add(
                        TrackingEvent(
                            asset_id=asset_id,
                            device_id=raw.device_id,
                            provider_type="RFID_EPC",
                            event_type="rfid_read",
                            payload={
                                "raw_value": raw.tag_epc,
                                "normalized_value": normalized_epc,
                                "identifier_id": str(identifier.id),
                                "rssi": raw.rssi,
                            },
                            scanned_by=None,
                        )
                    )
                    await self.session.flush()
                    tracking_event_id = new_event.id
                    counts["new_tracking_events"] += 1

                tag = await self.tags.get_by_asset_identifier_id(identifier.id)
                if tag is not None:
                    tag.last_device_id = raw.device_id
                    tag.last_rssi = raw.rssi
                    tag.last_read_at = utcnow()
            else:
                counts["unresolved"] += 1

            self.reads.add(
                RfidReadEvent(
                    gateway_id=gateway_id,
                    device_id=raw.device_id,
                    tag_epc=raw.tag_epc,
                    rssi=raw.rssi,
                    asset_id=asset_id,
                    tracking_event_id=tracking_event_id,
                )
            )
            device.last_seen_at = utcnow()

        await self.session.flush()
        return counts

    async def list_read_events(
        self,
        *,
        resolved: bool | None = None,
        device_id: uuid.UUID | None = None,
        tag_epc: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RfidReadEvent]:
        return await self.reads.list_filtered(resolved=resolved, device_id=device_id, tag_epc=tag_epc, offset=offset, limit=limit)
