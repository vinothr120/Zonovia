"""ServiceSchedule's computed-not-stored next_due_at/is_overdue: the never-serviced-yet edge
case (computed from created_at, not last_serviced_at, since last_serviced_at is None),
recomputation after record_service, the overdue boundary (next_due_at == today is NOT overdue),
soft-delete, and the due report's overdue/upcoming split."""

from datetime import UTC, date, datetime, timedelta

from app.entitlements.models import TenantModuleEntitlement
from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_MAINTENANCE_PERMS = [
    "maintenance.view",
    "maintenance.manage_tickets",
    "maintenance.manage_warranty",
    "maintenance.manage_schedules",
]
_CATALOG_PERMS = ["assets.view", "assets.create", "asset_catalog.manage"]


def _today() -> date:
    return datetime.now(UTC).date()


async def _make_user(db, tenant, *, email="user@maintenance-schedules-test.example"):
    role = await make_role_with_permissions(
        db, tenant_id=None, name=f"MaintScheduleUser-{email}", permission_keys=_MAINTENANCE_PERMS + _CATALOG_PERMS
    )
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email=email, role=role)
    db.add(TenantModuleEntitlement(tenant_id=tenant.id, module_key="maintenance", enabled=True, source="manual"))
    return user, token


async def _create_asset(client, headers, name="Schedule Test Asset"):
    category = (await client.post("/api/v1/asset-categories", json={"name": f"Cat - {name}"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": f"Type - {name}"}, headers=headers)
    ).json()["data"]
    asset = (await client.post("/api/v1/assets", json={"name": name, "asset_type_id": asset_type["id"]}, headers=headers)).json()[
        "data"
    ]
    return asset


async def _create_schedule(client, headers, asset_id, *, name="Filter Change", interval_days=30):
    resp = await client.post(
        "/api/v1/maintenance/schedules",
        json={"asset_id": asset_id, "name": name, "interval_days": interval_days},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_interval_days_must_be_positive(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-bad-interval")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(
        "/api/v1/maintenance/schedules", json={"asset_id": asset["id"], "name": "Bad", "interval_days": 0}, headers=headers
    )
    assert resp.status_code == 422


async def test_never_serviced_next_due_at_is_computed_from_created_at(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-never-serviced")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"], interval_days=15)

    assert schedule["last_serviced_at"] is None
    created_at = datetime.fromisoformat(schedule["created_at"]).date()
    assert schedule["next_due_at"] == (created_at + timedelta(days=15)).isoformat()


async def test_record_service_recomputes_next_due_at(client, db):
    """First record_service (defaulting to today) sets the baseline; a second record_service
    with a different explicit serviced_at proves next_due_at is recomputed off the NEW
    last_serviced_at each time, not left stale from the first call. (A single record_service
    against a same-day-created, never-serviced schedule trivially computes the same
    next_due_at as the never-serviced case, since both start from "today" — that edge case is
    covered by test_never_serviced_next_due_at_is_computed_from_created_at instead.)"""
    tenant = await make_tenant(db, subdomain="maint-schedule-record-service")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"], interval_days=30)

    first = await client.post(f"/api/v1/maintenance/schedules/{schedule['id']}/record-service", json={}, headers=headers)
    assert first.status_code == 200, first.text
    first_data = first.json()["data"]
    assert first_data["last_serviced_at"] == _today().isoformat()
    assert first_data["next_due_at"] == (_today() + timedelta(days=30)).isoformat()

    earlier_service_date = (_today() - timedelta(days=5)).isoformat()
    second = await client.post(
        f"/api/v1/maintenance/schedules/{schedule['id']}/record-service",
        json={"serviced_at": earlier_service_date},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_data = second.json()["data"]
    assert second_data["last_serviced_at"] == earlier_service_date
    assert second_data["next_due_at"] == (_today() + timedelta(days=25)).isoformat()
    assert second_data["next_due_at"] != first_data["next_due_at"]


async def test_record_service_with_explicit_serviced_at(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-explicit-service")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"], interval_days=10)

    serviced_at = (_today() - timedelta(days=5)).isoformat()
    resp = await client.post(
        f"/api/v1/maintenance/schedules/{schedule['id']}/record-service", json={"serviced_at": serviced_at}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["last_serviced_at"] == serviced_at
    assert data["next_due_at"] == (_today() + timedelta(days=5)).isoformat()


async def test_overdue_boundary_next_due_at_equal_to_today_is_not_overdue(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-boundary-not-overdue")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"], interval_days=5)
    serviced_at = (_today() - timedelta(days=5)).isoformat()  # next_due_at == today exactly

    resp = await client.post(
        f"/api/v1/maintenance/schedules/{schedule['id']}/record-service", json={"serviced_at": serviced_at}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["next_due_at"] == _today().isoformat()
    assert data["is_overdue"] is False


async def test_overdue_boundary_next_due_at_one_day_past_is_overdue(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-boundary-overdue")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"], interval_days=5)
    serviced_at = (_today() - timedelta(days=6)).isoformat()  # next_due_at == yesterday

    resp = await client.post(
        f"/api/v1/maintenance/schedules/{schedule['id']}/record-service", json={"serviced_at": serviced_at}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["next_due_at"] == (_today() - timedelta(days=1)).isoformat()
    assert data["is_overdue"] is True


async def test_soft_deleted_schedule_returns_404_and_is_excluded_from_listing(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-soft-delete")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    schedule = await _create_schedule(client, headers, asset["id"])

    delete_resp = await client.delete(f"/api/v1/maintenance/schedules/{schedule['id']}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/maintenance/schedules/{schedule['id']}", headers=headers)
    assert get_resp.status_code == 404

    list_resp = await client.get(f"/api/v1/maintenance/schedules?asset_id={asset['id']}", headers=headers)
    assert list_resp.status_code == 200
    assert schedule["id"] not in [s["id"] for s in list_resp.json()["data"]]


async def test_due_report_splits_overdue_and_upcoming_sorted_by_next_due_at(client, db):
    tenant = await make_tenant(db, subdomain="maint-schedule-report-split")
    _user, token = await _make_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)

    overdue_schedule = await _create_schedule(client, headers, asset["id"], name="Overdue One", interval_days=5)
    await client.post(
        f"/api/v1/maintenance/schedules/{overdue_schedule['id']}/record-service",
        json={"serviced_at": (_today() - timedelta(days=20)).isoformat()},
        headers=headers,
    )

    upcoming_schedule = await _create_schedule(client, headers, asset["id"], name="Upcoming One", interval_days=60)

    resp = await client.get("/api/v1/maintenance/schedules/report", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    overdue_ids = [s["id"] for s in data["overdue"]]
    upcoming_ids = [s["id"] for s in data["upcoming"]]
    assert overdue_schedule["id"] in overdue_ids
    assert upcoming_schedule["id"] in upcoming_ids
    assert overdue_schedule["id"] not in upcoming_ids
    assert upcoming_schedule["id"] not in overdue_ids

    # Sorted ascending by next_due_at within each bucket.
    for bucket in (data["overdue"], data["upcoming"]):
        due_dates = [s["next_due_at"] for s in bucket]
        assert due_dates == sorted(due_dates)
