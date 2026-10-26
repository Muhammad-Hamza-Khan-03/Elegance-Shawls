# Infrastructure baseline — 2026-10-26

**Status:** infrastructure baseline only; **not a commercial launch**. The production catalog remains intentionally empty. No legacy catalog was imported, and no production catalog changes were made.

## Exact baseline

| Item | Evidence |
|---|---|
| Production `main` SHA | `eb43cec4ef9e560b4a7c57bf6324739c0a696e18` |
| GitHub CI run | `40318847937` — completed successfully; frontend, backend, containers, and E2E checks passed |
| Vercel production deployment | `dpl_3UhNafgzgWxDAxjCqj5DYxEzfbys` — READY |
| Vercel production URL | https://elegance-shawls.vercel.app |
| Render production deployment | `dep-dbfk04g473hc73a5in3g` — live |
| Render API URL | https://elegance-shawls-api.onrender.com |

## Live verification

Verified on 2026-10-26:

- `GET https://elegance-shawls.vercel.app/` returned HTTP 200 and served the Elegance Shawls application HTML.
- `GET https://elegance-shawls.vercel.app/api/health` returned HTTP 200: `{"status":"ok","service":"storefront"}`.
- `GET https://elegance-shawls-api.onrender.com/health/` returned HTTP 200: `{"status":"ok"}`.
- `GET https://elegance-shawls-api.onrender.com/ready/` returned HTTP 200: `{"status":"ready","database":"connected"}`.

These checks verify availability and readiness only. They do not establish commercial launch, catalog readiness, independent QA, or a successful production write flow.

## Network boundary

MongoDB Atlas must allow only `74.220.52.0/24` and `74.220.60.0/24`. `0.0.0.0/0` must remain removed. No credential rotation was performed for this workflow; the previously mentioned QA credential was fake and required no rotation.

## Follow-ups / blocked items

1. Provision and verify a reusable isolated Render staging service and Atlas staging database with separate credentials, separate admin key, exact CORS, and cleanup procedure.
2. Verify Render production automatic deployment is disabled and that production requires an explicit exact-SHA deploy. If the provider control is unavailable or risky, document that limitation rather than changing live infrastructure.
3. Verify Vercel production controls in the provider UI/API without changing the live alias or production deployment. Preview remains the branch-review mechanism.
4. Complete independent QA against the isolated staging tuple before the next production promotion.
5. Add future products manually through the built-in admin; do not import the legacy catalog.

This record intentionally does not claim staging provisioning, provider-control changes, independent QA, or commercial launch without provider evidence.
