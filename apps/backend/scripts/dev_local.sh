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

# Semantic search (multilingual-e5-base, local CPU) when the model is present: fetch once with `python scripts/fetch_e5_model.py`
# after `pip install -r requirements-local-e5.txt`. Without it the shop still works with keyword search.
E5_DIR="${SEMANTIC_E5_MODEL_PATH:-$HOME/.cache/elegance/multilingual-e5-base}"
if [ -f "$E5_DIR/model.safetensors" ] && python -c "import sentence_transformers" 2>/dev/null; then
  export SEMANTIC_EMBEDDING_PROVIDER=local_e5 SEMANTIC_EMBEDDING_MODEL=intfloat/multilingual-e5-base SEMANTIC_EMBEDDING_DIMENSIONS=768 \
         SEMANTIC_E5_MODEL_PATH="$E5_DIR" HF_HUB_OFFLINE=1
  python scripts/embedding_backfill.py
else
  echo "semantic search off (no E5 model); keyword search only"
fi

uvicorn main:app --port 8000 &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd ../frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_SITE_URL=http://localhost:3000 NEXT_PUBLIC_WHATSAPP_NUMBER=923001234567 \
  NEXT_PUBLIC_ASSISTANT_ENABLED=1 npm run dev
