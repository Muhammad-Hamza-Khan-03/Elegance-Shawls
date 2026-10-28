#!/bin/bash
# Host-side watchdog for the compose stack; run every minute (see OPERATIONS.md).
# Alerts once when a problem starts and once when it recovers, via
# ALERT_WEBHOOK_URL (JSON {"text": ...}) and stderr.
#
# Required: SITE_URL, API_URL.
# Optional: CONTAINERS (default: compose project elegance-shawls service names),
#   BACKEND_CONTAINER, STATE_DIR (default /var/tmp/elegance-watchdog),
#   PROBE_FAILURE_THRESHOLD (3 consecutive runs), ERROR_5XX_THRESHOLD (5 in 5 min),
#   DISK_PERCENT_THRESHOLD (85), MEMORY_PERCENT_THRESHOLD (90), CURL_CA_BUNDLE.
set -uo pipefail

: "${SITE_URL:?Set SITE_URL}"
: "${API_URL:?Set API_URL}"
CONTAINERS=${CONTAINERS:-"elegance-shawls-proxy-1 elegance-shawls-frontend-1 elegance-shawls-backend-1 elegance-shawls-mongo-1"}
BACKEND_CONTAINER=${BACKEND_CONTAINER:-elegance-shawls-backend-1}
STATE_DIR=${STATE_DIR:-/var/tmp/elegance-watchdog}
PROBE_FAILURE_THRESHOLD=${PROBE_FAILURE_THRESHOLD:-3}
ERROR_5XX_THRESHOLD=${ERROR_5XX_THRESHOLD:-5}
DISK_PERCENT_THRESHOLD=${DISK_PERCENT_THRESHOLD:-85}
MEMORY_PERCENT_THRESHOLD=${MEMORY_PERCENT_THRESHOLD:-90}
mkdir -p "$STATE_DIR"

notify() {
  echo "$(date -u +%FT%TZ) $1" >&2
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    curl -fsS -m 10 -H 'content-type: application/json' \
      -d "$(printf '{"text": "%s"}' "Elegance $(hostname): $1")" "$ALERT_WEBHOOK_URL" >/dev/null || true
  fi
}

# check <id> <problem description or empty when healthy>
check() {
  local flag="$STATE_DIR/$1.alerting"
  if [ -n "$2" ]; then
    [ -f "$flag" ] || { notify "ALERT $1: $2"; touch "$flag"; }
  elif [ -f "$flag" ]; then
    notify "RECOVERED $1"; rm -f "$flag"
  fi
}

for probe in "$SITE_URL/api/health" "$SITE_URL/api/ready" "$API_URL/health/" "$API_URL/ready/"; do
  id="probe-$(echo "$probe" | tr -c 'a-zA-Z0-9' '_')"
  failures_file="$STATE_DIR/$id.failures"
  code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$probe")
  if [ "$code" = 200 ]; then
    echo 0 > "$failures_file"
    check "$id" ""
  else
    failures=$(( $(cat "$failures_file" 2>/dev/null || echo 0) + 1 ))
    echo "$failures" > "$failures_file"
    [ "$failures" -ge "$PROBE_FAILURE_THRESHOLD" ] && check "$id" "$probe returned $code for $failures consecutive checks"
  fi
done

errors=$(docker logs --since 5m "$BACKEND_CONTAINER" 2>/dev/null | grep -c '"status": 5')
check "backend-5xx" "$([ "$errors" -ge "$ERROR_5XX_THRESHOLD" ] && echo "$errors HTTP 5xx responses in the last 5 minutes")"

for container in $CONTAINERS; do
  restarts=$(docker inspect -f '{{.RestartCount}}' "$container" 2>/dev/null || echo missing)
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || echo missing)
  previous=$(cat "$STATE_DIR/$container.restarts" 2>/dev/null || echo "$restarts")
  echo "$restarts" > "$STATE_DIR/$container.restarts"
  problem=""
  [ "$restarts" = missing ] && problem="container is missing"
  [ "$restarts" != missing ] && [ "$restarts" != "$previous" ] && problem="restarted (count $previous -> $restarts)"
  [ "$health" = unhealthy ] && problem="health check is unhealthy"
  check "container-$container" "$problem"
done

disk=$(df --output=pcent / | tail -1 | tr -dc '0-9')
check "disk" "$([ "$disk" -ge "$DISK_PERCENT_THRESHOLD" ] && echo "root filesystem ${disk}% full")"

pressure=$(docker stats --no-stream --format '{{.Name}} {{.MemPerc}}' $CONTAINERS 2>/dev/null \
  | awk -v limit="$MEMORY_PERCENT_THRESHOLD" '{ sub("%", "", $2); if ($2 + 0 >= limit) printf "%s %s%% ", $1, $2 }')
check "memory" "$([ -n "$pressure" ] && echo "memory pressure: $pressure")"
exit 0
