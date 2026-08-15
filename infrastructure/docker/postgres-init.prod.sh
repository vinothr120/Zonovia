#!/bin/sh
# Production equivalent of postgres-init.sql — same least-privilege app role, but the
# password comes from $APP_DB_PASSWORD (set in docker-compose.prod.yml's postgres service
# environment, sourced from .env.prod) instead of being hardcoded. docker-entrypoint-initdb.d
# scripts ending in .sh run with the container's own environment, so this env var is visible
# here without any extra plumbing. Left as a separate file rather than templating the dev
# postgres-init.sql, so dev's setup (a fixed, throwaway local password) stays untouched.
set -e

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set (see .env.prod.example)}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zonovia_app') THEN
            CREATE ROLE zonovia_app LOGIN PASSWORD '$APP_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE $POSTGRES_DB TO zonovia_app;
    GRANT USAGE ON SCHEMA public TO zonovia_app;
EOSQL
