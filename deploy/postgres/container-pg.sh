#!/bin/bash
# Runs a PostgreSQL client tool inside the PostgreSQL container, so the host needs no client install and the internal-only
# database needs no published port. Point the backup CLI at it (see OPERATIONS.md), e.g.
#   PG_DUMP_CMD="deploy/postgres/container-pg.sh pg_dump" PG_RESTORE_CMD="deploy/postgres/container-pg.sh pg_restore" \
#   PSQL_CMD="deploy/postgres/container-pg.sh psql"
# Connection settings reach the tool as PG* variables forwarded by name (never in argv). Host and port are fixed to the
# container's own server, so the user/password/database from BACKUP_DATABASE_URL are what select the role.
set -euo pipefail

tool=${1:?Usage: container-pg.sh <pg_dump|pg_restore|psql> [args...]}
shift
case "$tool" in pg_dump|pg_restore|psql) ;; *) echo "unsupported tool: $tool" >&2; exit 64 ;; esac

exec docker exec -i -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGCONNECT_TIMEOUT -e PGHOST=localhost -e PGPORT=5432 \
  "${POSTGRES_CONTAINER:-elegance-shawls-postgres-1}" "$tool" "$@"
