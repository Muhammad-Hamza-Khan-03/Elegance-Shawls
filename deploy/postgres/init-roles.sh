#!/bin/bash
# Runs once, on first start of an empty data volume, as the bootstrap superuser.
# Creates the vector extension, a least-privilege application role and a
# read-only backup role.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$POSTGRES_APP_USER" -v app_pw="$POSTGRES_APP_PASSWORD" \
  -v backup_user="$POSTGRES_BACKUP_USER" -v backup_pw="$POSTGRES_BACKUP_PASSWORD" \
  -v db="$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE ROLE :"app_user" LOGIN PASSWORD :'app_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE :"backup_user" LOGIN PASSWORD :'backup_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app_user", :"backup_user";

-- The app role runs Alembic migrations (DDL) in its own schema only.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"backup_user";
GRANT pg_read_all_data TO :"backup_user";
SQL
echo "Created vector extension, application role and backup role"
