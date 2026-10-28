#!/usr/bin/env bash
# Local-only monthly refresh of the authorized source into the STAGING database.
#
#   scripts/monthly_refresh.sh [--once | --dry-run | --discovery-only]     (default: --once)
#
# Secrets come from the environment or the ignored apps/backend/.env, never from arguments.
# The run is bounded (see ingestion.refresh), cannot overlap another run, refuses any database
# that is not clearly staging, and only stages products as pending_review.
set -euo pipefail

backend="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$backend"

mode="--once"
if [ "$#" -gt 1 ]; then echo "usage: $0 [--once|--dry-run|--discovery-only]" >&2; exit 64; fi
if [ "$#" -eq 1 ]; then
  case "$1" in
    --once|--dry-run|--discovery-only) mode="$1" ;;
    *) echo "usage: $0 [--once|--dry-run|--discovery-only] (no secrets or other options are accepted)" >&2; exit 64 ;;
  esac
fi

# Database name: environment first, then the ignored .env. Read as text, never executed or printed.
db_name="${MONGO_DB_NAME:-}"
if [ -z "$db_name" ] && [ -f .env ]; then
  db_name="$(grep -E '^MONGO_DB_NAME=' .env | tail -1 | cut -d= -f2- | tr -d "\"'" || true)"
fi
if ! [[ "$db_name" =~ (^|[_-])[Ss][Tt][Aa][Gg][Ii][Nn][Gg]($|[_-]) ]] || [[ "$db_name" =~ [Pp][Rr][Oo][Dd] ]]; then
  echo "Refusing to run: MONGO_DB_NAME must clearly identify a staging database." >&2
  exit 2
fi

# One run at a time.
lock="${REFRESH_LOCK_FILE:-${TMPDIR:-/tmp}/elegance-monthly-refresh.lock}"
exec 9>"$lock"
if ! flock -n 9; then
  echo "Another monthly refresh is already running; exiting." >&2
  exit 75
fi

# Sanitized summaries live in a directory that ignores itself, so nothing here can be committed.
out="${REFRESH_OUTPUT_DIR:-$backend/.refresh-output}"
mkdir -p "$out"
[ -f "$out/.gitignore" ] || printf '*\n' > "$out/.gitignore"
summary="$out/refresh-summary-$(date -u +%Y%m%dT%H%M%SZ).json"

if [ -n "${PYTHON:-}" ]; then py="$PYTHON"; elif [ -x .venv/bin/python ]; then py=.venv/bin/python; else py=python3.11; fi

status=0
"$py" -m ingestion.worker "$mode" --summary-file "$summary" || status=$?
echo "refresh finished: exit=$status summary=$summary" >&2
exit "$status"
