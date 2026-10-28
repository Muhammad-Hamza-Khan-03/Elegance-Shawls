# Operations runbook

The step-by-step release procedure and current external blocker are maintained in `LAUNCH_RUNBOOK.md`.

## Launch gate

- CI is green for the exact commit being deployed.
- Production environment values are present and use final HTTPS origins.
- MongoDB is private, authenticated and not exposed to the internet: TLS-enabled with a managed provider, or on the internal-only compose network when self-hosted.
- Quill authentication, create/update/publish/unpublish/archive and inventory changes are verified in staging.
- Browse, filter, product selection, inventory display and WhatsApp order text are verified on desktop and mobile.
- Delivery, returns, privacy, terms and contact wording has been approved by the business owner.
- DNS, TLS, reverse proxy limits and backups have been tested.

## Health and monitoring

Monitor the frontend `/api/health` for liveness and `/api/ready` for configuration/backend connectivity. Monitor backend `/health/` for process liveness and `/ready/` for MongoDB connectivity.

`deploy/monitoring/watchdog.sh` implements this for the compose stack. Run it every minute from the host, for example with cron:

```cron
* * * * * cd /srv/elegance && set -a && . ./.env && set +a && ALERT_WEBHOOK_URL=https://hooks.example/... deploy/monitoring/watchdog.sh 2>>/var/log/elegance-watchdog.log
```

It alerts once when a problem starts and once when it recovers. It covers: any probe failing for 3 consecutive runs; 5 or more backend 5xx responses in 5 minutes; a container restarting, missing or unhealthy; root disk at 85% or more; and container memory at 90% or more. `ALERT_WEBHOOK_URL` receives `{"text": "..."}`, which Slack, Discord (`/slack` suffix) and most chat webhooks accept. Thresholds are environment variables documented in the script.

Logs: Caddy writes JSON access logs with the `X-Admin-Key`, `X-Internal-API-Token`, `Cookie`, `Authorization` and `Set-Cookie` headers removed and adds an `X-Request-ID`. The backend logs one JSON line per request (request ID, method, path, status, duration) and never logs headers, query strings, bodies or client addresses. Operators read them with `docker compose logs proxy backend`. Configure Docker's log rotation (`max-size`, `max-file`) or ship logs to central storage, and restrict access to the host. Never log `X-Admin-Key`, MongoDB credentials, customer WhatsApp messages, addresses or payment details.

## Backup and restore

`deploy/backup/backup.sh` takes a `mongodump` of the application database as the backup-role user, with credentials read inside the container and never on a command line. It encrypts the dump with AES-256 (`openssl enc -pbkdf2`, 600,000 iterations) using a passphrase file, and writes a SHA-256 checksum and a manifest of product and variant counts. It then prunes backups older than `BACKUP_RETENTION_DAYS` (default 14) and alerts `ALERT_WEBHOOK_URL` on any failure. Schedule it daily:

```cron
15 2 * * * cd /srv/elegance && BACKUP_DIR=/var/backups/elegance BACKUP_PASSPHRASE_FILE=/root/.elegance-backup-pass MONGO_CONTAINER=elegance-shawls-mongo-1 ALERT_WEBHOOK_URL=https://hooks.example/... BACKUP_SUCCESS_URL=https://hc-ping.example/... BACKUP_UPLOAD_COMMAND="rclone copy --immutable" deploy/backup/backup.sh >>/var/log/elegance-backup.log 2>&1
```

- **Encryption and access:** the passphrase file is mode 600, readable only by root. Keep a second copy offline; backups cannot be restored without it. Backup files are mode 600.
- **Independent storage:** set `BACKUP_UPLOAD_COMMAND` (for example `rclone copy` to a bucket in a separate account) so copies leave the host. Local copies alone do not survive loss of the host.
- **Missed-backup alerting:** `BACKUP_SUCCESS_URL` pings a dead-man's-switch monitor after each success, so a backup that stops running entirely also raises an alert.
- **Restore drill:** `BACKUP_PASSPHRASE_FILE=... deploy/backup/restore-drill.sh <backup>.archive.gz.enc` verifies the checksum, then restores into a throwaway MongoDB container with no network. It reconciles product and variant counts against the manifest, prints dated JSON evidence and removes the container. It never touches the live database. Run it monthly and after any change to backup tooling. Record the output in `docs/qa/`.
- **Targets:** RPO 24 hours (daily backups). RTO 1 hour for a full restore on a prepared host; a local drill on a small catalogue restored in seconds. **Owner:** the repository owner runs restores and drills and receives backup alerts.
- A backup is not considered valid until a restore into an isolated environment succeeds and product/variant counts are checked.

## Incident response

Incident owner: the repository owner, who receives watchdog and backup alerts.

1. Confirm impact using health endpoints and recent deployment/log data.
2. Stop further risky changes; revoke exposed credentials immediately.
3. Roll back application images when the incident follows a deployment: `deploy/rollback.sh <previous-sha>` (see `DEPLOYMENT.md`).
4. Restore data only from a verified backup and preserve evidence before destructive action.
5. Record timeline, impact, resolution and preventative action. Notify affected parties where applicable.

## Key rotation

Create a new random `ADMIN_API_KEY`, update backend and Quill secret stores in a coordinated maintenance window, deploy/restart the backend, verify one authenticated request, then revoke the old value. Rotate MongoDB credentials through the provider without embedding them in images or commits.

## Routine maintenance

Review Dependabot pull requests weekly. Merge only after CI and compatibility review. Apply security updates promptly, avoid unreviewed major upgrades, review rate-limit behavior and logs monthly, and rehearse rollback and restore procedures before high-traffic campaigns.
