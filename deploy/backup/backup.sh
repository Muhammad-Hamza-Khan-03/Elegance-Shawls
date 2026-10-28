#!/bin/bash
# Encrypted MongoDB backup for the compose stack. Schedule it on the host (see
# OPERATIONS.md). Writes <name>.archive.gz.enc, <name>.sha256 and <name>.json
# (counts at dump time) to BACKUP_DIR, prunes old backups and alerts on failure.
#
# Required: BACKUP_DIR, BACKUP_PASSPHRASE_FILE (mode 600, kept outside the repo
# and also stored offline: without it backups cannot be restored).
# Optional: MONGO_CONTAINER (default elegance-shawls-mongo-1),
#   BACKUP_RETENTION_DAYS (default 14), ALERT_WEBHOOK_URL (JSON {"text": ...}),
#   BACKUP_SUCCESS_URL (dead-man's-switch ping), BACKUP_UPLOAD_COMMAND (run with
#   each new file path appended, e.g. `rclone copy` to separate storage).
# The mongo container already holds MONGO_DB_NAME and the backup user's credentials.
set -euo pipefail

: "${BACKUP_DIR:?Set BACKUP_DIR}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
MONGO_CONTAINER=${MONGO_CONTAINER:-elegance-shawls-mongo-1}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}

name="elegance-$(date -u +%Y%m%dT%H%M%SZ)"
archive="$BACKUP_DIR/$name.archive.gz.enc"

alert() {
  echo "$(date -u +%FT%TZ) backup failed: $1" >&2
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    curl -fsS -m 10 -H 'content-type: application/json' \
      -d "{\"text\": \"Elegance MongoDB backup failed on $(hostname): $1\"}" "$ALERT_WEBHOOK_URL" >/dev/null || true
  fi
}
on_exit() {
  local status=$?
  rm -f "$archive.partial"
  [ "$status" -eq 0 ] || alert "exit status $status"
}
trap on_exit EXIT

[ -r "$BACKUP_PASSPHRASE_FILE" ] || { echo "passphrase file is not readable" >&2; exit 1; }
umask 077
mkdir -p "$BACKUP_DIR"

# Credentials are read from the container's environment, never from command-line arguments.
counts=$(docker exec "$MONGO_CONTAINER" mongosh --quiet --nodb --eval '
  const env = process.env;
  const conn = new Mongo("mongodb://127.0.0.1:27017/?authSource=admin");
  conn.getDB("admin").auth(env.MONGO_BACKUP_USERNAME, env.MONGO_BACKUP_PASSWORD);
  const products = conn.getDB(env.MONGO_DB_NAME).products;
  const variants = products.aggregate([{ $group: { _id: null, n: { $sum: { $size: { $ifNull: ["$variants", []] } } } } }]).toArray();
  print(JSON.stringify({ products: products.countDocuments(), variants: variants.length ? variants[0].n : 0 }));
')

docker exec "$MONGO_CONTAINER" sh -c '
  set -e
  config=$(mktemp)
  trap "rm -f $config" EXIT
  printf "password: \"%s\"\n" "$MONGO_BACKUP_PASSWORD" > "$config"
  mongodump --quiet --config "$config" --username "$MONGO_BACKUP_USERNAME" \
    --authenticationDatabase admin --db "$MONGO_DB_NAME" --archive --gzip
' | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$BACKUP_PASSPHRASE_FILE" -out "$archive.partial"

mv "$archive.partial" "$archive"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$archive")" > "$name.sha256")
printf '{"backup": "%s", "created_at": "%s", "database": "%s", "counts": %s}\n' \
  "$(basename "$archive")" "$(date -u +%FT%TZ)" \
  "$(docker exec "$MONGO_CONTAINER" printenv MONGO_DB_NAME)" "$counts" > "$BACKUP_DIR/$name.json"

if [ -n "${BACKUP_UPLOAD_COMMAND:-}" ]; then
  for file in "$archive" "$BACKUP_DIR/$name.sha256" "$BACKUP_DIR/$name.json"; do
    $BACKUP_UPLOAD_COMMAND "$file"
  done
fi

find "$BACKUP_DIR" -maxdepth 1 -name 'elegance-*' -mtime "+$BACKUP_RETENTION_DAYS" -delete

if [ -n "${BACKUP_SUCCESS_URL:-}" ]; then curl -fsS -m 10 "$BACKUP_SUCCESS_URL" >/dev/null || true; fi
echo "$(date -u +%FT%TZ) backup ok: $(basename "$archive") $counts"
