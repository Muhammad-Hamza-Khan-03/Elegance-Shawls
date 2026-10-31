# Operations runbook

The step-by-step release procedure and current external blocker are maintained in `LAUNCH_RUNBOOK.md`.

## Launch gate

- CI is green for the exact commit being deployed.
- Production environment values are present and use final HTTPS origins.
- PostgreSQL is private and not exposed to the internet: it runs on the internal-only compose network with no published port and the backend uses the least-privilege application role.
- Quill authentication, create/update/publish/unpublish/archive and inventory changes are verified in staging.
- Browse, filter, product selection, inventory display and WhatsApp order text are verified on desktop and mobile.
- Delivery, returns, privacy, terms and contact wording has been approved by the business owner.
- DNS, TLS, reverse proxy limits and backups have been tested.

## Health and monitoring

Monitor the frontend `/api/health` for liveness and `/api/ready` for configuration/backend connectivity. Monitor backend `/health/` for process liveness and `/ready/` for PostgreSQL connectivity.

`deploy/monitoring/watchdog.sh` implements this for the compose stack. Run it every minute from the host, for example with cron:

```cron
* * * * * cd /srv/elegance && set -a && . ./.env && set +a && ALERT_WEBHOOK_URL=https://hooks.example/... deploy/monitoring/watchdog.sh 2>>/var/log/elegance-watchdog.log
```

It alerts once when a problem starts and once when it recovers. It covers: any probe failing for 3 consecutive runs; 5 or more backend 5xx responses in 5 minutes; a container restarting, missing or unhealthy; root disk at 85% or more; and container memory at 90% or more. `ALERT_WEBHOOK_URL` receives `{"text": "..."}`, which Slack, Discord (`/slack` suffix) and most chat webhooks accept. Thresholds are environment variables documented in the script.

Logs: Caddy writes JSON access logs with the `X-Admin-Key`, `X-Admin-Session`, `X-Internal-API-Token`, `Cookie`, `Authorization` and `Set-Cookie` headers removed and adds an `X-Request-ID`. The backend logs one JSON line per request (request ID, method, path, status, duration) and never logs headers, query strings, bodies or client addresses. Operators read them with `docker compose logs proxy backend`. Configure Docker's log rotation (`max-size`, `max-file`) or ship logs to central storage, and restrict access to the host. Never log `X-Admin-Key`, `X-Admin-Session`, admin passwords, database credentials, customer WhatsApp messages, addresses or payment details.

## Backup and restore

