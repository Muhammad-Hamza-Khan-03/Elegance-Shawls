# Production deployment

## Required configuration

Set these values in the deployment platform's encrypted secret/environment store. Do not place real values in source control, image layers, screenshots or support messages.

| Variable | Service | Requirement |
|---|---|---|
| `MONGODB_URI` | backend | TLS-enabled production MongoDB connection string with a least-privilege application user |
| `MONGO_DB_NAME` | backend | Dedicated production database name |
| `ADMIN_API_KEY` | backend + Quill | Long random secret (at least 32 random bytes); Quill sends it only as `X-Admin-Key` |
| `ALLOWED_ORIGINS` | backend | Exact comma-separated HTTPS storefront origin(s), with no wildcard |
| `NEXT_PUBLIC_API_URL` | frontend | Public HTTPS backend origin; baked into the frontend build |
| `NEXT_PUBLIC_SITE_URL` | frontend | Canonical public HTTPS storefront origin; baked into the frontend build |
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | frontend | International digits only, without `+` or spaces |

Generate the admin key with `openssl rand -hex 32`. Rotate it immediately if exposed. Because `NEXT_PUBLIC_*` values are public and build-time values, changing them requires rebuilding the frontend image.

## Container deployment

1. Point `SITE_URL` and `API_URL` at the final HTTPS origins and set `WHATSAPP_NUMBER`, `ADMIN_API_KEY` and `MONGO_DB_NAME` in a local server-only `.env` file.
2. Terminate TLS at a trusted reverse proxy. Proxy the public storefront to `127.0.0.1:3000` and the API to `127.0.0.1:8000`.
3. Run `docker compose build --pull` and `docker compose up -d`.
4. Confirm `GET /api/health` returns 200, `GET /api/ready` returns 200, backend `GET /health/` returns 200 and backend `GET /ready/` returns 200.
5. Send a Quill test product through an authenticated admin endpoint, publish it, verify it appears publicly, then archive the test record.
6. Complete the launch checklist in `OPERATIONS.md` before directing traffic.

The included Mongo container is suitable for a controlled single-host deployment only when backups, access restrictions and disk monitoring are configured. A managed replica set is preferred for production resilience.

## Quill integration

Quill must use the documented `/products/admin/*` routes and send `X-Admin-Key` over HTTPS. It must not call public routes for writes or put the key in query strings, logs or browser code. Validate the exact payload contract against backend OpenAPI at `/docs` in a non-public staging environment.

## Rollback

Keep the previous immutable frontend/backend image tags. If post-deployment checks fail, restore both previous application image tags, redeploy, verify readiness, and only then investigate. Database rollback requires a tested restore procedure; do not delete or rewrite production product data during an application rollback.
