# Production deployment

## Required configuration

Set these values in the deployment platform's encrypted secret/environment store. Do not place real values in source control, image layers, screenshots or support messages.

| Variable | Service | Requirement |
|---|---|---|
| `DATABASE_URL` | backend, ingestion worker, `migrate` | `postgresql+asyncpg://` URL of the least-privilege application role. Required: the backend refuses to start without it. In `compose.yaml` it is built from the `POSTGRES_*` values. |
| `ADMIN_API_KEY`, `ADMIN_LEGACY_KEY_EXPIRES_AT` | backend (and a trusted Quill server if still on the shared key) | **Legacy fallback, not the admin sign-in.** The key (at least 32 random bytes, sent as `X-Admin-Key`) is honoured only while the expiry (ISO 8601 with offset, e.g. `2026-12-31T00:00:00+00:00`) is in the future; otherwise it is rejected. Leave both empty once individual accounts exist (see "Admin sign-in protection"). The Next.js frontend does not read it. Never expose it through a `NEXT_PUBLIC_*` variable. |
| `ALLOWED_ORIGINS` | backend | Exact comma-separated HTTPS storefront origin(s), with no wildcard |
| `NEXT_PUBLIC_API_URL` | frontend | Public HTTPS backend origin; baked into the frontend build |
| `NEXT_PUBLIC_SITE_URL` | frontend | Canonical public HTTPS storefront origin; baked into the frontend build |
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | frontend | International digits only, without `+` or spaces |
| `POSTGRES_ADMIN_*`, `POSTGRES_APP_*`, `POSTGRES_BACKUP_*`, `POSTGRES_DB` | postgres (compose) | Separate random passwords for the bootstrap superuser, the application role and the read-only backup role; see `.env.example` |
| `SITE_DOMAIN`, `API_DOMAIN` | proxy (compose) | Public hostnames Caddy serves and obtains certificates for |
| `INTERNAL_API_TOKEN` | backend + frontend server | Matching random secret. The storefront server sends it on its own reads so server-rendered pages, which all reach the API from one address, are not limited as one client. It only bypasses the public rate limit (never admin routes) and grants no data access. Never expose it through `NEXT_PUBLIC_*`. Unset means no exemption. |
| `PUBLIC_RATE_LIMIT_PER_MINUTE`, `ADMIN_RATE_LIMIT_PER_MINUTE` | backend | Optional per-client limits (defaults 120 and 60) |

If you still need the legacy key, generate it with `openssl rand -hex 32` and rotate it immediately if exposed. Because `NEXT_PUBLIC_*` values are public and build-time values, changing them requires rebuilding the frontend image.

PostgreSQL is the only database and is part of `compose.yaml`. Redis, the arq worker, the LLM gateway and events are optional and **not part of the production stack**: their variables (`REDIS_URL`, `SESSION_SIGNING_KEY`, `LLM_*`, `OTEL_ENABLED`) default to disabled. Local services for them live in `compose.ai.yaml`; see the root README and `OPERATIONS.md`.

## Container deployment

`compose.yaml` runs four services: Caddy (`proxy`, the only service with host ports), the Next.js `frontend`, the FastAPI `backend` and PostgreSQL 17 + pgvector (`postgres`), plus a `migrate` one-shot job that `up` never starts.

1. Copy `.env.example` to `.env` (mode 600, never committed) and replace every placeholder. Use `openssl rand -hex 32` for each PostgreSQL password (and for `ADMIN_API_KEY`, which `compose.yaml` still requires to be set even though it is only the legacy fallback, see "Admin sign-in protection"); hex keeps them safe inside the connection string. Set `APP_VERSION` to the release git SHA so images are tagged immutably.
2. Point DNS for `SITE_DOMAIN` and `API_DOMAIN` at the host and open ports 80 and 443. Caddy obtains publicly trusted certificates automatically, redirects HTTP to HTTPS, caps request bodies at 1 MB and writes JSON access logs with the admin key, admin session header, cookies and authorization headers removed.
3. Run `docker compose build --pull`. On a new host, start only the database first (`docker compose up -d --wait postgres`), then apply the schema (see "Database migrations"), then `docker compose up -d`.
4. Confirm `GET https://$SITE_DOMAIN/api/health` and `/api/ready` and `GET https://$API_DOMAIN/health/` and `/ready/` return 200. Backend readiness returns 503 within about 2 seconds when PostgreSQL is unavailable; `/health/` stays dependency-free.
5. Create a uniquely named draft through the admin UI, publish it, verify it appears publicly, then archive it.
6. Set up the watchdog (`OPERATIONS.md`) and complete the launch checklist before directing traffic. Encrypted PostgreSQL backup and restore-drill tooling exists in the repository (`apps/backend/scripts/pg_backup.py`, see `OPERATIONS.md`) but is **not activated**: it needs an owner-approved off-server S3-compatible destination (free-tier/cost confirmed), credentials from the secret manager and separately authorized scheduling. Until a drill on a real off-server copy has passed, backups are a launch prerequisite, not a fact.

