#!/bin/bash
# Coordinated application rollback (or roll-forward) to existing immutable images.
# Replaces only the backend and frontend containers: MongoDB data, the proxy and
# its certificates are untouched. Run from the repository root next to .env.
#
# Usage: deploy/rollback.sh <APP_VERSION>
set -euo pipefail

version=${1:?Usage: deploy/rollback.sh <APP_VERSION>}
for image in elegance-backend elegance-frontend; do
  docker image inspect "$image:$version" >/dev/null 2>&1 || { echo "Image $image:$version is not available locally" >&2; exit 1; }
done

set -a; . ./.env; set +a
APP_VERSION=$version docker compose up -d --no-build --no-deps backend frontend

for _ in $(seq 1 60); do
  healthy=true
  for probe in "$SITE_URL/api/health" "$SITE_URL/api/ready" "$API_URL/health/" "$API_URL/ready/"; do
    [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$probe")" = 200 ] || healthy=false
  done
  if $healthy; then
    echo "$(date -u +%FT%TZ) now serving $version; all readiness probes pass."
    echo "Set APP_VERSION=$version in .env so restarts keep this version."
    exit 0
  fi
  sleep 2
done
echo "$(date -u +%FT%TZ) $version did not become ready; investigate or roll to another version." >&2
exit 1
