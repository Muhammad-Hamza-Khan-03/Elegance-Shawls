#!/usr/bin/env bash
# One-command LOCAL store: pgvector Postgres (docker volume), migrations, owner account, seed catalogue, API and storefront.
#   ADMIN_ACCOUNT_PASSWORD='choose-a-long-passphrase' bash scripts/dev_local.sh      # from apps/backend, venv active, npm ci done
# Optional: LOCAL_DB_PORT (55432), LOCAL_DB_CONTAINER (elegance-local-db; also names the data volume), LOCAL_FRONTEND_PORT (3000).
# WHATSAPP_LOCAL=1 also starts Redis, the WhatsApp consumer and a FAKE bridge with a browser "customer phone" (no WhatsApp account):
#   see "Try the WhatsApp automation locally" in README.md. Everything WhatsApp stays off unless you set it.
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
DBC="${LOCAL_DB_CONTAINER:-elegance-local-db}"; DB_PORT="${LOCAL_DB_PORT:-55432}"; FRONT_PORT="${LOCAL_FRONTEND_PORT:-3000}"
export DATABASE_URL="postgresql+asyncpg://elegance:local-dev-only@127.0.0.1:$DB_PORT/elegance_shawls"
# Next picks 3001 when 3000 is busy, and the browser-side catalogue fetches are cross-origin, so both ports must be allowed.
export ENVIRONMENT=development ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,http://localhost:$FRONT_PORT ASSISTANT_CATALOGUE=true
# LLM wording turns on by itself when a model chain is configured.
export ASSISTANT_LLM="${ASSISTANT_LLM:-$([ -n "${LLM_CHAIN_DEFAULT:-}" ] && echo true || echo false)}"

docker inspect $DBC >/dev/null 2>&1 || docker run -d --name $DBC -p 127.0.0.1:$DB_PORT:5432 \
  -e POSTGRES_USER=elegance -e POSTGRES_PASSWORD=local-dev-only -e POSTGRES_DB=elegance_shawls \
  -v $DBC:/var/lib/postgresql/data pgvector/pgvector:0.8.1-pg17 >/dev/null
docker start $DBC >/dev/null
until docker exec $DBC pg_isready -U elegance -d elegance_shawls >/dev/null 2>&1; do sleep 1; done

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

PIDS=""
if [ "${WHATSAPP_LOCAL:-0}" = "1" ]; then
  RPORT="${LOCAL_REDIS_PORT:-56379}"; BPORT="${LOCAL_BRIDGE_PORT:-3600}"
  docker inspect elegance-local-redis >/dev/null 2>&1 || docker run -d --name elegance-local-redis -p 127.0.0.1:$RPORT:6379 \
    redis:7.4-alpine redis-server --maxmemory-policy noeviction >/dev/null
  docker start elegance-local-redis >/dev/null
  # Local-only switches (a throwaway token, no allowlist): the repo defaults stay off.
  export REDIS_URL="redis://127.0.0.1:$RPORT/1" WHATSAPP_BRIDGE_ENABLED=true WHATSAPP_BRIDGE_TOKEN=local-dev-token \
         WHATSAPP_BRIDGE_URL="http://127.0.0.1:$BPORT" WHATSAPP_ASSISTANT_ENABLED=true WHATSAPP_SITE_URL="http://localhost:$FRONT_PORT" \
         WHATSAPP_VOICE_ENABLED=true WHATSAPP_ASR_URL="http://127.0.0.1:$BPORT/sim/asr" WHATSAPP_ASR_PRIVACY=self_hosted
  [ -d ../whatsapp-bridge/node_modules ] || (cd ../whatsapp-bridge && npm ci --silent)
  (cd ../whatsapp-bridge && PORT="$BPORT" node dev/fake-bridge.mjs) & PIDS="$PIDS $!"
  python -m whatsapp.consumer & PIDS="$PIDS $!"
  echo "WhatsApp simulator: http://127.0.0.1:$BPORT/sim   |   admin: http://localhost:$FRONT_PORT/admin/whatsapp (owner@elegance.local)"
fi
uvicorn main:app --port 8000 &
API=$!
trap 'kill $API $PIDS 2>/dev/null' EXIT
cd ../frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_SITE_URL=http://localhost:$FRONT_PORT NEXT_PUBLIC_WHATSAPP_NUMBER=923001234567 \
  NEXT_PUBLIC_ASSISTANT_ENABLED=1 NEXT_PUBLIC_GOOGLE_CLIENT_ID="${NEXT_PUBLIC_GOOGLE_CLIENT_ID:-${CUSTOMER_AUTH_AUDIENCE:-}}" npm run dev -- -p "$FRONT_PORT"
