"""RfidIngestionService.ingest_batch via POST /rfid/ingest — the phase's core design decisions,
proven end to end: N reads for the same (asset, device) within the dedup window collapse to a
single TrackingEvent; after the window, a genuinely new one is created; a DIFFERENT device
reading the SAME asset within the window is NOT deduped (proving the dedup key is
(asset_id, device_id), not asset_id alone — a genuine zone transition must always surface);
an unresolved EPC still writes an RfidReadEvent (asset_id=None, tracking_event_id=None) but
writes ZERO new audit_logs rows — contrasted directly against test_tracking.py's
test_scan_with_unresolved_code_returns_404_writes_audit_log_and_no_tracking_event, which DOES
write one; and an invalid device_id is counted, not fatal to the rest of the batch."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.audit.models import AuditLog
from app.core.base_model import utcnow
from app.entitlements.models import TenantModuleEntitlement
from app.track_rfid.models import RfidReadEvent
from app.tracking.models import TrackingEvent
from tests.conftest import gateway_headers, make_role_with_permissions, make_tenant, make_user_with_role

_ADMIN_PERMS = [
    "assets.view",
    "assets.create",
    "asset_catalog.manage",
    "tracking.manage_gateways",
    "tracking.manage_devices",
    "track_rfid.manage_tags",
    "track_rfid.view",
]


async def _setup(client, db, *, subdomain: str):
    tenant = await make_tenant(db, subdomain=subdomain)
    role = await make_role_with_permissions(db, tenant_id=None, name="RfidIngestAdmin", permission_keys=_ADMIN_PERMS)
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email=f"admin@{subdomain}.example", role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="track-rfid", enabled=True, source="manual"))
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post("/api/v1/assets", json={"name": "Dedup Asset", "asset_type_id": asset_type["id"]}, headers=headers)
    ).json()["data"]
    tag_resp = await client.post("/api/v1/rfid/tags", json={"asset_id": asset["id"], "epc": "E200DEDUP"}, headers=headers)
    assert tag_resp.status_code == 201, tag_resp.text

    gw_resp = await client.post("/api/v1/tracking/gateways", json={"name": "Dedup Gateway"}, headers=headers)
    gateway = gw_resp.json()["data"]["gateway"]
    raw_key = gw_resp.json()["data"]["api_key"]

    device_a_resp = await client.post(
        f"/api/v1/tracking/gateways/{gateway['id']}/devices", json={"device_type": "RFID_READER"}, headers=headers
    )
    device_a = device_a_resp.json()["data"]
    device_b_resp = await client.post(
        f"/api/v1/tracking/gateways/{gateway['id']}/devices", json={"device_type": "RFID_READER"}, headers=headers
    )
    device_b = device_b_resp.json()["data"]

    gw_auth_headers = gateway_headers(tenant_slug=tenant.subdomain, raw_api_key=raw_key)
    return tenant, headers, asset, gateway, device_a, device_b, gw_auth_headers


async def _tracking_events_for_asset(db, tenant_id, asset_id: str) -> list[TrackingEvent]:
    stmt = select(TrackingEvent).where(TrackingEvent.tenant_id == tenant_id, TrackingEvent.asset_id == uuid.UUID(asset_id))
    return list((await db.execute(stmt)).scalars().all())


async def _read_events(db, tenant_id) -> list[RfidReadEvent]:
    stmt = select(RfidReadEvent).where(RfidReadEvent.tenant_id == tenant_id)
    return list((await db.execute(stmt)).scalars().all())


async def test_repeated_reads_same_asset_and_device_within_window_dedupe_to_one_event(client, db):
    tenant, _headers, asset, _gateway, device_a, _device_b, gw_headers = await _setup(
        client, db, subdomain="rfid-dedup-same-device"
    )

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={
            "reads": [
                {"device_id": device_a["id"], "tag_epc": "E200DEDUP", "rssi": -40},
                {"device_id": device_a["id"], "tag_epc": "E200DEDUP", "rssi": -41},
                {"device_id": device_a["id"], "tag_epc": "E200DEDUP", "rssi": -42},
            ]
        },
        headers=gw_headers,
    )
    assert resp.status_code == 201, resp.text
    counts = resp.json()["data"]
    assert counts == {"resolved": 3, "unresolved": 0, "invalid": 0, "new_tracking_events": 1, "deduped": 2}

    events = await _tracking_events_for_asset(db, tenant.id, asset["id"])
    assert len(events) == 1
    assert str(events[0].device_id) == device_a["id"]

    read_events = await _read_events(db, tenant.id)
    assert len(read_events) == 3
    assert all(r.tracking_event_id == events[0].id for r in read_events)


async def test_read_after_dedup_window_creates_a_second_event(client, db):
    tenant, _headers, asset, _gateway, device_a, _device_b, gw_headers = await _setup(
        client, db, subdomain="rfid-dedup-after-window"
    )

    first = await client.post(
        "/api/v1/rfid/ingest", json={"reads": [{"device_id": device_a["id"], "tag_epc": "E200DEDUP"}]}, headers=gw_headers
    )
    assert first.json()["data"]["new_tracking_events"] == 1

    # Backdate the TrackingEvent past the default 300s dedup window — same underlying SQLite
    # engine as the HTTP client's own sessions (see conftest.py's engine/session_factory
    # fixtures), so this commit is visible to the next request.
    events_before = await _tracking_events_for_asset(db, tenant.id, asset["id"])
    assert len(events_before) == 1
    events_before[0].occurred_at = utcnow() - timedelta(seconds=400)
    await db.commit()

    second = await client.post(
        "/api/v1/rfid/ingest", json={"reads": [{"device_id": device_a["id"], "tag_epc": "E200DEDUP"}]}, headers=gw_headers
    )
    assert second.status_code == 201, second.text
    counts = second.json()["data"]
    assert counts == {"resolved": 1, "unresolved": 0, "invalid": 0, "new_tracking_events": 1, "deduped": 0}

    events_after = await _tracking_events_for_asset(db, tenant.id, asset["id"])
    assert len(events_after) == 2


async def test_different_device_same_asset_within_window_is_not_deduped(client, db):
    """The dedup-key proof: (asset_id, device_id), NOT asset_id alone. A different device
    reading the same asset within the SAME window as an existing event must produce an
    IMMEDIATE second TrackingEvent — a genuine zone transition (tag moving from Reader A to
    Reader B) must always surface, never be silently swallowed."""
    tenant, _headers, asset, _gateway, device_a, device_b, gw_headers = await _setup(
        client, db, subdomain="rfid-dedup-diff-device"
    )

    first = await client.post(
        "/api/v1/rfid/ingest", json={"reads": [{"device_id": device_a["id"], "tag_epc": "E200DEDUP"}]}, headers=gw_headers
    )
    assert first.json()["data"]["new_tracking_events"] == 1

    second = await client.post(
        "/api/v1/rfid/ingest", json={"reads": [{"device_id": device_b["id"], "tag_epc": "E200DEDUP"}]}, headers=gw_headers
    )
    assert second.status_code == 201, second.text
    counts = second.json()["data"]
    # Immediate new event, NOT deduped, even though the first read for device_a happened
    # moments ago (well within the 300s window) — the window is irrelevant here because the
    # dedup key itself doesn't match.
    assert counts == {"resolved": 1, "unresolved": 0, "invalid": 0, "new_tracking_events": 1, "deduped": 0}

    events = await _tracking_events_for_asset(db, tenant.id, asset["id"])
    assert len(events) == 2
    assert {str(e.device_id) for e in events} == {device_a["id"], device_b["id"]}


async def test_unresolved_read_writes_read_event_but_zero_audit_logs(client, db):
    """Direct contrast against test_tracking.py's
    test_scan_with_unresolved_code_returns_404_writes_audit_log_and_no_tracking_event, whose
    Phase 2 human-scan path DOES write a tracking.scan_unresolved audit row. RFID ingestion
    deliberately does not — see RfidReadEvent's docstring."""
    tenant, _headers, _asset, _gateway, device_a, _device_b, gw_headers = await _setup(
        client, db, subdomain="rfid-dedup-unresolved"
    )

    audit_count_before = len((await db.execute(select(AuditLog).where(AuditLog.tenant_id == tenant.id))).scalars().all())

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={"reads": [{"device_id": device_a["id"], "tag_epc": "NO-SUCH-EPC"}]},
        headers=gw_headers,
    )
    assert resp.status_code == 201, resp.text
    counts = resp.json()["data"]
    assert counts == {"resolved": 0, "unresolved": 1, "invalid": 0, "new_tracking_events": 0, "deduped": 0}

    read_events = await _read_events(db, tenant.id)
    assert len(read_events) == 1
    assert read_events[0].asset_id is None
    assert read_events[0].tracking_event_id is None
    assert read_events[0].tag_epc == "NO-SUCH-EPC"

    audit_count_after = len((await db.execute(select(AuditLog).where(AuditLog.tenant_id == tenant.id))).scalars().all())
    assert audit_count_after == audit_count_before  # zero NEW audit_logs rows


async def test_invalid_device_id_is_counted_but_not_fatal_to_the_batch(client, db):
    tenant, _headers, _asset, _gateway, device_a, _device_b, gw_headers = await _setup(
        client, db, subdomain="rfid-dedup-invalid-device"
    )

    resp = await client.post(
        "/api/v1/rfid/ingest",
        json={
            "reads": [
                {"device_id": "00000000-0000-0000-0000-000000000000", "tag_epc": "E200DEDUP"},
                {"device_id": device_a["id"], "tag_epc": "E200DEDUP"},
            ]
        },
        headers=gw_headers,
    )
    assert resp.status_code == 201, resp.text
    counts = resp.json()["data"]
    assert counts == {"resolved": 1, "unresolved": 0, "invalid": 1, "new_tracking_events": 1, "deduped": 0}

    read_events = await _read_events(db, tenant.id)
    # No RfidReadEvent for the invalid-device read — it can't be attributed to a real device.
    assert len(read_events) == 1
    assert str(read_events[0].device_id) == device_a["id"]
