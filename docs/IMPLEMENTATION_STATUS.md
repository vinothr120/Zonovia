# Zonovia — Implementation Status

**Last updated:** 2026-08-16, after the Inventory web UI increment (`ba609ed`).

This document tracks what's actually built and verified, as opposed to what the [architecture blueprint](architecture/Zonovia-Architecture-Blueprint.md) describes as the target design. The blueprint is the destination; this file is "where are we on the map right now," kept current at each increment so a later session — human or AI — doesn't have to reconstruct it from commit messages. When this file and the blueprint disagree on a detail, a note here explains why (usually: a blueprint ambiguity resolved during implementation, cited by section).

## How to read the status table

- **Built** — code exists and is wired in (migrations, routes, module registration).
- **Tested** — has automated test coverage that passes.
- **Verified** — independently confirmed working end-to-end (either a real backend/browser run, or, for mobile, the static checks described below — mobile has no compiler available in this environment, so "verified" means something narrower there; see its own section).

## Phase / increment status

| # | Name | Built | Tested | Verified | Notes |
|---|---|---|---|---|---|
| 0 | Platform Core (tenants, users/RBAC, auth, audit, entitlements) | ✅ | ✅ | ✅ (SQLite) | Postgres/RLS never run — see [Known gaps](#known-gaps) |
| 1 | Asset Core (registry, categories, locations, identifiers, documents) + Flow (lifecycle, custody, movement) | ✅ | ✅ | ✅ (SQLite) | |
| 2 | Tracking baseline (QR/barcode scanning) | ✅ | ✅ | ✅ (SQLite + real browser) | First frontend code (`web/`) |
| 3 | Inventory & Audit (verification cycles, reconciliation) | ✅ | ✅ | ✅ (SQLite) | `default_enabled=False` — "Zonovia Manage" tier |
| 4 | Maintenance & Warranty (tickets, warranty, service schedules) | ✅ | ✅ | ✅ (SQLite) | `default_enabled=False` — "Zonovia Manage" tier |
| 5.1 | Mobile shell + auth + online scanning (Flutter) | ✅ | — | ⚠️ static only | **Never compiled or run** — see [Mobile](#mobile-phase-51) |
| 5.2 | Mobile offline storage + sync engine | ❌ not started | — | — | Blocked behind confirming 5.1 actually runs |
| 6 | RFID / Device Gateway — backend domain | ✅ | ✅ | ✅ (SQLite) | `default_enabled=False` — "Zonovia RFID" tier (separate from Manage) |
| 6.2 | RFID / Device Gateway — separate deployable service | ❌ not started | — | — | Needs a simulated hardware adapter (no real reader available) |
| 7 | Workflow & Integrations | ❌ not started | — | — | |
| — | Web UI: Asset Core (catalog, locations, asset CRUD) | ✅ | — | ✅ (real browser) | |
| — | Web UI: Flow write actions (transition, assign/unassign, move) | ✅ | — | ✅ (real browser) | |
| — | Web UI: Inventory | ✅ | — | ✅ (real browser) | First UI for a paid-tier ("Zonovia Manage") module; first with irreversible actions (confirm dialogs) |
| — | Web UI: Maintenance | ❌ not started | — | — | Backend complete, zero UI |
| — | Web UI: RFID | ❌ not started | — | — | Backend complete, zero UI |

Backend combined test suite: **229/229 passing**, ruff clean, as of Phase 6.

## Known gaps

These are open, acknowledged, and — per explicit user decisions — not blocking further work. Don't re-raise them as new findings; they're already tracked.

### Postgres / Row-Level Security never run against a real database

Every phase's automated tests and manual verification run against SQLite (via `backend/scripts/run_dev_sqlite.py`, a dev-convenience path that uses `Base.metadata.create_all` rather than the real Alembic migrations, since the hand-written migrations use Postgres-specific SQL — RLS policies, `gen_random_uuid()`, native `JSONB` — that doesn't run on SQLite at all). This means:

- The actual RLS fail-closed tenant-isolation guarantee (§9/§17 of the blueprint) has never been exercised against real Postgres — only its *application-layer* equivalent (`TenantScopedRepository`'s explicit `WHERE tenant_id = ...` filtering) has real coverage, via `tests/test_tenant_isolation.py`. `tests/test_tenant_isolation_postgres.py` and other `@pytest.mark.postgres`-tagged tests exist and are written correctly against the real Postgres behavior, but are excluded from every CI/local run so far (`pytest -m "not postgres"`).
- The 15 Alembic migrations (`0001`–`0015`) have only been checked for structural validity (`alembic history` resolves to a single linear chain, migration files parse) — never actually applied to a live Postgres instance.
- `zonovia_app`'s automatically-inherited grants (via `ALTER DEFAULT PRIVILEGES`, migration `0003`) have never been confirmed live.

**Status:** on 2026-08-15 the user was offered three options (free-tier cloud Postgres with no local install, install Docker Desktop, or skip it) and explicitly chose to skip it and keep building. Docker Desktop is confirmed not installed on the development machine. **This is a deliberate, informed deferral, not an oversight** — treat it as closed unless the user raises it again themselves.

**What to do when it's time to close this gap:** `docker compose up --build` from the repo root, then run migrations `0001`–`0015` for real, then `pytest -m postgres`. The RLS verification steps documented in each phase's original implementation plan (now superseded by this file, but their content is preserved in git history via the plan files' role in each commit) describe the exact manual proof (`SELECT set_config('app.current_tenant_id', ...)` then confirming cross-tenant rows are invisible even to a raw SQL query as the `zonovia_app` role).

### Mobile (Phase 5.1) has never been compiled or run

No Flutter/Dart SDK exists anywhere in the environment these increments were built in. `mobile/zonovia_mobile/` was built by copying and precisely renaming the already-working native Android/iOS scaffolding from Virasaka's sibling product (SchoolAssist's Flutter app), then writing fresh Dart source against it — see `mobile/README.md` for the full explanation and the exact commands someone with a real Flutter toolchain needs to run first (`flutter pub get && flutter run`).

What *was* verified, without a compiler: the rename is complete (zero leftover `schoolasist`/`school_asist` strings anywhere in the tree, confirmed by direct grep, twice), every Dart model's `fromJson` field mapping was cross-checked by hand against the live backend Pydantic schemas (all correct, including tricky `snake_case`→`camelCase` mappings), every import resolves to a real file or declared dependency, and every config/manifest file is well-formed. What was **not** verified: whether the Dart actually compiles, whether `flutter pub get` resolves the dependency graph, whether the Gradle/Xcode builds succeed, or any runtime behavior at all (camera permission dialog, decode-to-backend round trip, token refresh).

**Status:** open, not blocking. Phase 5.2 (offline storage/sync) is explicitly sequenced *after* someone with a real Flutter toolchain confirms 5.1 runs — building more Dart on an unverified foundation was judged too risky.

### RFID hardware is simulated, not real

Phase 6 built the backend domain (Device/DeviceGateway registry, RFID tag management, batched read-ingestion with deduplication) assuming a gateway process feeds it real reads. No physical RFID reader or vendor SDK is available in this environment, and the separate `device-gateway/` deployable service (the architecturally-intended location for a real or simulated hardware adapter, per blueprint §14) has not been built yet at all — only the backend's *receiving* end exists. End-to-end verification of the ingestion endpoint used hand-crafted batch payloads via curl, not a real or even simulated reader process.

**Status:** open, not blocking. Building the actual `device-gateway/` service (with an honestly-labeled simulated adapter, since no real hardware exists to integrate against) is one of the candidate next increments.

## Architectural decisions and corrections made during implementation

Places where the blueprint was ambiguous, self-contradictory, or silent, and a concrete decision was made and should be treated as settled unless revisited:

- **Warranty's module placement** (Phase 4): the blueprint's §6/§7 tables place `Warranty` under Asset Core (bundled, free tier), but §29's packaging table and §30's roadmap both place it under the paid "Zonovia Manage" tier alongside Maintenance. Resolved in favor of the packaging/roadmap signal — `Warranty` lives in `app/maintenance/`, gated by that module's `default_enabled=False` entitlement, not `app/asset_core/`.
- **Maintenance's relationship with Flow** (Phase 4): the blueprint lists `maintenance` as depending on `flow`, which could be read as "opening a ticket should transition the asset's lifecycle state." Resolved as **read-only** — a maintenance ticket's status never calls `FlowService.transition_asset` (three concrete failure modes made write-through unsafe: the lifecycle graph is tenant-configurable and might have no valid path, only one `current_lifecycle_state_id` column exists with no "state to return to," and concurrent tickets on the same asset would race the same column). The dependency is satisfied by a read-only filter (`GET /maintenance/tickets?lifecycle_state_key=...`) instead.
- **Inventory's relationship with Flow** (Phase 3): same reasoning, same resolution — reconciling a discrepancy records the decision only; executing it (an actual location/lifecycle change) is a separate, explicit Flow API call. This is the same "record, don't execute" boundary Phase 4 later confirmed independently for Maintenance, and the blueprint's own §646 (future Workflow-engine scope) explicitly names both "maintenance approval" and "inventory reconciliation approval" side by side as the intended eventual hook point for this exact kind of cross-module action.
- **`Device`/`DeviceGateway` ownership** (Phase 6): confirmed to belong to the generic `tracking-engine` module (already bundled/free since Phase 2), not the new RFID-specific `track_rfid` module — they're shared abstraction infrastructure a future `track-vision`/`track-sense` module would also need, per the blueprint's own module dependency table.
- **RFID read deduplication key** (Phase 6): deduplicated per `(asset_id, device_id)`, not `asset_id` alone — a different reader picking up the same asset within the dedup window still produces an immediate new event, so a genuine zone transition is never silently swallowed by the window.

## Mobile (Phase 5.1)

See [Known gaps](#known-gaps) above for the compilation-status caveat. Functionally, this stage ported SchoolAssist's proven mobile conventions (hand-written `http` client with manual 401-refresh, `flutter_secure_storage` for tokens, no state-management package) and added camera-based QR/barcode scanning via `mobile_scanner`, at feature parity with `web/`'s scan page. No offline storage, no sync engine — that's Phase 5.2.

## Web (`web/`)

The only part of this project with a fully-available, fully-verifiable toolchain end to end (build, lint, and real browser-driven testing against a live backend) — every web increment has been independently re-verified this way, not just trusted from a build report.

- **Login + Scan** (Phase 2): `/login`, `/scan`.
- **Asset Core** (increment 1): catalog management (`/catalog/categories|types|vendors`), location hierarchy browser (`/locations`), full asset list/detail/create/edit (`/assets`, `/assets/new`, `/assets/:id`, `/assets/:id/edit`) with real pagination, identifiers, and documents. Client-side reference-data hooks resolve raw foreign-key ids into names, since the API deliberately doesn't denormalize them.
- **Flow write actions** (increment 2): lifecycle transition, assign/unassign custodian, and move controls on the asset detail page — computed against the tenant's actual configured lifecycle graph, never a hardcoded state list.
- **Inventory** (increment 3, `/inventory`): verification cycles, discrepancy/missing-asset reporting, reconciliation. First UI increment for a `default_enabled=False` module — a 403 from "not licensed" and a 403 from "missing permission" are deliberately indistinguishable in the UI, since the backend doesn't expose a way to tell them apart either. First increment with genuinely irreversible actions (Complete/Cancel a cycle) — these get a `window.confirm()`, unlike every reversible action in the Flow-actions increment. Asset names for report rows resolve via per-id lookups sharing `AssetDetailPage`'s query key, not a new batch endpoint.

Not yet built: any UI for Maintenance or RFID (both have complete, tested backends and zero web presence — reachable only via curl/Swagger today).

**Known side finding, not yet fixed:** `web/src/tracking/types.ts`'s `IdentifierType` (`"QR" | "BARCODE"` only) is stale relative to `web/src/assets/types.ts`'s authoritative set (`+ "SERIAL" | "RFID_EPC"`, confirmed to mirror the backend's actual allow-list). `ScanPage.tsx`'s manual-entry identifier-type select is therefore narrower than what the backend actually accepts. Found during the Inventory increment (which correctly imports from `assets/types.ts` instead), not fixed there since it's out of scope for that increment — worth a small follow-up fix.

## Next candidates (not yet decided between)

1. **Web UI for Maintenance** — tickets, warranty, service schedules. Now the more operationally central of the two remaining backend-only modules (Inventory is done).
2. **Web UI for RFID** — gateway/device registration, tag management, read history. More of an admin/setup surface than a daily-use one.
3. **Fix `tracking/types.ts`'s stale `IdentifierType`** — small, isolated, found during the Inventory increment (see the note above).
4. **Phase 7 — Workflow & Integrations** — approval engine, notifications, first external connector. New backend domain, not yet started.
5. **`device-gateway/` deployable service** — completes the Phase 6 RFID story with a real (simulated-hardware) separate deployment.
6. **Mobile Phase 5.2** — offline storage/sync, blocked behind someone confirming 5.1 compiles.
7. **Closing the Postgres/RLS gap** — see [Known gaps](#known-gaps); deliberately deferred, not urgent, but the honest bar for "production-ready" needs it eventually.
