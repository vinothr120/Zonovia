# Zonovia

Zonovia is Virasaka's enterprise asset-visibility platform — RFID, computer vision, and IoT/BLE sensing fused with an AI layer into one live model of every physical asset an organization owns. See [`docs/architecture/Zonovia-Architecture-Blueprint.md`](docs/architecture/Zonovia-Architecture-Blueprint.md) for the full product and technical architecture.

## Current status: Phase 0 — Platform Core Foundation

Per the blueprint's roadmap (§30), this repository currently implements exactly **Phase 0**: repo + CI/CD, Platform Core (tenant, user, RBAC, licensing/entitlements stub, audit), DB + Row-Level Security, and a Docker Compose dev environment. It does not yet include Asset Core (Phase 1) or any tracking technology, AI, or UI — `web/`, `mobile/`, `device-gateway/`, and `sdks/` are placeholder directories only, each with a README explaining what phase fills them in.

Zonovia's Phase 0 is deliberately modeled on Virasaka's own shipped sibling product, SchoolAssist (identical stack: FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL 16 + Redis + PyJWT + Argon2) — see the implementation plan referenced from this repo's history for the exact file-by-file mapping.

## Repository layout

```
backend/            FastAPI modular monolith — Platform Core only in Phase 0
  app/
    core/            base model/repository, DB session + RLS session-var plumbing, JWT/Argon2
                      security, exceptions, module registry, audit, Redis cache + rate limit,
                      connection router (Tenant Routing Table seam, ADR-003)
    tenants/         Tenant, TenantConnectionRoute, TenantSetting
    users/           User, Role, Permission, RolePermission, UserRole — RBAC
    auth/            JWT access/refresh tokens, login lockout, IP rate limiting
    audit/           append-only audit log (read-only API; every module writes through
                      core.audit.write_audit_log)
    entitlements/     module-entitlement stub (ADR-007) — TenantModuleEntitlement,
                      require_module() gate
  migrations/        Alembic — 0001 schema, 0002 Row-Level Security, 0003 app-role grants
  tests/             pytest — SQLite unit tier (default) + Postgres RLS integration tier
                      (`-m postgres`)
web/, mobile/, device-gateway/, sdks/    placeholders — see each directory's README
infrastructure/docker/                   postgres-init scripts (dev + prod)
docs/                architecture blueprint + multi-tenancy/authorization/database notes
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
