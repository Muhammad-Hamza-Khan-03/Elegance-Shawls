#!/usr/bin/env bash
# One-command LOCAL store: pgvector Postgres (docker volume), migrations, owner account, seed catalogue, API and storefront.
#   ADMIN_ACCOUNT_PASSWORD='choose-a-long-passphrase' bash scripts/dev_local.sh      # from apps/backend, venv active, npm ci done
# Local only: throwaway database password, ENVIRONMENT=development. Ctrl-C stops the API and storefront; the database keeps its data.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ADMIN_ACCOUNT_PASSWORD:?set ADMIN_ACCOUNT_PASSWORD (12+ chars) for the local owner account}"
# Optional: LOCAL_ENV_FILE=/path/to/apps/backend/.env supplies provider keys (GROQ_API_KEY ...), LLM_CHAIN_DEFAULT and CUSTOMER_AUTH_*.
# Sourced first, so the local database settings below always win. Values are never printed.
if [ -n "${LOCAL_ENV_FILE:-}" ]; then   # parsed as dotenv (never sourced): unquoted values with spaces are fine
  eval "$(python - "$LOCAL_ENV_FILE" <<'PY'
import shlex, sys
from dotenv import dotenv_values
for key, value in dotenv_values(sys.argv[1]).items():
    if value is not None:
        print(f"export {key}={shlex.quote(value)}")
PY
)"
fi
export ADMIN_EMAIL="${ADMIN_EMAIL:-owner@elegance.local}"
export DATABASE_URL='postgresql+asyncpg://elegance:local-dev-only@127.0.0.1:55432/elegance_shawls'
# Next picks 3001 when 3000 is busy, and the browser-side catalogue fetches are cross-origin, so both ports must be allowed.
export ENVIRONMENT=development ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001 ASSISTANT_CATALOGUE=true
# LLM wording turns on by itself when a model chain is configured.
export ASSISTANT_LLM="${ASSISTANT_LLM:-$([ -n "${LLM_CHAIN_DEFAULT:-}" ] && echo true || echo false)}"

docker inspect elegance-local-db >/dev/null 2>&1 || docker run -d --name elegance-local-db -p 127.0.0.1:55432:5432 \
  -e POSTGRES_USER=elegance -e POSTGRES_PASSWORD=local-dev-only -e POSTGRES_DB=elegance_shawls \
  -v elegance-local-db:/var/lib/postgresql/data pgvector/pgvector:0.8.1-pg17 >/dev/null
docker start elegance-local-db >/dev/null
until docker exec elegance-local-db pg_isready -U elegance -d elegance_shawls >/dev/null 2>&1; do sleep 1; done

python scripts/check_migration_stamp.py || exit 1   # read-only: refuses a database stamped under the pre-consolidation numbering
alembic upgrade head
python scripts/admin_accounts.py bootstrap-owner --email "$ADMIN_EMAIL"
python scripts/seed_local.py

# Semantic search (multilingual-e5-base, local CPU) when the model is present: fetch once with `python scripts/fetch_e5_model.py`
# after `pip install -r requirements-local-e5.txt`. Without it the shop still works with keyword search.
E5_DIR="${LOCAL_E5_MODEL_PATH:-$HOME/.cache/elegance/multilingual-e5-base}"
if [ -f "$E5_DIR/model.safetensors" ] && python -c "import sentence_transformers" 2>/dev/null; then
  # One embedding pipeline: search/embedding_service writes product_embeddings + variant_embeddings, search and the assistant read them.
  export ENVIRONMENT=development EMBEDDING_ENABLED=true EMBEDDING_PROVIDER=local_e5 EMBEDDING_DIMENSIONS=768 \
         LOCAL_SEMANTIC_SEARCH_ENABLED=true LOCAL_E5_MODEL_PATH="$E5_DIR" HF_HUB_OFFLINE=1
  export LOCAL_E5_MODEL_REVISION="${LOCAL_E5_MODEL_REVISION:-$(python -c "from embeddings.providers.local_e5 import model_tree_digest as d; print(d('$E5_DIR'))")}"
  for kind in product variant; do
    after=""
    while :; do   # resumable: each run embeds one bounded page, last_id is the next --after
      out=$(python scripts/embedding_backfill.py --kind "$kind" --limit 100 ${after:+--after "$after"})
      echo "$out"
      after=$(python -c "import json,sys; print(json.loads(sys.argv[1]).get('last_id') or '')" "$out")
      [ -n "$after" ] || break
      [ "$(python -c "import json,sys; print(json.loads(sys.argv[1])['examined'])" "$out")" -ge 100 ] || break
    done
  done
else
  echo "semantic search off (no E5 model); keyword search only"
fi

uvicorn main:app --port 8000 &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd ../frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_SITE_URL=http://localhost:3000 NEXT_PUBLIC_WHATSAPP_NUMBER=923001234567 \
  NEXT_PUBLIC_ASSISTANT_ENABLED=1 NEXT_PUBLIC_GOOGLE_CLIENT_ID="${NEXT_PUBLIC_GOOGLE_CLIENT_ID:-${CUSTOMER_AUTH_AUDIENCE:-}}" npm run dev
