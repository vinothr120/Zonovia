"""Production bootstrap — creates ONLY the platform tenant and a single Platform Admin user,
with a password YOU choose. Contrast with app/seed.py, which is dev-only (entrypoint.sh
never runs it when ENVIRONMENT=production) and creates a full demo tenant on top of the
platform tenant, with everyone sharing a well-known password.

Creating a tenant normally requires an existing platform-admin token (POST
/api/v1/platform/tenants is gated on require_platform_admin — see app/tenants/router.py) —
there is no self-registration endpoint, deliberately (accounts are always created by an
existing admin). This script is how the very first admin gets created, run once, directly
against the database rather than through the API. Safe to re-run — every step checks for an
existing row first (same idempotent pattern as app/seed.py).

Usage (inside the running backend container, after `docker compose ... up -d`):
    docker compose -f docker-compose.prod.yml exec \\
      -e PLATFORM_ADMIN_EMAIL=you@your-domain.example \\
      -e PLATFORM_ADMIN_PASSWORD='a real password, not a placeholder' \\
      backend python -m app.bootstrap_platform

After this, log in at tenant_slug "platform" with the email/password above, then use the API
to create your first real tenant.
"""

import asyncio
import os
import sys

from app.core.bootstrap import register_all_modules
from app.core.database import AsyncSessionLocal, set_tenant_session_var
from app.seed import ensure_tenant, ensure_user, sync_permissions, sync_system_roles


async def main() -> None:
    email = os.environ.get("PLATFORM_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
    if not email or not password:
        sys.exit("PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD must both be set — see this module's docstring.")
    if len(password) < 10:
        sys.exit("PLATFORM_ADMIN_PASSWORD must be at least 10 characters (matches UserCreate's own validation).")

    register_all_modules()

    async with AsyncSessionLocal() as db:
        permissions_by_key = await sync_permissions(db)
        roles_by_name = await sync_system_roles(db, permissions_by_key)
        await db.commit()

    async with AsyncSessionLocal() as db:
        platform_tenant = await ensure_tenant(db, name="Zonovia Platform", subdomain="platform", tier="platform")
        await set_tenant_session_var(db, platform_tenant.id, local=False)
        await ensure_user(db, platform_tenant.id, email=email, role=roles_by_name["Platform Admin"], password=password)
        await db.commit()

    print(f"Platform tenant ready. Platform Admin: {email} (tenant_slug='platform')")


if __name__ == "__main__":
    asyncio.run(main())
