"""Populates realistic demo data across every completed Zonovia module, via the real HTTP API
(not direct service calls) so it exercises the exact same request path a browser would.

Run AFTER run_dev_sqlite.py (needs the schema + base tenants/users to already exist) and AFTER
the backend server is already running and reachable at BASE_URL.

Usage (from backend/, with the dev server already running):
    python scripts/seed_demo_data.py

Not a test, not shipped product code — local dev convenience only, mirrors app/seed.py's own
"THIS IS NOT THE PRODUCTION PATH" framing.
"""

import asyncio
import sys

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
TENANT = "acme-demo"
PASSWORD = "ChangeMe123!"


async def login(client: httpx.AsyncClient, email: str) -> dict:
    resp = await client.post(f"{BASE_URL}/auth/login", json={"tenant_slug": TENANT, "email": email, "password": PASSWORD})
    resp.raise_for_status()
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def unwrap(resp: httpx.Response):
    if resp.status_code >= 400:
        print(f"  !! {resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()["data"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        admin = await login(client, "admin@zonovia.example")
        print("Logged in as admin@zonovia.example (Tenant Admin)")

        users = unwrap(await client.get(f"{BASE_URL}/users", params={"page_size": 100}, headers=admin))
        member_id = next(u["id"] for u in users if u["email"] == "member@zonovia.example")

        # -- catalog ------------------------------------------------------------------------
        categories = {}
        for name in ("IT Equipment", "Medical Equipment", "Furniture"):
            categories[name] = unwrap(await client.post(f"{BASE_URL}/asset-categories", json={"name": name}, headers=admin))["id"]

        types = {}
        for name, cat in (
            ("Laptop", "IT Equipment"),
            ("Desktop", "IT Equipment"),
            ("Projector", "IT Equipment"),
            ("X-Ray Machine", "Medical Equipment"),
            ("MRI Scanner", "Medical Equipment"),
            ("Office Chair", "Furniture"),
            ("Standing Desk", "Furniture"),
        ):
            types[name] = unwrap(
                await client.post(f"{BASE_URL}/asset-types", json={"category_id": categories[cat], "name": name}, headers=admin)
            )["id"]

        vendors = {}
        for name in ("Dell Inc.", "Herman Miller", "Siemens Healthineers"):
            vendors[name] = unwrap(await client.post(f"{BASE_URL}/vendors", json={"name": name}, headers=admin))["id"]

        # -- locations ------------------------------------------------------------------------
        hq = unwrap(await client.post(f"{BASE_URL}/asset-locations", json={"name": "Headquarters"}, headers=admin))["id"]
        bldg_a = unwrap(
            await client.post(f"{BASE_URL}/asset-locations", json={"name": "Building A", "parent_location_id": hq}, headers=admin)
        )["id"]
        it_floor = unwrap(
            await client.post(
                f"{BASE_URL}/asset-locations", json={"name": "2nd Floor - IT", "parent_location_id": bldg_a}, headers=admin
            )
        )["id"]
        bldg_b = unwrap(
            await client.post(f"{BASE_URL}/asset-locations", json={"name": "Building B", "parent_location_id": hq}, headers=admin)
        )["id"]
        radiology = unwrap(
            await client.post(
                f"{BASE_URL}/asset-locations", json={"name": "Radiology Wing", "parent_location_id": bldg_b}, headers=admin
            )
        )["id"]
        print("Catalog + locations created")

        # -- workflow definitions (created BEFORE the assets/tickets that should trigger them) --
        await client.post(
            f"{BASE_URL}/workflow/definitions",
            json={
                "entity_type": "asset_lifecycle_transition",
                "name": "High-value asset approval",
                "condition_attribute": "purchase_price",
                "condition_operator": "gte",
                "condition_value": 5000,
                "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
            },
            headers=admin,
        )
        await client.post(
            f"{BASE_URL}/workflow/definitions",
            json={
                "entity_type": "maintenance_ticket",
                "name": "High-cost repair approval",
                "condition_attribute": "cost",
                "condition_operator": "gte",
                "condition_value": 500,
                "steps": [{"sequence_order": 1, "approver_role_key": "Tenant Admin"}],
            },
            headers=admin,
        )
        print("Workflow definitions created (purchase_price >= 5000, ticket cost >= 500)")

        # -- assets -----------------------------------------------------------------------------
        async def create_asset(name, type_name, *, vendor=None, price=None, location=None, order_ref=None):
            body = {"name": name, "asset_type_id": types[type_name]}
            if vendor:
                body["vendor_id"] = vendors[vendor]
            if price is not None:
                body["purchase_price"] = str(price)
            if location:
                body["current_location_id"] = location
            if order_ref:
                body["purchase_order_ref"] = order_ref
            return unwrap(await client.post(f"{BASE_URL}/assets", json=body, headers=admin))

        laptop1 = await create_asset("Dell Latitude 7420 #1", "Laptop", vendor="Dell Inc.", price=1200, location=it_floor, order_ref="PO-1001")
        laptop2 = await create_asset("Dell Latitude 7420 #2 (spare)", "Laptop", vendor="Dell Inc.", price=1200, location=it_floor)
        desktop = await create_asset("Dell OptiPlex Desktop", "Desktop", vendor="Dell Inc.", price=800, location=it_floor, order_ref="PO-1002")
        projector = await create_asset("Conference Room Projector", "Projector", price=300, location=bldg_a)
        xray = await create_asset("Siemens X-Ray Unit", "X-Ray Machine", vendor="Siemens Healthineers", price=85000, location=radiology, order_ref="PO-2001")
        mri = await create_asset("MRI Scanner", "MRI Scanner", vendor="Siemens Healthineers", price=250000, location=radiology, order_ref="PO-2002")
        chair = await create_asset("Herman Miller Aeron Chair", "Office Chair", vendor="Herman Miller", price=1400, location=bldg_a)
        desk = await create_asset("Standing Desk", "Standing Desk", price=450, location=it_floor)
        print(f"Created 8 assets")

        # -- identifiers --------------------------------------------------------------------
        await client.post(f"{BASE_URL}/assets/{laptop1['id']}/identifiers", json={"identifier_type": "QR", "value": "QR-LAPTOP-001", "is_primary": True}, headers=admin)
        await client.post(f"{BASE_URL}/assets/{laptop2['id']}/identifiers", json={"identifier_type": "QR", "value": "QR-LAPTOP-002", "is_primary": True}, headers=admin)
        await client.post(f"{BASE_URL}/assets/{desktop['id']}/identifiers", json={"identifier_type": "BARCODE", "value": "BC-DESKTOP-001", "is_primary": True}, headers=admin)
        await client.post(f"{BASE_URL}/assets/{chair['id']}/identifiers", json={"identifier_type": "SERIAL", "value": "SN-CHAIR-9001", "is_primary": True}, headers=admin)
        print("Identifiers added (QR/barcode/serial)")

        # -- lifecycle transitions -----------------------------------------------------------
        states = {s["key"]: s["id"] for s in unwrap(await client.get(f"{BASE_URL}/asset-lifecycle/states", headers=admin))}

        async def transition(asset, *keys):
            for key in keys:
                await client.post(f"{BASE_URL}/assets/{asset['id']}/transition", json={"to_state_id": states[key]}, headers=admin)

        await transition(laptop1, "procured", "received", "registered", "tagged", "available", "assigned")
        await transition(laptop2, "procured", "received", "registered", "tagged", "available")
        await transition(desktop, "procured", "received", "registered", "tagged", "available", "assigned")
        await transition(chair, "procured", "received", "registered", "tagged", "available")
        await transition(desk, "procured")  # deliberately left at the very first state
        await transition(projector, "procured", "received", "registered", "tagged", "available", "retired", "disposed")
        # High-value assets — each transition (including this first one) evaluates the
        # purchase_price >= 5000 workflow rule and opens a pending ApprovalInstance.
        await transition(xray, "procured", "received", "registered")
        await transition(mri, "procured")
        print("Lifecycle transitions applied (including two high-value assets that opened approvals)")

        # -- custody --------------------------------------------------------------------------
        await client.post(f"{BASE_URL}/assets/{laptop1['id']}/assign", json={"custodian_user_id": member_id, "note": "Issued for onboarding"}, headers=admin)
        await client.post(f"{BASE_URL}/assets/{desktop['id']}/assign", json={"custodian_user_id": member_id}, headers=admin)
        print("Custody assigned to member@zonovia.example")

        # -- resolve one of the two high-value approvals, leave the other pending -------------
        xray_transitions = unwrap(await client.get(f"{BASE_URL}/assets/{xray['id']}/history", headers=admin))
        first_xray_transition_id = next(e["data"]["id"] for e in xray_transitions if e["entry_type"] == "lifecycle_transition")
        xray_instances = unwrap(
            await client.get(
                f"{BASE_URL}/workflow/instances",
                params={"entity_type": "asset_lifecycle_transition", "entity_id": first_xray_transition_id},
                headers=admin,
            )
        )
        if xray_instances:
            step_id = xray_instances[0]["steps"][0]["id"]
            await client.post(f"{BASE_URL}/workflow/instance-steps/{step_id}/approve", headers=admin)
            print("Approved the X-Ray unit's high-value transition (MRI's is left pending, for demo)")

        # -- maintenance ------------------------------------------------------------------------
        await client.put(
            f"{BASE_URL}/assets/{laptop1['id']}/warranty",
            json={"vendor_id": vendors["Dell Inc."], "warranty_type": "Standard 3-year", "start_date": "2025-01-15", "end_date": "2028-01-15"},
            headers=admin,
        )
        await client.put(
            f"{BASE_URL}/assets/{mri['id']}/warranty",
            json={"vendor_id": vendors["Siemens Healthineers"], "warranty_type": "Extended service", "start_date": "2024-06-01", "end_date": "2026-06-01"},
            headers=admin,
        )
        schedule = unwrap(
            await client.post(
                f"{BASE_URL}/maintenance/schedules", json={"asset_id": xray["id"], "name": "Quarterly calibration", "interval_days": 90}, headers=admin
            )
        )
        await client.post(f"{BASE_URL}/maintenance/schedules/{schedule['id']}/record-service", json={}, headers=admin)

        ticket_open = unwrap(
            await client.post(
                f"{BASE_URL}/maintenance/tickets",
                json={"asset_id": laptop2["id"], "title": "Keyboard not responding", "priority": "low", "cost": "45.00"},
                headers=admin,
            )
        )
        ticket_completed = unwrap(
            await client.post(
                f"{BASE_URL}/maintenance/tickets",
                json={"asset_id": desktop["id"], "title": "Replace power supply", "priority": "medium", "cost": "80.00"},
                headers=admin,
            )
        )
        await client.post(f"{BASE_URL}/maintenance/tickets/{ticket_completed['id']}/start", headers=admin)
        await client.post(
            f"{BASE_URL}/maintenance/tickets/{ticket_completed['id']}/complete",
            json={"resolution_note": "Power supply replaced under warranty."},
            headers=admin,
        )
        ticket_highcost = unwrap(
            await client.post(
                f"{BASE_URL}/maintenance/tickets",
                json={"asset_id": mri["id"], "title": "MRI coolant system repair", "priority": "urgent", "cost": "750.00"},
                headers=admin,
            )
        )
        print("Maintenance: 2 warranties, 1 service schedule (serviced once), 3 tickets (1 open, 1 completed, 1 high-cost -> pending approval)")

        # -- inventory --------------------------------------------------------------------------
        cycle_done = unwrap(await client.post(f"{BASE_URL}/inventory/cycles", json={"name": "Q1 IT Floor Audit", "root_location_id": it_floor}, headers=admin))
        await client.post(f"{BASE_URL}/inventory/cycles/{cycle_done['id']}/start", headers=admin)
        await client.post(f"{BASE_URL}/inventory/cycles/{cycle_done['id']}/counts", json={"identifier_type": "QR", "value": "QR-LAPTOP-001"}, headers=admin)
        await client.post(f"{BASE_URL}/inventory/cycles/{cycle_done['id']}/counts", json={"identifier_type": "BARCODE", "value": "BC-DESKTOP-001"}, headers=admin)
        await client.post(
            f"{BASE_URL}/inventory/cycles/{cycle_done['id']}/reconciliations",
            json={"asset_id": laptop2["id"], "action_type": "location_corrected", "note": "Found in storage room, not on the floor"},
            headers=admin,
        )
        await client.post(f"{BASE_URL}/inventory/cycles/{cycle_done['id']}/complete", headers=admin)

        cycle_active = unwrap(await client.post(f"{BASE_URL}/inventory/cycles", json={"name": "Radiology Wing Spot Check"}, headers=admin))
        await client.post(f"{BASE_URL}/inventory/cycles/{cycle_active['id']}/start", headers=admin)
        print("Inventory: 1 completed cycle (with a reconciliation), 1 active in-progress cycle")

        # -- RFID -----------------------------------------------------------------------------
        gateway = unwrap(
            await client.post(f"{BASE_URL}/tracking/gateways", json={"name": "Warehouse Reader 1", "location_id": it_floor}, headers=admin)
        )
        gateway_id = gateway["gateway"]["id"]
        api_key = gateway["api_key"]
        device = unwrap(
            await client.post(
                f"{BASE_URL}/tracking/gateways/{gateway_id}/devices",
                json={"device_type": "RFID_READER", "vendor": "Impinj", "model": "R700", "serial_number": "IMP-R700-0007"},
                headers=admin,
            )
        )
        await client.post(f"{BASE_URL}/rfid/tags", json={"asset_id": chair["id"], "epc": "E200001B0C0D0E0F00001234", "tag_type": "passive"}, headers=admin)
        await client.post(f"{BASE_URL}/rfid/tags", json={"asset_id": desk["id"], "epc": "E200001B0C0D0E0F00005678", "tag_type": "passive"}, headers=admin)

        gw_headers = {"X-Gateway-Tenant-Slug": TENANT, "X-Gateway-Api-Key": api_key}
        await client.post(
            f"{BASE_URL}/rfid/ingest",
            json={"reads": [{"device_id": device["id"], "tag_epc": "E200001B0C0D0E0F00001234", "rssi": -42}]},
            headers=gw_headers,
        )
        print(f"RFID: 1 gateway + 1 device, 2 tags registered, 1 simulated read ingested (gateway API key: {api_key})")

        print("\nDemo data seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
