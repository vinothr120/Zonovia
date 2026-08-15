"""Warranty follows TenantService.upsert_setting's shape (GET+PUT, no DELETE): upsert is
genuinely update-in-place (never a second row for the same asset), date validation
(end_date >= start_date), and is_expired/days_remaining computed at read time — including the
end_date == today boundary (still valid through the whole of that day, so NOT expired)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.entitlements.models import TenantModuleEntitlement
from app.maintenance.models import Warranty
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _days_from_today(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


async def _make_user(db, tenant, *, email="user@maintenance-warranty-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"MaintWarrantyUser-{email}", permission_keys=_MAINTENANCE_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name="Warranty Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def test_warranty_not_found_before_any_upsert(client, db):
    tenant = await make_tenant(db, subdomain="maint-warranty-not-found")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.get(f"/api/v1/assets/{asset['id']}/warranty", headers=headers)
    assert resp.status_code == 404


async def test_end_date_before_start_date_is_rejected(client, db):
    tenant = await make_tenant(db, subdomain="maint-warranty-bad-dates")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _days_from_today(10), "end_date": _days_from_today(-10)},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_upsert_against_missing_asset_returns_404(client, db):
    tenant = await make_tenant(db, subdomain="maint-warranty-missing-asset")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.put(
        f"/api/v1/assets/{fake_id}/warranty",
        json={"start_date": _days_from_today(-10), "end_date": _days_from_today(365)},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_upsert_is_update_in_place_not_a_duplicate_row(client, db):
    """The core assertion: two upserts against the same asset leave exactly one Warranty row."""
    tenant = await make_tenant(db, subdomain="maint-warranty-upsert-in-place")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    first = await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _days_from_today(-30), "end_date": _days_from_today(335), "warranty_type": "Standard"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["data"]["id"]

    second = await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _days_from_today(-30), "end_date": _days_from_today(700), "warranty_type": "Extended"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_data = second.json()["data"]
    assert second_data["id"] == first_id
    assert second_data["warranty_type"] == "Extended"
    assert second_data["end_date"] == _days_from_today(700)

    rows = (
        (await db.execute(select(Warranty).where(Warranty.tenant_id == tenant.id, Warranty.asset_id == uuid.UUID(asset["id"]))))
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_expired_warranty_computes_is_expired_true_with_negative_days_remaining(client, db):
    tenant = await make_tenant(db, subdomain="maint-warranty-expired")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _days_from_today(-100), "end_date": _days_from_today(-10)},
        headers=headers,
    )

    resp = await client.get(f"/api/v1/assets/{asset['id']}/warranty", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_expired"] is True
    assert data["days_remaining"] == -10


async def test_end_date_equal_to_today_is_the_not_yet_expired_boundary(client, db):
    """end_date == today: still valid through the whole of that day, so is_expired is False
    and days_remaining is exactly 0 — the explicit boundary case."""
    tenant = await make_tenant(db, subdomain="maint-warranty-boundary")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _days_from_today(-30), "end_date": _today()},
        headers=headers,
    )

    resp = await client.get(f"/api/v1/assets/{asset['id']}/warranty", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_expired"] is False
    assert data["days_remaining"] == 0


async def test_future_warranty_computes_positive_days_remaining(client, db):
    tenant = await make_tenant(db, subdomain="maint-warranty-future")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    await client.put(
        f"/api/v1/assets/{asset['id']}/warranty",
        json={"start_date": _today(), "end_date": _days_from_today(30)},
        headers=headers,
    )

    resp = await client.get(f"/api/v1/assets/{asset['id']}/warranty", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_expired"] is False
    assert data["days_remaining"] == 30
