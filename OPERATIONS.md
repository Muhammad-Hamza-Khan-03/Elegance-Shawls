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

Logs: Caddy writes JSON access logs with the `X-Admin-Key`, `X-Internal-API-Token`, `Cookie`, `Authorization` and `Set-Cookie` headers removed and adds an `X-Request-ID`. The backend logs one JSON line per request (request ID, method, path, status, duration) and never logs headers, query strings, bodies or client addresses. Operators read them with `docker compose logs proxy backend`. Configure Docker's log rotation (`max-size`, `max-file`) or ship logs to central storage, and restrict access to the host. Never log `X-Admin-Key`, database credentials, customer WhatsApp messages, addresses or payment details.

## Backup and restore

**Not automated yet.** The MongoDB backup and restore-drill scripts were removed with MongoDB. PostgreSQL backup, encryption, off-host copies and restore drills are approval-gated issue #105 and have not been built. The database already has a read-only `elegance_backup` role (`pg_read_all_data`) ready for it, and the catalogue data is currently disposable (owner decision), but this must be in place and drilled before real customer or catalogue data is held. Until then, take no backup claims from this document, and treat "pre-launch backup" and "restore drill" items in `LAUNCH_RUNBOOK.md` as blocked on #105.

## Incident response

Incident owner: the repository owner, who receives watchdog and backup alerts.

1. Confirm impact using health endpoints and recent deployment/log data.
2. Stop further risky changes; revoke exposed credentials immediately.
3. Roll back application images when the incident follows a deployment: `deploy/rollback.sh <previous-sha>` (see `DEPLOYMENT.md`).
4. Restore data only from a verified backup and preserve evidence before destructive action.
5. Record timeline, impact, resolution and preventative action. Notify affected parties where applicable.

## Key rotation

Create a new random `ADMIN_API_KEY`, update backend and Quill secret stores in a coordinated maintenance window, deploy/restart the backend, verify one authenticated request, then revoke the old value. Rotate the PostgreSQL role passwords (`ALTER ROLE ... PASSWORD`, then update `.env` and restart the backend) without embedding them in images or commits.

## Routine maintenance

Review Dependabot pull requests weekly. Merge only after CI and compatibility review. Apply security updates promptly, avoid unreviewed major upgrades, review rate-limit behavior and logs monthly, and rehearse rollback and restore procedures before high-traffic campaigns.

## AI platform services (local foundation)

Not deployed by `compose.yaml`; they run from `compose.ai.yaml` for development until the separately approved hosting decisions are made.

- **Two queue systems, deliberately:** PostgreSQL-backed `ingestion_jobs` (`python -m ingestion.worker`, `SELECT ... FOR UPDATE SKIP LOCKED` claims, leases, heartbeats, bounded retries with backoff) run ingestion; the queue semantics are unchanged from the earlier design. Redis/arq (`arq workers.settings.WorkerSettings`) is for new AI workloads only (embeddings, enrichment, memory, ASR). Migrating ingestion to arq is a separate, approved task.
- **Health:** backend `/health/` stays dependency-free. `/ready/` returns 503 when PostgreSQL is down (it holds the catalogue, so data routes answer 503 too); `redis` and `worker` are reported but never gate readiness, and a configured-but-down Redis degrades AI/events features only. Startup fails fast without `DATABASE_URL`; an unreachable database does not crash the process, the pool reconnects.
- **Events:** `POST /v1/events` and the public listing record anonymous events (`GET /products/` logs an `impression` with result positions; it has no server-side query or filters, so server-side search logging arrives with the PostgreSQL-backed search endpoint in Phase 1; client-side search events come from the tracker). Do Not Track / `Sec-GPC` requests are accepted but nothing is stored. Retention: the arq worker runs `purge_events_job` daily at 03:17 UTC (arq cron, one run across replicas; needs `DATABASE_URL` on the worker) and deletes events older than `EVENTS_RETENTION_MONTHS` (18). `python -m events.retention` runs it by hand.
- **LLM model discovery:** `GET /v1/llm/models` and `POST /v1/admin/llm/models/refresh` are admin-key protected. Discovery is advisory only and never edits `LLM_CHAIN_DEFAULT` or `LLM_PRODUCTION_CHAIN`; missing/deprecated models therefore require an explicit operator configuration change. Redis outages leave manual refresh and reads functional through the in-process cache.
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