On first start of an empty volume, `deploy/postgres/init-roles.sh` creates the `vector` extension, a least-privilege application role (no superuser, createdb, createrole or replication; it owns its tables in `public` and runs the migrations) and a read-only backup role (`pg_read_all_data`), and revokes public access. The backend connects as the application role. PostgreSQL runs on an internal Docker network with no internet egress and no published port, so only the backend and the `migrate` job can reach it; traffic on that private network is not TLS-encrypted. Pointing `DATABASE_URL` at a managed PostgreSQL instead is a separate, approved decision.

### Database migrations

The schema is managed only by Alembic (`apps/backend/migrations`, reversible, applied with `alembic upgrade head`). Ownership is explicit:

- **The operator runs migrations, never the application.** The backend image does not migrate on start, so a deploy or restart can never change the schema by itself.
- **Command (production or staging):** `docker compose --profile tools run --rm migrate`. It runs as the application role on the internal network and is idempotent at `head`.
- **Approval boundary:** running it against staging or production needs separate written approval, a verified backup (`OPERATIONS.md`; tooling exists but must first be activated, see above) and a reviewed `alembic upgrade --sql` or revision list. Agents and CI never run it against a shared environment. Roll back with `alembic downgrade <revision>` only with the same approval.
- **Local or throwaway verification** is the only automatic case: `compose.ai.yaml`'s `migrate` service against a local database, and the Testcontainers integration suite.
- Apply migrations before starting the new backend version; `/ready/` checks connectivity, not the schema revision.

The backend trusts `X-Forwarded-For` (`FORWARDED_ALLOW_IPS=*`) because it is reachable only through Caddy, which replaces any client-supplied value. Do not publish the backend or frontend ports directly.

On a hosted backend (for example Render), the backend's per-client limits are only as accurate as the client address uvicorn sees. Unless `FORWARDED_ALLOW_IPS` trusts the platform's proxy, browser requests are keyed by proxy addresses and share limits. Set it only after confirming how the platform builds `X-Forwarded-For`, so clients cannot choose their own address.

### Local HTTPS acceptance stack

`compose.local.yaml` with `.env.local` (from `.env.local.example`) runs the same stack at `https://store.localhost:8443` and `https://api.localhost:8443`, using certificates from Caddy's local CA:

```bash
docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml up -d --build
cd apps/frontend
set -a; . ../../.env.local; set +a
LIVE_SITE_URL=$SITE_URL LIVE_API_URL=$API_URL LIVE_ADMIN_KEY=$ADMIN_API_KEY \
LIVE_WHATSAPP_NUMBER=$WHATSAPP_NUMBER LIVE_IGNORE_HTTPS_ERRORS=1 \
  npm run test:e2e:live -- admin-lifecycle customer-whatsapp
```

`npm run test:e2e:live` drives real Next.js, FastAPI and PostgreSQL on desktop and mobile; `wa.me` is intercepted so no WhatsApp message is sent. Run `login-throttle` separately and last: it locks the client out of admin sign-in for 15 minutes. Never set `LIVE_IGNORE_HTTPS_ERRORS` against production.

The storefront reverse proxy must preserve the public `Host` and HTTPS request scheme. Admin product mutations require a valid admin session and an `Origin` matching that public host and scheme. In staging, verify that same-origin create, edit, status, stock, and archive requests succeed and cross-origin requests return 403 without reaching the backend. If legitimate writes return 403, correct the proxy forwarding configuration before release; do not weaken the origin check.

The included PostgreSQL container is suitable for a controlled single-host deployment only when backups, access restrictions and disk monitoring are configured. Backups are not scheduled or activated (tooling only, see `OPERATIONS.md`); a managed PostgreSQL service is preferred for production resilience.

