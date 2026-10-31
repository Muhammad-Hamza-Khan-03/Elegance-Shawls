#!/usr/bin/env bash
# One-command LOCAL store: pgvector Postgres (docker volume), migrations, owner account, seed catalogue, API and storefront.
#   ADMIN_ACCOUNT_PASSWORD='choose-a-long-passphrase' bash scripts/dev_local.sh      # from apps/backend, venv active, npm ci done
# Local only: throwaway database password, ENVIRONMENT=development. Ctrl-C stops the API and storefront; the database keeps its data.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ADMIN_ACCOUNT_PASSWORD:?set ADMIN_ACCOUNT_PASSWORD (12+ chars) for the local owner account}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-owner@elegance.local}"
export DATABASE_URL='postgresql+asyncpg://elegance:local-dev-only@127.0.0.1:55432/elegance_shawls'
export ENVIRONMENT=development ALLOWED_ORIGINS=http://localhost:3000 ASSISTANT_CATALOGUE=true

docker inspect elegance-local-db >/dev/null 2>&1 || docker run -d --name elegance-local-db -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=elegance -e POSTGRES_PASSWORD=local-dev-only -e POSTGRES_DB=elegance_shawls \
  -v elegance-local-db:/var/lib/postgresql/data pgvector/pgvector:0.8.1-pg17 >/dev/null
docker start elegance-local-db >/dev/null
until docker exec elegance-local-db pg_isready -U elegance -d elegance_shawls >/dev/null 2>&1; do sleep 1; done

alembic upgrade head
python scripts/admin_accounts.py bootstrap-owner --email "$ADMIN_EMAIL"
python scripts/seed_local.py

uvicorn main:app --port 8000 &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd ../frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_SITE_URL=http://localhost:3000 NEXT_PUBLIC_WHATSAPP_NUMBER=923001234567 \
  NEXT_PUBLIC_ASSISTANT_ENABLED=1 npm run dev
