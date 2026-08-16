"""RFIDProvider.normalize unit tests (mirrors test_tracking_providers.py's QR/Barcode shape),
plus proof that once registered into tracking-engine's existing provider registry, the ALREADY
EXISTING /tracking/scan endpoint transparently accepts identifier_type="RFID_EPC" — free reuse
of the human-scan endpoint, no new endpoint needed for a manual RFID lookup. This last test
deliberately never enables the track-rfid module (default_enabled=False) — /tracking/scan lives
entirely under tracking-engine (default_enabled=True), proving the reuse is genuinely free."""

from app.track_rfid.providers.rfid import RFIDProvider
from app.tracking.providers.registry import get_provider
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role


def test_rfid_provider_uppercases_and_trims():
    provider = RFIDProvider()
    assert provider.normalize("  e200001a  ") == "E200001A"


def test_rfid_provider_rejects_internal_whitespace():
    provider = RFIDProvider()
    assert provider.normalize("E200 001A") is None


def test_rfid_provider_rejects_empty_value():
    provider = RFIDProvider()
    assert provider.normalize("   ") is None


def test_rfid_provider_is_registered_under_rfid_epc():
    """Registered once at app startup via app.core.bootstrap.register_all_tracking_providers
    (app/main.py imports it at module load, which conftest.py's `from app.main import app`
    already triggers)."""
    provider = get_provider("RFID_EPC")
    assert provider is not None
    assert provider.provider_type == "RFID_EPC"


async def test_tracking_scan_transparently_accepts_rfid_epc_identifier_type(client, db):
    """The free-reuse claim, end to end — never enables track-rfid; only tracking-engine
    (default_enabled=True) and asset-core are involved."""
    tenant = await make_tenant(db, subdomain="track-rfid-provider-scan-reuse")
    role = await make_role_with_permissions(
        db,
        tenant_id=None,
        name="RfidScanReuse",
        permission_keys=["tracking.scan", "assets.view", "assets.create", "assets.edit", "asset_catalog.manage"],
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="scan@track-rfid-provider-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Laptop"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post("/api/v1/assets", json={"name": "RFID Reuse Asset", "asset_type_id": asset_type["id"]}, headers=headers)
    ).json()["data"]
    # asset_core's generic identifier endpoint stores values literally — it has no notion of
    # tracking-engine's provider normalization (see app.track_rfid.service.RfidTagService.
    # register_tag's docstring for the module that DOES normalize before storing). Stored
    # already-normalized here so the scan below resolves.
    ident_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/identifiers", json={"identifier_type": "RFID_EPC", "value": "E200001A"}, headers=headers
    )
    assert ident_resp.status_code == 201, ident_resp.text

    scan_resp = await client.post(
        "/api/v1/tracking/scan", json={"identifier_type": "RFID_EPC", "value": "e200001a"}, headers=headers
    )
    assert scan_resp.status_code == 201, scan_resp.text
    data = scan_resp.json()["data"]
    assert data["asset"]["id"] == asset["id"]
    assert data["tracking_event"]["provider_type"] == "RFID_EPC"
    assert data["tracking_event"]["payload"]["normalized_value"] == "E200001A"
