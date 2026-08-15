-- Runs once, on first container startup, before the backend's migrations. Creates the
-- least-privilege runtime role the application actually connects as. See
-- migrations/versions/0003_app_role_grants.py for the table grants (applied after
-- migrations create the tables) and docs/multi-tenancy.md for why this role separation is
-- what makes Postgres RLS meaningful rather than a no-op against a superuser connection.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zonovia_app') THEN
        CREATE ROLE zonovia_app LOGIN PASSWORD 'zonovia_app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE zonovia TO zonovia_app;
GRANT USAGE ON SCHEMA public TO zonovia_app;
