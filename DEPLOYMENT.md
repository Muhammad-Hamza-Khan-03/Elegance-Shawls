# Production deployment

## Required configuration

Set these values in the deployment platform's encrypted secret/environment store. Do not place real values in source control, image layers, screenshots or support messages.

| Variable | Service | Requirement |
|---|---|---|
| `MONGODB_URI` | backend | TLS-enabled production MongoDB connection string with a least-privilege application user |
| `MONGO_DB_NAME` | backend | Dedicated production database name |
| `ADMIN_API_KEY` | backend + frontend server + trusted Quill server if enabled | Matching long random secret (at least 32 random bytes); server-side proxies send it only as `X-Admin-Key`. Never expose it through a `NEXT_PUBLIC_*` variable. |
| `ALLOWED_ORIGINS` | backend | Exact comma-separated HTTPS storefront origin(s), with no wildcard |
| `NEXT_PUBLIC_API_URL` | frontend | Public HTTPS backend origin; baked into the frontend build |
| `NEXT_PUBLIC_SITE_URL` | frontend | Canonical public HTTPS storefront origin; baked into the frontend build |
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | frontend | International digits only, without `+` or spaces |
| `MONGO_ROOT_*`, `MONGO_APP_*`, `MONGO_BACKUP_*` | mongo (compose) | Separate random passwords for the root, application and backup users; see `.env.example` |
| `SITE_DOMAIN`, `API_DOMAIN` | proxy (compose) | Public hostnames Caddy serves and obtains certificates for |
| `INTERNAL_API_TOKEN` | backend + frontend server | Matching random secret. The storefront server sends it on its own reads so server-rendered pages, which all reach the API from one address, are not limited as one client. It only bypasses the public rate limit (never admin routes) and grants no data access. Never expose it through `NEXT_PUBLIC_*`. Unset means no exemption. |
| `PUBLIC_RATE_LIMIT_PER_MINUTE`, `ADMIN_RATE_LIMIT_PER_MINUTE` | backend | Optional per-client limits (defaults 120 and 60) |

Generate the admin key with `openssl rand -hex 32`. Rotate it immediately if exposed. Because `NEXT_PUBLIC_*` values are public and build-time values, changing them requires rebuilding the frontend image.

## Container deployment

`compose.yaml` runs four services: Caddy (`proxy`, the only service with host ports), the Next.js `frontend`, the FastAPI `backend` and MongoDB (`mongo`).

1. Copy `.env.example` to `.env` (mode 600, never committed) and replace every placeholder. Use `openssl rand -hex 32` for `ADMIN_API_KEY` and each MongoDB password; hex keeps them safe inside the connection string. Set `APP_VERSION` to the release git SHA so images are tagged immutably.
2. Point DNS for `SITE_DOMAIN` and `API_DOMAIN` at the host and open ports 80 and 443. Caddy obtains publicly trusted certificates automatically, redirects HTTP to HTTPS, caps request bodies at 1 MB and writes JSON access logs with the admin key, cookies and authorization headers removed.
3. Run `docker compose build --pull` and `docker compose up -d`.
4. Confirm `GET https://$SITE_DOMAIN/api/health` and `/api/ready` and `GET https://$API_DOMAIN/health/` and `/ready/` return 200. Readiness returns 503 within about 2 seconds when MongoDB or the backend is unavailable.
5. Create a uniquely named draft through the admin UI, publish it, verify it appears publicly, then archive it.
6. Schedule backups and the watchdog (`OPERATIONS.md`) and complete the launch checklist before directing traffic.

MongoDB requires authentication. On first start of an empty volume, `deploy/mongo/init-users.sh` creates an application user with `readWrite` on `MONGO_DB_NAME` only, and a backup user with the built-in `backup` role. The backend connects as the application user. MongoDB runs on an internal Docker network with no internet egress and no published port, so only the backend can reach it; traffic on that private network is not TLS-encrypted. For a managed provider (for example Atlas), point `MONGODB_URI` at its TLS connection string with a least-privilege user and IP allowlist instead of running the `mongo` service.

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

`npm run test:e2e:live` drives real Next.js, FastAPI and MongoDB on desktop and mobile; `wa.me` is intercepted so no WhatsApp message is sent. Run `login-throttle` separately and last: it locks the client out of admin sign-in for 15 minutes. Never set `LIVE_IGNORE_HTTPS_ERRORS` against production.

The storefront reverse proxy must preserve the public `Host` and HTTPS request scheme. Admin product mutations require a signed session and an `Origin` matching that public host and scheme. In staging, verify that same-origin create, edit, status, stock, and archive requests succeed and cross-origin requests return 403 without reaching the backend. If legitimate writes return 403, correct the proxy forwarding configuration before release; do not weaken the origin check.

The included Mongo container is suitable for a controlled single-host deployment only when backups, access restrictions and disk monitoring are configured. A managed replica set is preferred for production resilience.

## Admin sign-in protection

`POST /api/admin/session` compares the submitted key in constant time, accepts only JSON bodies, and returns 429 with `Retry-After` after 5 failed attempts from one client within 15 minutes, including when the next attempt uses the correct key. The client is the right-most `X-Forwarded-For` address, so exactly one trusted reverse proxy (or Vercel) must set or append that header; without it, all clients share one throttle bucket, and if the frontend is reachable without passing through that proxy, clients can choose their own throttle key. The counter lives in each frontend process, so it resets on restart and is not shared between instances. Add an edge/proxy rate limit for `/api/admin/session` in production. A long random `ADMIN_API_KEY` remains the primary defence.

Sessions are HMAC-signed, `HttpOnly`, `SameSite=Lax`, `Secure` in production, and expire after 8 hours. Signing out clears the cookie but cannot revoke a copied token before it expires; rotate `ADMIN_API_KEY` to invalidate every session.

## Quill integration

Quill must use the documented `/products/admin/*` routes and send `X-Admin-Key` over HTTPS. It must not call public routes for writes or put the key in query strings, logs or browser code. Validate the exact payload contract against backend OpenAPI at `/docs` in a non-public staging environment.

The currently accessible `quill-panel` does not yet meet this contract and must not be connected to production. See `LAUNCH_RUNBOOK.md` for the verified incompatibilities and acceptance procedure.

## Rollback

Keep the previous release's images (`elegance-backend:<sha>` and `elegance-frontend:<sha>`). If post-deployment checks fail, run `deploy/rollback.sh <previous-sha>` from the repository root. It replaces only the backend and frontend containers with the existing images (no rebuild, no database changes, proxy and certificates untouched), waits until all four probes pass and reminds you to pin `APP_VERSION` in `.env`. Roll forward the same way. Database rollback is a separate restore procedure (`OPERATIONS.md`); never delete or rewrite production product data during an application rollback.