## Admin sign-in protection

`POST /api/admin/session` takes `{email, password}` and forwards them to the backend `POST /v1/admin/auth/login`, which verifies the password hash, locks the account after `ADMIN_LOGIN_MAX_FAILURES` (5) failures for `ADMIN_LOGIN_LOCKOUT_SECONDS` (15 min), and issues an opaque server-side session (`ADMIN_SESSION_TTL_SECONDS`, default 8h; only its hash is stored). The frontend keeps a per-process throttle too; add an edge rate limit for `/api/admin/session`.

The `es_admin_session` cookie holds that opaque token (`HttpOnly`, `SameSite=Lax`, `Secure` in production). Sign-out revokes the session server-side. Roles are `viewer`, `editor`, `owner`; every admin mutation and denial is written to `audit_log`. Run `alembic upgrade head` (0007), then create the first owner from `apps/backend`: `python scripts/admin_accounts.py bootstrap-owner --email you@example.com` (password via `ADMIN_ACCOUNT_PASSWORD` or prompt). `ADMIN_API_KEY` is a legacy fallback accepted only until `ADMIN_LEGACY_KEY_EXPIRES_AT` (ISO 8601 with offset; empty, naive or past means rejected, and expiry needs no redeploy); it acts as `editor` plus `platform:operate`, is audited as `legacy-shared-key` and the backend logs a startup warning while it is open. Leave both empty once accounts exist. `compose.yaml` passes `ADMIN_API_KEY` but not `ADMIN_LEGACY_KEY_EXPIRES_AT` to the backend, so in the compose stack the legacy key is rejected unless the expiry variable is also added to the backend environment. Downgrading 0007 refuses when accounts/sessions/audit details exist unless `ALEMBIC_ALLOW_ADMIN_DATA_LOSS=1` (pg_dump first).

Enquiry references (migration 0008): the cart button calls the storefront `POST /api/enquiries`, which forwards to the backend `POST /v1/enquiries`. The backend re-validates every line against the live catalogue (active product and option, current price and currency, stock, no duplicate options, one currency; otherwise 409 `cart_stale`), stores a snapshot with a reference like `ES-7F3K9Q` (no name, phone, address or session id) and the customer then sends the prefilled `wa.me` message themselves. Nothing is ordered, reserved or sent. Staff look references up under `/admin/enquiries` (any admin role). Downgrading 0008 drops the table and refuses while rows exist unless `ALEMBIC_ALLOW_ENQUIRY_DATA_LOSS=1` (pg_dump first). `/v1/enquiries` has its own per-client rate-limit bucket (`EVENTS_RATE_LIMIT_PER_MINUTE`).

## Quill integration

Quill must use the documented `/products/admin/*` routes over HTTPS from a trusted server. Until it can use an individual account (`X-Admin-Session`), it may send the legacy `X-Admin-Key`, which stops working at `ADMIN_LEGACY_KEY_EXPIRES_AT`. It must not call public routes for writes or put credentials in query strings, logs or browser code. Validate the exact payload contract against backend OpenAPI at `/docs` in a non-public staging environment.

The currently accessible `quill-panel` does not yet meet this contract and must not be connected to production. See `LAUNCH_RUNBOOK.md` for the verified incompatibilities and acceptance procedure.

## Rollback

Keep the previous release's images (`elegance-backend:<sha>` and `elegance-frontend:<sha>`). If post-deployment checks fail, run `deploy/rollback.sh <previous-sha>` from the repository root. It replaces only the backend and frontend containers with the existing images (no rebuild, no database changes, proxy and certificates untouched), waits until all four probes pass and reminds you to pin `APP_VERSION` in `.env`. Roll forward the same way. Database rollback is a separate restore procedure (`OPERATIONS.md`); never delete or rewrite production product data during an application rollback.

## Upgrading a database from migration 0009 to head (0015)

Needs explicit approval for any shared database (see `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md` section 5). Procedure and rollback strategy: section 3.11 ("Safe upgrade of an existing database"). In short: verified backup, `python scripts/check_migration_stamp.py`, `alembic current` = 0009, `alembic upgrade head`, embedding backfill. Rollback is a restore of the backup. Never `alembic stamp` a database to a revision it has not really reached.
