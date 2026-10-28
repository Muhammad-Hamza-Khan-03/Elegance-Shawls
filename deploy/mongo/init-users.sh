#!/bin/bash
# Runs once, on first start of an empty data volume, after the root user exists.
# Creates a least-privilege application user and a backup-only user.
set -euo pipefail

mongosh --quiet admin \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --eval '
    const env = process.env;
    db.getSiblingDB(env.MONGO_DB_NAME).createUser({
      user: env.MONGO_APP_USERNAME,
      pwd: env.MONGO_APP_PASSWORD,
      roles: [{ role: "readWrite", db: env.MONGO_DB_NAME }],
    });
    db.getSiblingDB("admin").createUser({
      user: env.MONGO_BACKUP_USERNAME,
      pwd: env.MONGO_BACKUP_PASSWORD,
      roles: ["backup"],
    });
  '
echo "Created application and backup users"
