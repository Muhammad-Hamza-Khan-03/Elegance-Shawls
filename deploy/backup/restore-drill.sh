#!/bin/bash
# Restore drill: decrypts one backup into a throwaway MongoDB container with no
# network, reconciles product and variant counts against the backup manifest,
# prints dated evidence and removes the container. Never touches the live database.
#
# Usage: BACKUP_PASSPHRASE_FILE=... deploy/backup/restore-drill.sh /path/to/elegance-<stamp>.archive.gz.enc
set -euo pipefail

archive=${1:?Usage: restore-drill.sh <backup.archive.gz.enc>}
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
dir=$(dirname "$archive")
name=$(basename "$archive" .archive.gz.enc)
manifest="$dir/$name.json"
container="elegance-restore-drill-$$"
started=$(date +%s)

cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT

(cd "$dir" && sha256sum --quiet -c "$name.sha256")
database=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["database"])' "$manifest")
expected=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["counts"], sort_keys=True))' "$manifest")

docker run -d --name "$container" --network none mongo:8.0 >/dev/null
for _ in $(seq 1 30); do
  docker exec "$container" mongosh --quiet --eval 'db.adminCommand("ping").ok' >/dev/null 2>&1 && break
  sleep 1
done

openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$archive" \
  | docker exec -i "$container" mongorestore --quiet --archive --gzip \
      --nsFrom "$database.*" --nsTo "restore_drill.*"

actual=$(docker exec "$container" mongosh --quiet --eval '
  const products = db.getSiblingDB("restore_drill").products;
  const variants = products.aggregate([{ $group: { _id: null, n: { $sum: { $size: { $ifNull: ["$variants", []] } } } } }]).toArray();
  print(JSON.stringify({ products: products.countDocuments(), variants: variants.length ? variants[0].n : 0 }));
' | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), sort_keys=True))')

result=$([ "$actual" = "$expected" ] && echo pass || echo fail)
printf '{"drill": "restore", "date": "%s", "backup": "%s", "expected": %s, "restored": %s, "duration_seconds": %s, "result": "%s"}\n' \
  "$(date -u +%FT%TZ)" "$(basename "$archive")" "$expected" "$actual" "$(( $(date +%s) - started ))" "$result"
[ "$result" = pass ]
