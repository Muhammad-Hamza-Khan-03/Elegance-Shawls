# Production preparation — 25 October 2026
> **Historical record (pre-PostgreSQL).** Everything below describes the earlier MongoDB/Atlas-backed deployment validation. MongoDB, the Atlas catalogue and `scripts/import_legacy_catalog.py` were retired in S4; the catalogue is now PostgreSQL-only and the legacy data was declared disposable. Kept for audit only; it is not current setup guidance.


Release remains blocked until reviewed code, isolated preview/backend validation, WhatsApp configuration and live checks are complete.

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
- Render's latest deployment remains `update_failed` at `0140e8ff166da3887f8d9da07420655aca323c74`, predating credential recovery. The service tracks `main` and has not been redeployed.
- The dedicated Atlas application credential was recovered under explicit owner approval and stored only in Render as `MONGODB_URI`. `MONGO_DB_NAME` is confirmed configured for `elegance_shawls`. A read-only check using the stored credential passed ping, authenticated as the intended application user, and read the empty products collection. Its readWrite role remains limited to this database and cluster. No catalog records were imported.
- `ADMIN_API_KEY` was rotated once under explicit owner approval and the same value stored in Render and Vercel Production. Vercel confirms sensitive storage. It was not copied to Preview or Development.
- The exposed Vercel deployment hook was revoked. The authenticated dashboard explicitly confirms that the project has no deployment hooks. Its value is absent from this document and commits.
- `NEXT_PUBLIC_WHATSAPP_NUMBER` remains unknown and must be supplied by the owner. No production placeholder is configured.
- The Atlas admin connection is now active and project access is verified.
- Vercel Preview has branch-scoped `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SITE_URL`. `ADMIN_API_KEY` and `NEXT_PUBLIC_WHATSAPP_NUMBER` are absent in Preview; Development remains unconfigured. No production secrets were copied into Preview.
- Atlas currently permits `0.0.0.0/0`; replace it with the backend provider's required egress ranges before go-live.

## Local validation results

| Check | Result |
| --- | --- |
| Runtime | Node.js 22.23.4; Python 3.12 |
| npm installation | Passed |
| Frontend lint/typecheck | Passed |
| Frontend unit tests | 26 passed, including admin-proxy authentication and stalled-backend sitemap regressions |
| Backend tests | 21 passed, including import safety/idempotency checks |
| Frontend production build | Local Node.js 22.23.4 build passed with the unavailable Render API configured; sitemap completes using its static fallback |
| Frontend production-only/full audits | Zero findings |
| Backend dependency audit | Zero findings |
| Browser E2E | 12 passed: desktop Chromium and emulated Pixel 7 |
| HTTP integration | 19 passed across actual Next.js and FastAPI servers with in-memory MongoDB persistence |
| Live Atlas / Render / Vercel E2E | Atlas authenticated read passed; backend is not deployed successfully; Vercel Preview build failed at sitemap generation; live application E2E remains blocked |

The standard Playwright browser CDN download failed in this workspace. The same committed suite passed with a temporary Chromium 153 executable, outside the application dependency tree. This temporary executable/configuration is not committed. CI still uses its normal Playwright installation. Browser tests use the repository's mock API; HTTP integration exercises the real FastAPI routes with mongomock, not live Atlas.

Reproduce the local HTTP integration with the backend development venv: `python apps/backend/scripts/verify_local_api_flow.py`. It verifies anonymous access rejection, login/logout, private-key isolation, CRUD, draft/public isolation, stock, archive and CORS without production credentials.

## Preview build diagnosis and local fix

PR #84 remains draft and unmerged at `8519c2dd50d615bd2a6e2a50e3a3406888c19e24`. Its five published checks pass: frontend, backend, containers, e2e and Vercel Preview Comments.

A manual deployment of this exact commit was created with the dashboard's explicit Preview target: `dpl_3dGFTsANrNZ9ec6d1JNvminXbtNu`. Its environment is Preview (`target: null` in the API), not Production. It compiled and typechecked, then failed because `/sitemap.xml` waited indefinitely for the unavailable backend and exceeded Next.js's 60-second prerender limit three times.

The fix adds an optional abort signal to `api.getProducts` and gives sitemap generation the existing readiness check's four-second backend deadline. On timeout, the sitemap retains its existing static-page fallback. Two regression cases cover a stalled request and a normal product response. Lint, typecheck, all 26 frontend unit tests and a Node.js 22 production build pass. The published CI results above apply to the earlier commit; the resulting fix commit needs its own required checks and Preview build before readiness can be established.

The earlier unexpected feature-branch Production build remains canceled. Production branch tracking is `main`, and Preview tracking is enabled. Automatic approval review previously rejected globally disabling previews. A narrower `git.deploymentEnabled` guard is included only for `fix/production-deployment-readiness`, preventing pushes to this PR branch from automatically deploying while retaining the explicit manual Preview workflow. Other branches retain their default behavior. This guard is not permission to deploy a feature branch to Production.

The API's `staging` target was rejected by automatic approval review; its literal `preview` target was rejected by Vercel with HTTP 400. The explicitly labeled dashboard Preview action succeeded. No production deployment, source-data migration or merge has been performed.

## Preview-only QA workflow

- `apps/frontend/vercel.json` sets `git.deploymentEnabled` to `false` only for `fix/production-deployment-readiness`. Other branches retain their default behavior. This blocks automatic deployments from this PR branch while retaining the manual Preview workflow authorized by the owner.
- Publish the sitemap fix to the existing draft PR, rerun its required checks, then create a manual Preview from the resulting exact commit.
- Proposed, not provisioned: use a separate Free Render service named `elegance-shawls-api-pr84`, root `apps/backend`, Docker runtime, PR branch, and auto-deploy off. Verify the deployed SHA against the checked PR commit. Reuse it if it already exists; do not change the production service.
- Use an empty `elegance_shawls_pr84` database with a separate application user scoped only to that database and cluster. Store its connection string only in the QA Render service. Generate a separate `ADMIN_API_KEY` for the QA service and branch-scoped Vercel Preview; never reuse the production key.
- Configure QA CORS to the verified Preview origin. Keep the unknown business WhatsApp variable absent and report checkout validation blocked. Use only synthetic, disposable CRUD fixtures in the QA database, with cleanup; do not import catalog records.
- Render service previews inherit base-service environment variables on creation. Do not launch an inherited preview against production credentials as a shortcut. The connected Render tools do not expose service creation; provider setup is required for this isolated target.

Vercel's branch-specific Git deployment control is documented at https://vercel.com/docs/project-configuration/git-configuration .