**Status: code foundation built (M1-S5, issue #105); nothing is activated.** No backup has ever run against a shared or production database, no off-server destination exists, nothing is scheduled, and no restore has been drilled outside disposable test containers. Treat the "encrypted backup", "pre-launch backup" and "isolated restore drill" launch items as **still open** until the owner steps below are done and evidence is recorded.

### What the repository provides

`apps/backend/scripts/pg_backup.py` (library in `apps/backend/backup/`), run from `apps/backend`, configured only through environment variables (secrets also as `NAME_FILE`, a path to an owner-only file from the deployment secret manager; never as arguments):

| Command | Does |
|---|---|
| `backup` | Checks the role is the least-privilege backup role, runs `pg_dump --format=custom`, validates the archive, encrypts it, proves it decrypts, uploads data then manifest, re-verifies from the destination, then applies retention |
| `verify [--stem S]` | Downloads the newest (or given) backup, checks the manifest MAC and ciphertext digest, decrypts, checks the plaintext digest and `pg_restore --list` |
| `decrypt --output FILE [--stem S]` | Writes the verified plaintext archive (mode 0600, refuses to overwrite) for a real recovery |
| `check-freshness` | Exit 7 if the newest complete backup in the destination is missing or older than `BACKUP_MAX_AGE_HOURS` (26) |
| `restore-drill --confirm-disposable-target restore_drill_x --evidence-dir DIR [--stem S]` | Restores into an empty disposable database and writes an evidence JSON |

| Variable | Meaning |
|---|---|
| `BACKUP_DATABASE_URL` | `postgresql://elegance_backup:<password>@host:port/db` for the read-only backup role (the compose wrapper ignores host/port) |
| `BACKUP_ENCRYPTION_PASSPHRASE` | Generated secret, 32+ characters (`openssl rand -hex 32`). **Losing it makes every backup unrecoverable; store it separately from the backups and the server.** |
| `BACKUP_STORE_DIR` | Local directory destination. **Not off-server**; for tests and disposable drills only (the CLI warns) |
| `BACKUP_PREFIX`, `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`, `BACKUP_MAX_AGE_HOURS`, `BACKUP_WORK_DIR` | `postgres`, 14, 8, 26, system temp |
| `PG_DUMP_CMD`, `PG_RESTORE_CMD`, `PSQL_CMD` | Optional tool wrappers. With the compose database (internal network, no published port) use `deploy/postgres/container-pg.sh <tool>` (set `POSTGRES_CONTAINER` if the container is not `elegance-shawls-postgres-1`); otherwise install the PostgreSQL 17 client |
| `RESTORE_DRILL_DATABASE_URL` | Drill target, see below |

Compose example, from `apps/backend` (values come from the secret manager; this runs against the real database, so it is an operator step under "Activation" below, not something agents run):

```bash
export PG_DUMP_CMD="../../deploy/postgres/container-pg.sh pg_dump" PG_RESTORE_CMD="../../deploy/postgres/container-pg.sh pg_restore" PSQL_CMD="../../deploy/postgres/container-pg.sh psql"
python scripts/pg_backup.py backup
```

**Format and integrity.** Each backup is two objects, `<prefix>/elegance-<UTC timestamp>.pgdump.enc` and `.manifest.json`. The archive is AES-256-CBC with a PBKDF2-derived key and random salt, made with the standard `openssl` CLI. The manifest records the SHA-256 of plaintext and ciphertext, the KDF parameters, the table list and Alembic revision (no hostnames or credentials) and an HMAC-SHA256 over itself keyed from the same passphrase. Verification authenticates the manifest and ciphertext **before** decrypting, so a wrong passphrase, corruption, truncation or tampering is rejected. The manifest is uploaded last, so an archive without one is an unfinished upload and is ignored. Objects are never overwritten. The plaintext dump exists only in a private (0700) temporary directory and is removed afterwards; size the temp filesystem for one uncompressed dump.

**Least-privilege contract.** The backup role is created by `deploy/postgres/init-roles.sh`: login only, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`, `CONNECT` on the one database, `USAGE` on `public`, member of `pg_read_all_data`, nothing else. Every `backup` run checks this on the live connection first (no superuser/createdb/createrole/replication/bypassrls, no `CREATE` on the database or `public`, member of `pg_read_all_data`, not of `pg_write_all_data`, no write privilege on any public table) and refuses to dump as the application or admin role. Tests prove the contract against disposable containers only; nothing was applied to a shared database. A database created before this script ran needs the equivalent grants applied by the owner.

**Retention.** After a successful, verified backup only: keep the newest backup of each of the `BACKUP_KEEP_DAILY` most recent days and `BACKUP_KEEP_WEEKLY` most recent ISO weeks that have a backup (default 14 + 8, per the architecture). Days and weeks are counted among existing backups, so a long outage never ages out the last good copies, and a failed run never prunes. A retention failure does not discard the new backup but exits 6.

**Failure and alert semantics.** Failures print `ALERT elegance-backup <code>: <message>` to stderr, never contain passwords or the passphrase (URL credentials and tool output are redacted), and exit non-zero: 2 configuration/usage, 3 dump, 4 verification/integrity, 5 destination, 6 retention (backup itself succeeded), 7 stale or no backup, 8 restore drill, 9 role contract violated, 1 unexpected. The CLI does not send notifications. The scheduler that is later approved must (a) alert the incident owner on any non-zero exit and (b) run `check-freshness` separately as a dead-man's switch, because a scheduler that silently stops produces no failure. `check-freshness` trusts object names; `verify` proves content, so run it at least weekly.

### Restore drill

The drill proves a backup restores, on a **disposable PostgreSQL instance that is not the source**. The CLI refuses unless the database name matches `restore_drill_[a-z0-9_]+`, the name is typed again in `--confirm-disposable-target`, the host is local (`localhost`, `127.0.0.1`, `::1` or unset), the instance differs from `BACKUP_DATABASE_URL`'s host and port, and the database is empty. It restores with `--exit-on-error --single-transaction --no-owner --no-acl` and checks that every table in the manifest exists and the Alembic revision matches. Evidence (`drill-<UTC>.json`, mode 0600) records the backup, ciphertext digest, MAC result, per-table row counts, revision, timings and result; failures still write it and exit 8. Row counts are evidence for a human to compare with the source, not an equality gate, because a live source keeps changing.

```bash
docker run -d --rm --name es-drill -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" -e POSTGRES_DB=restore_drill_$(date +%Y%m%d) pgvector/pgvector:0.8.1-pg17
# RESTORE_DRILL_DATABASE_URL=postgresql://postgres:<that password>@127.0.0.1:55432/restore_drill_YYYYMMDD
python scripts/pg_backup.py restore-drill --confirm-disposable-target restore_drill_YYYYMMDD --evidence-dir ./drill-evidence
docker stop es-drill   # destroys the target; each drill needs a fresh one
```

Record the evidence file with the date in the launch checklist. Cadence per the architecture: automated drill monthly, full drill quarterly (RPO 24 h, RTO 4 h targets).

### Real recovery (manual, approval-gated, not scripted)

`decrypt` a verified archive, create a fresh stack so `init-roles.sh` makes the roles, run `pg_restore --exit-on-error --single-transaction --dbname=<db>` as the bootstrap superuser (ownership and grants are kept in the dump, so do not use `--no-owner`), then check readiness and counts. This path has been exercised only as the disposable drill above, with ownership stripped; rehearse it on a throwaway stack before relying on it.

### Activation: what code cannot do (owner actions)

The repository cannot verify any of these; each is a separate decision.

1. **Choose and approve an off-server S3-compatible destination and its cost.** No real adapter exists: `backup/store.py` defines the `ObjectStore` contract (`put`, `get`, `list`, `delete`, immutable objects) and the `S3Settings` configuration shape (`BACKUP_S3_ENDPOINT` https only, `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `BACKUP_S3_REGION`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`). The architecture assumes Cloudflare R2 inside its free allowance, but that is unconfirmed: the owner must pick the provider, confirm the free-tier limits cover the retained backups, and approve any cost. Writing the adapter against the chosen provider is then a small follow-up that must pass the same contract tests. Until then the CLI refuses to start if `BACKUP_S3_ENDPOINT` is set rather than ignoring it, and a local directory is the only destination.
2. **Provide credentials through the deployment secret manager** (bucket credentials scoped to one bucket with no delete-bucket rights, the backup role password, the encryption passphrase kept apart from the backups), and generate the passphrase.
3. **Separately authorize scheduling and production activation**: choosing the scheduler and host, the alert channel for non-zero exits and for `check-freshness`, the first production backup, the first drill against it, and recording the evidence. Agents and CI never run backups against production.
4. Until 1-3 are done and a drill on a real off-server copy has passed, no document may claim backups exist.

## Incident response

Incident owner: the repository owner, who receives watchdog and backup alerts.

1. Confirm impact using health endpoints and recent deployment/log data.
2. Stop further risky changes; revoke exposed credentials immediately.
3. Roll back application images when the incident follows a deployment: `deploy/rollback.sh <previous-sha>` (see `DEPLOYMENT.md`).
4. Restore data only from a verified backup and preserve evidence before destructive action.
5. Record timeline, impact, resolution and preventative action. Notify affected parties where applicable.

## Key rotation

Admin people use individual accounts, so there is no shared secret to rotate for them. Account recovery and offboarding: `python scripts/admin_accounts.py reset-password --email <addr>` (from `apps/backend`; revokes all of the account's sessions) or an owner disabling the account via `/v1/admin/accounts/{id}` (revokes sessions; the last active owner cannot be removed). If no owner can sign in, run `bootstrap-owner` (it only creates one when no active owner exists). Review who did what in `audit_log` (owners: `GET /v1/admin/audit`); it is append-only and attributes each mutation to the account UUID, or `legacy-shared-key`.

The legacy `ADMIN_API_KEY` is an expiring fallback (accepted only before `ADMIN_LEGACY_KEY_EXPIRES_AT`, an ISO 8601 instant with offset). To retire it, set both variables empty and restart, or let the expiry pass; it stops working with no code change. If it is exposed while still enabled, empty or expire it immediately; if a replacement is still needed, create a new random value (update backend and Quill secret stores in a coordinated maintenance window, verify one authenticated request, then revoke the old value). Rotate the PostgreSQL role passwords (`ALTER ROLE ... PASSWORD`, then update `.env` and restart the backend) without embedding them in images or commits.

## Routine maintenance

Review Dependabot pull requests weekly. Merge only after CI and compatibility review. Apply security updates promptly, avoid unreviewed major upgrades, review rate-limit behavior and logs monthly, and rehearse rollback and restore procedures before high-traffic campaigns.

## AI platform services (local foundation)

Not deployed by `compose.yaml`; they run from `compose.ai.yaml` for development until the separately approved hosting decisions are made.

- **Two queue systems, deliberately:** PostgreSQL-backed `ingestion_jobs` (`python -m ingestion.worker`, `SELECT ... FOR UPDATE SKIP LOCKED` claims, leases, heartbeats, bounded retries with backoff) run ingestion; the queue semantics are unchanged from the earlier design. Redis/arq (`arq workers.settings.WorkerSettings`) is for new AI workloads only (embeddings, enrichment, memory, ASR). Migrating ingestion to arq is a separate, approved task.
- **Health:** backend `/health/` stays dependency-free. `/ready/` returns 503 when PostgreSQL is down (it holds the catalogue, so data routes answer 503 too); `redis` and `worker` are reported but never gate readiness, and a configured-but-down Redis degrades AI/events features only. Startup fails fast without `DATABASE_URL`; an unreachable database does not crash the process, the pool reconnects.
- **Events:** `POST /v1/events` and the public listing record anonymous events (`GET /products/` logs an `impression` with result positions; it has no server-side query or filters, so server-side search logging arrives with the PostgreSQL-backed search endpoint in Phase 1; client-side search events come from the tracker). Do Not Track / `Sec-GPC` requests are accepted but nothing is stored. Retention: the arq worker runs `purge_events_job` daily at 03:17 UTC (arq cron, one run across replicas; needs `DATABASE_URL` on the worker) and deletes events older than `EVENTS_RETENTION_MONTHS` (18). `python -m events.retention` runs it by hand.
- **LLM model discovery:** `GET /v1/llm/models` and `POST /v1/admin/llm/models/refresh` require an admin account with the `platform:operate` permission (an `owner`, or the legacy key while it is enabled). Discovery is advisory only and never edits `LLM_CHAIN_DEFAULT` or `LLM_PRODUCTION_CHAIN`; missing/deprecated models therefore require an explicit operator configuration change. Redis outages leave manual refresh and reads functional through the in-process cache.
- **Observability:** each request has a W3C-compatible trace ID in `X-Trace-ID` and the access log. Trace context follows the work: browser reads and the events tracker send a W3C `traceparent` (the Next.js events handler continues or starts one), the API request span has PostgreSQL child spans (operation only, never SQL or parameters), and the API puts it in arq job payloads so the worker job continues the same trace. OTLP export (`opentelemetry-exporter-otlp-proto-http`) stays off unless `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` are set; credentials go in `OTEL_EXPORTER_OTLP_HEADERS` in the environment only; Langfuse generation tracing is off unless `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` are all set (package in `requirements-llm.txt`). Span attributes are PII-scrubbed and prompts are never recorded.
- **Approval boundaries:** no production or staging change, hosted PostgreSQL/Redis, paid provider, credential creation, catalogue switch or production database change happens without separate written approval.

## Product ingestion (Phase 1)

Ingestion is off until an operator sets `INGESTION_SOURCE_DOMAIN` and `INGESTION_SOURCE_AUTHORIZED=true`; do this only for a source the business is authorized to use, and only on an isolated staging environment first. Staged products are never public; a reviewer approves and then publishes them in the admin UI (`/admin/staging`). The worker is a separate process (`python -m ingestion.worker`). Roll back by stopping the worker; staged and job collections are additive and can be left in place. See `docs/phase-1-one-source-ingestion.md`.

### Monthly one-shot refresh (local, no always-on worker)

`python -m ingestion.worker --once` (run from `apps/backend`) refreshes every enabled and authorized source, then exits. It reads the source's sitemap, queues idempotent jobs only for new or changed product URLs, processes that finite batch one product at a time and prints a sanitized JSON summary (`--summary-file PATH` also saves it). It never approves, publishes, archives or deletes: new and changed products land in `pending_review`, reviewed products are only flagged `source_changed`, and products missing from the sitemap are reported, not touched.

- `--dry-run` plans the run with no database writes; `--discovery-only` reads sitemaps only and needs no database access.
- It refuses to run unless the database named in `DATABASE_URL` contains the word `staging` (and not `prod`). Secrets come from the environment or the ignored `apps/backend/.env`, never from arguments.
- Limits: 500 product URLs per source (more fails with `discovery_limit_exceeded`, nothing is processed), 45 minutes total, 3 attempts per job, 2 seconds between requests, one request at a time. Exit code is 0 only for a fully completed run.
- The run happens on a trusted local machine that can reach the staging database. Do not use GitHub-hosted runners, do not expose the database publicly, and do not run a paid always-on worker.

**Local helper.** `apps/backend/scripts/monthly_refresh.sh [--once|--dry-run|--discovery-only]` wraps the command: it re-checks the staging database name, takes a `flock` lock so two runs cannot overlap (exit 75), writes a timestamped sanitized summary to `apps/backend/.refresh-output/` (a self-ignoring directory) and returns the command's exit code. It accepts no other arguments, so secrets can never be passed on the command line.

`apps/backend/.env` (ignored by git) needs, with real values only on your machine: `DATABASE_URL` (a staging PostgreSQL user and a database named like `elegance_shawls_staging`, migrated with `alembic upgrade head`), `INGESTION_SOURCE_ID=scarves-australia`, `INGESTION_SOURCE_NAME`, `INGESTION_SOURCE_DOMAIN=scarvesaustralia.com.au`, `INGESTION_ALLOWED_HOSTS=www.scarvesaustralia.com.au`, `INGESTION_IMAGE_HOSTS=cdn.shopify.com` and `INGESTION_SOURCE_AUTHORIZED=true`. Run `--discovery-only`, then `--dry-run`, before the first `--once`.

Example crontab entry (install it yourself; nothing installs it automatically). It runs at 02:00 on the 1st of each month. Use your own paths:

```
0 2 1 * * cd /path/to/Elegance-Shawls/apps/backend && flock -n /tmp/elegance-monthly-refresh.lock python3.11 -m ingestion.worker --once --summary-file /path/to/local/ignored/refresh-summary.json >> /path/to/local/ignored/refresh.log 2>&1
```

or, using the helper (which also keeps its own lock and output directory):

```
0 2 1 * * /path/to/Elegance-Shawls/apps/backend/scripts/monthly_refresh.sh >> /path/to/local/ignored/refresh.log 2>&1
```

Review: open `/admin/staging`, check each `pending_review` product, set the PKR price and stock, approve (creates an inactive draft), then publish separately.
