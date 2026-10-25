# Production preparation — 25 October 2026

Release remains blocked until provider secrets, catalog review and live checks are complete.

## Catalog decision

Atlas project `696d091e3f963b8e658ae2ad` / cluster `EleganceShawls-cluster` contains the legacy `quill_ecommerce` catalog: 29 products, 18 active and 11 archived. None has the current API's `variants`, `cover_image_url` or `is_active` fields; the current public query matches zero records. The separate `elegance_shawls.products` collection was created for the current API. Source products were not changed or imported.

`apps/backend/scripts/import_legacy_catalog.py` defaults to a read-only preview. It maps the legacy schema, keeps archived products archived, prepares other products as drafts with zero stock, and refuses to round prices or infer unsupported categories. `--apply` requires explicit use and inserts into a different database without overwriting existing slugs. An Atlas maintenance credential must be supplied through the existing `MONGODB_URI` environment variable, never a CLI argument.

The verified source snapshot produced 22 valid records and 7 requiring review: four have invalid/non-HTTPS images and three have unsupported categories. The import aborts before any target write if any record is invalid. Prices, currency, stock, sizes and image rights must be reviewed before publication.

## Application changes

- Upgrade Next.js and eslint-config-next together to 16.4.3 and Vitest to 4.1.12; refresh affected transitive dependencies and remove obsolete overrides. No force fixes or toolchain downgrades.
- Upgrade PyMongo to 4.18.2, within Motor's supported dependency range.
- Require a valid signed admin session on every frontend admin proxy route before the private backend key is attached. Reject malformed cookies safely.
- Restore saved carts after hydration so server and client initially render the same cart count. Keep the API-failure browser fixture unavailable until the explicit retry, including React development-mode re-runs.
- Document the matching server-only `ADMIN_API_KEY` in the frontend template and container runtime configuration.
- Ignore secret-bearing dotenv variants and Vercel local state while permitting example templates.

## Security evidence

Both `npm audit --omit=dev` and full `npm audit` report zero findings on the prepared branch. `pip-audit -r requirements.txt` reports no known vulnerabilities.

The `braces@3.0.3` path through micromatch/fast-glob remains installed. GitHub withdrew GHSA-vfj7-8cjw-p6xm on 23 October 2026 as not practically exploitable: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm . This explains its disappearance from npm audit; it was not removed by an override or downgrade. Issue #83 has not been closed or bypassed, and PR #65 has not been changed or merged.

## Provider state and unresolved inputs

- Vercel project: `prj_K4oWcap4jTwAr7qxkqUcIRUURRNL`; assigned domain `elegance-shawls.vercel.app`.
- Render service: `srv-dbevq7u7bikc73bm4rk0`; `https://elegance-shawls-api.onrender.com`.
- Render `MONGO_DB_NAME` was set to `elegance_shawls`; no deployment was requested.
- A dedicated Atlas account `elegance_render_app` was created with readWrite access only to the new database and scoped to this cluster. A local formatting error interrupted transfer of its one-time generated password before storage in Render. The password was not exposed or retained; secure recovery/reset is required before the account can be used. No pre-existing credential was changed.
- Automatic approval review rejected retrieving Render's `ADMIN_API_KEY`, even internally. Secret presence and matching values must be verified through an approved secure flow or owner-entered provider settings.
- A Vercel deployment-hook URL was inadvertently included in diagnostic output. It has not been used, repeated in this document or committed. Treat it as exposed; revocation/replacement requires owner approval under the no-rotation rule.
- `NEXT_PUBLIC_WHATSAPP_NUMBER` remains unknown and must be supplied by the owner. No production placeholder is configured.
- ChatGPT's Atlas connection works. Composio's separate MCP identity returned 403 during the last test.
- Atlas currently permits `0.0.0.0/0`; replace it with the backend provider's required egress ranges before go-live.

## Local validation results

| Check | Result |
| --- | --- |
| Runtime | Node.js 22.23.4; Python 3.12 |
| npm installation | Passed |
| Frontend lint/typecheck | Passed |
| Frontend unit tests | 24 passed, including admin-proxy authentication regressions |
| Backend tests | 21 passed, including import safety/idempotency checks |
| Frontend production build | Passed |
| Frontend production-only/full audits | Zero findings |
| Backend dependency audit | Zero findings |
| Browser E2E | 12 passed: desktop Chromium and emulated Pixel 7 |
| HTTP integration | 19 passed across actual Next.js and FastAPI servers with in-memory MongoDB persistence |
| Live Atlas / Render / Vercel E2E | Blocked by provider secret configuration and owner inputs |

The standard Playwright browser CDN download failed in this workspace. The same committed suite passed with a temporary Chromium 153 executable, outside the application dependency tree. This temporary executable/configuration is not committed. CI still uses its normal Playwright installation. Browser tests use the repository's mock API; HTTP integration exercises the real FastAPI routes with mongomock, not live Atlas.

Reproduce the local HTTP integration with the backend development venv: `python apps/backend/scripts/verify_local_api_flow.py`. It verifies anonymous access rejection, login/logout, private-key isolation, CRUD, draft/public isolation, stock, archive and CORS without production credentials.

No production deployment, source-data migration or merge has been performed. Automatic approval review rejected disabling preview deployments, so preview settings were left unchanged. Publishing a branch/PR may trigger the existing preview integration; production release still requires exact-commit CI and live-provider validation.
