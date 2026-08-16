# Zonovia

Zonovia is Virasaka's enterprise asset-visibility platform — RFID, computer vision, and IoT/BLE sensing fused with an AI layer into one live model of every physical asset an organization owns. See [`docs/architecture/Zonovia-Architecture-Blueprint.md`](docs/architecture/Zonovia-Architecture-Blueprint.md) for the full product and technical architecture.

## Current status

**See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for the up-to-date, phase-by-phase build/test/verify status, known gaps (Postgres/RLS never run, mobile never compiled, RFID hardware simulated), and architectural decisions made along the way — kept current at every increment, read that file first, not this summary.**

As of this writing: Platform Core, Asset Core + Flow, Tracking (QR/barcode), Inventory & Audit, Maintenance & Warranty, and RFID/Device Gateway (backend domain) are all built and tested (229/229 passing). A native Flutter mobile shell exists but has never been compiled (no Flutter SDK available in the environment that built it). A real multi-page web UI now covers every one of those modules — Asset Core (catalog, locations, asset CRUD), Flow write actions (transition/assign/move), Inventory, Maintenance, and RFID/Device Gateway — see [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for what's independently verified vs. static-only per increment.

Zonovia's backend stack is deliberately modeled on Virasaka's own shipped sibling product, SchoolAssist (FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL 16 + Redis + PyJWT + Argon2); the web frontend likewise mirrors SchoolAssist's web conventions (React + TS + Vite, hand-written fetch client, no component library); the mobile shell mirrors SchoolAssist's Flutter app.

## Repository layout

```
backend/            FastAPI modular monolith
  app/
    core/            base model/repository, DB session + RLS session-var plumbing, JWT/Argon2
                      security, exceptions, module registry, audit, Redis cache + rate limit
    tenants/         Tenant, TenantConnectionRoute, TenantSetting
    users/           User, Role, Permission, RolePermission, UserRole — RBAC
    auth/            JWT access/refresh tokens, login lockout, IP rate limiting
    audit/           append-only audit log
    entitlements/    module-entitlement gate (require_module()) — three tiers: bundled/free,
                      "Zonovia Manage" (inventory, maintenance), "Zonovia RFID" (track_rfid)
    asset_core/      asset registry, categories/types/vendors, hierarchical locations,
                      identifiers, documents
    flow/            "Zonovia Flow" — configurable lifecycle state/transition engine,
                      custody assignment, movement
    tracking/        TrackingProvider abstraction (QR/Barcode), Device/DeviceGateway,
                      gateway (non-user) auth
    inventory/       verification cycles, discrepancy/missing-asset reporting, reconciliation
    maintenance/     tickets, warranty, interval-based service schedules
    track_rfid/      RFID tag registration, batched read ingestion + deduplication
  migrations/        Alembic, 0001-0015
  tests/             pytest — SQLite unit tier (default) + Postgres RLS integration tier
                      (`-m postgres`, see docs/IMPLEMENTATION_STATUS.md — not yet run for real)
web/                 React + TS + Vite — login, scan, asset core CRUD + Flow actions,
                      Inventory, Maintenance, RFID/Device Gateway
mobile/              Flutter — shell, auth, online scanning (never compiled, see status doc)
device-gateway/, sdks/    still placeholders
infrastructure/docker/    postgres-init scripts (dev + prod)
docs/                architecture blueprint + IMPLEMENTATION_STATUS.md + design notes
```

## Running locally

### Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

This builds the backend image, waits for Postgres/Redis health checks, runs Alembic migrations, seeds development data (`ENVIRONMENT=development` runs `app/seed.py`), and starts the API on `http://localhost:8000`.

- `GET http://localhost:8000/health` → `{"status": "ok"}`
- `http://localhost:8000/api/v1/docs` — interactive OpenAPI docs
- Seeded logins (see `backend/app/seed.py` for the full list): `platformadmin@zonovia.example` (tenant `platform`) and `admin@zonovia.example` / `member@zonovia.example` / `viewer@zonovia.example` (tenant `acme-demo`), all with password `ChangeMe123!`.

Verify Row-Level Security directly:

```bash
docker compose exec postgres psql -U postgres -d zonovia -c "\d+ users"   # Row security: enabled
docker compose exec postgres psql -U postgres -d zonovia -c "\dp users"   # zonovia_app: DML only, no ownership
```

### Backend tests, without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest -v -m "not postgres"       # SQLite-backed unit tier — no external services needed
ruff check app tests
ruff format --check app tests
```

The Postgres-backed RLS integration tests (`tests/test_tenant_isolation_postgres.py`) need a real, migrated Postgres:

```bash
docker compose up -d postgres
cd backend
cp .env.example .env
alembic upgrade head
python -m app.seed
pytest -v -m postgres
```

### Web app

```bash
cd web
npm install
cp .env.example .env.local   # VITE_API_BASE_URL, defaults to http://localhost:8000/api/v1
npm run dev                  # http://localhost:5173
npm run build                # tsc -b && vite build
npm run lint                 # oxlint
```

Log in with any of the seeded accounts above (tenant slug `acme-demo` for the non-platform ones). See `web/src/App.tsx` for the route table.

### Mobile app

See `mobile/README.md` — **this code has never been compiled**, no Flutter SDK was available in the environment that built it. Static checks (rename completeness, model-field contract vs. the live backend schemas) passed, but `flutter pub get && flutter run` needs a real first pass before it can be trusted.

### Production

```bash
cp .env.prod.example .env.prod   # fill in every value marked REQUIRED
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml exec \
  -e PLATFORM_ADMIN_EMAIL=you@your-domain.example \
  -e PLATFORM_ADMIN_PASSWORD='a real password' \
  backend python -m app.bootstrap_platform
```

`docker-compose.prod.yml` is postgres + redis + backend only in Phase 0 — no `nginx`, since there's no built `web/` app yet to reverse-proxy. See `docs/multi-tenancy.md`, `docs/authorization.md`, and `docs/database.md` for the design this implementation follows.

## CI

`.github/workflows/ci.yml` runs three jobs on every push/PR: **lint** (`ruff check` + `ruff format --check`), **unit-tests** (the SQLite tier, `pytest -m "not postgres"`, plus a smoke test of the dev seed script), and **postgres-integration** (a real `postgres:16-alpine` service container, migrations, seeding, then `pytest -m postgres` against the RLS proof suite). The Postgres job is a required gate, not a manual step — see `docs/multi-tenancy.md`'s testing section for why.
