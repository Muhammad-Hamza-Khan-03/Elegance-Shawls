#!/bin/bash
# Operator step for WHATSAPP_AUTH_STORE=postgres (not run automatically). Creates the bridge's own least-privilege role.
#   docker compose exec -e WA_AUTH_PASSWORD='<new secret>' postgres bash /whatsapp-auth-role.sh   (or run psql by hand)
# Run after migration 0020. The role can touch only whatsapp_auth_entries: no access to the catalogue, enquiries or chats.
set -euo pipefail
: "${WA_AUTH_PASSWORD:?Set WA_AUTH_PASSWORD}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v pw="$WA_AUTH_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
SELECT 'CREATE ROLE elegance_wa_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elegance_wa_auth') \gexec
ALTER ROLE elegance_wa_auth PASSWORD :'pw';
GRANT CONNECT ON DATABASE :"db" TO elegance_wa_auth;
GRANT USAGE ON SCHEMA public TO elegance_wa_auth;
GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_auth_entries TO elegance_wa_auth;
SQL
echo "elegance_wa_auth ready (whatsapp_auth_entries only)"
