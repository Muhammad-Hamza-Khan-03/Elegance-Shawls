# Phase 1 QA handoff — one-source product ingestion

> **Historical record (pre-PostgreSQL).** Written when the catalogue ran on MongoDB; those parts no longer apply. Current setup: `DEPLOYMENT.md`.

> **Admin authentication note.** Any shared `ADMIN_API_KEY` / HMAC-signed session-cookie description below is the retired flow. Current behaviour: individual admin accounts with opaque server-side `X-Admin-Session` sessions, a server-side Next.js proxy, audit attribution, and `ADMIN_API_KEY` only as an expiring legacy fallback (`docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md` 3.9, `DEPLOYMENT.md`).

**Status: implementation complete on fixtures; independent QA NOT yet performed.** Implementation tests below are not independent QA. This record must not be treated as staging evidence.

**Code under test:** branch `phase-1/one-source-ingestion`, commit `32c9520405e4926c91840386b000d5ca7bd06113` (docs-only commits may follow; re-record the SHA QA actually deploys).

## Inputs

| Item | Status |
|---|---|
| Staging API | `https://elegance-shawls-api-staging.onrender.com` (ready; admin key configured, unauthenticated admin calls return 401) |
| Source | Scarves Australia, `INGESTION_SOURCE_ID=scarves-australia`, `INGESTION_SOURCE_DOMAIN=scarvesaustralia.com.au`, **`INGESTION_ALLOWED_HOSTS=www.scarvesaustralia.com.au` (new; must be set on staging API and worker)**, `INGESTION_IMAGE_HOSTS=cdn.shopify.com` (approved by the owner; authorization flag set on staging) |
| Field extractor | `ShopifyHtmlExtractor`, deterministic, wired into the worker |
| Staging worker | **not deployed yet** (deploy after this handoff is reviewed; spec below) |
| Deployed commit SHA | to be recorded from the Render deploy (not exposed by the API) |
| Job IDs / live evidence | none yet; no live crawl has been run |

## Implementation evidence (developer-run, local fixtures)

- Backend `pytest -q`: 220 passed (31 baseline). `python -m compileall -q .` PASS. `pip-audit -r requirements.txt`: no known vulnerabilities.
- Frontend `npm test`: 149 passed (95 baseline). `npm run lint`, `npm run typecheck`, `npm run build` PASS.
- Not run: `npm run test:e2e` (Playwright mock API has no ingestion endpoints), any Docker/compose stack, any real network fetch.

## Staging worker spec (to deploy after review)

Separate Render **background worker**, same repository and backend image/build as the API, start command `python -m ingestion.worker` from `apps/backend`. Same staging environment as the API: `MONGODB_URI` / `MONGO_DB_NAME` (the isolated staging database), `INGESTION_SOURCE_ID`, `INGESTION_SOURCE_NAME`, `INGESTION_SOURCE_DOMAIN`, `INGESTION_ALLOWED_HOSTS`, `INGESTION_SOURCE_AUTHORIZED`, `INGESTION_IMAGE_HOSTS`. It needs no admin key and no inbound port. Run exactly one instance. Do not point it at production. Stopping the worker is the rollback; jobs stay queued and resume later.

## QA script

1. Confirm the target is staging: separate DB, staging-only key, no production data.
2. Unauthenticated and wrong-key calls to every `/products/admin/ingestion/*` route return 401; the browser proxy returns 401 without a session and 403 cross-origin.
3. `POST /products/admin/ingestion/jobs` with a full URL, `//host/...`, or `/products/../x` returns 422.
4. Queue one real product path (`/products/<handle>`) from the approved source. Do not queue a catalogue crawl. Record the job ID. Job goes queued → running → succeeded (`GET .../jobs/{id}`).
5. Staged product appears as `pending_review`; it is absent from `GET /products/` and `/products/slug/{slug}`. Check name, images, source URL, source price/currency, missing fields, stock unknown.
6. Re-queue the same path and rerun the job: still exactly one staged product (outcome `unchanged`).
7. `publish` before approval returns 409. Approve with a PKR price and stock: product exists as draft, still not public.
8. Publish: visible in the storefront. Unpublish: hidden again. Archive: hidden, publish returns 409.
9. A second product: reject with a reason; confirm it never reaches `products` or the public API.
10. Generic `PATCH /products/admin/{id}/status {"status":"active"}` on an ingested draft returns 409.
11. Kill the worker mid-job (or set a short `INGESTION_JOB_LEASE_SECONDS`) and confirm lease recovery and bounded retries ending in `failed` with `last_error`.
12. Clean up QA staged/product/job documents afterwards.

Record for each step: pass/fail, timestamp, job IDs, and the exact deployed commit SHA and URLs.

## Open items / known limitations

- **Real markup is unverified.** The extractor targets standard Shopify/schema.org structures and was tested on fixtures only. Expect the first live run to be the real test; failed jobs carry a specific `last_error`.
- **Hosts.** Approved: `scarvesaustralia.com.au` and `www.scarvesaustralia.com.au`, exact match only; redirects are revalidated per hop and may move between those two hosts and nowhere else. Staged URLs use the canonical apex host. `INGESTION_ALLOWED_HOSTS` must be set or an apex-to-www redirect fails with "Host is not on the source allowlist".
- **Category.** Approved mapping (first explicit term in category, title or URL handle): scarf/scarves → `scarves`; stole/stoles → `stoles`; shawl/shawls/wrap/pashmina → `shawls`. `scarves` is a first-class category (display label "Scarves"). A page with none of those terms fails with "Cannot determine category". No data migration: existing products keep their stored category and `scarves` only adds an allowed value.
- **No inference.** Material, size, weight, origin, stock and currency come only from structured fields or explicit `Label: value` lines. A price with no stated currency stays currency-unknown; stock is always unknown until a reviewer sets it.
- **Bot protection / rate limits.** Fetches identify as `EleganceIngestion/1.0` and are spaced by `INGESTION_DOMAIN_MIN_INTERVAL_SECONDS` (default 2s). A 429 or 5xx retries with backoff, then fails.
- **No browser.** JS-rendered pages are unsupported; Crawl4AI is not used.
- **One quill-store behavior changed:** image extraction runs on raw HTML (quill-store ran it after `<img>` tags were removed).
- Source price is provenance only; PKR price and stock are entered at approval. The review card can show a reference PKR suggestion from the fawazahmed0 rate API (suggestion only, nothing stored or pre-filled). QA: with a priced item, click "Suggest from source price", check the rate/date, click "Use as starting price", and confirm approval still needs an explicit click.
- Generic status changes to inactive on a published ingested product do not update the staged record's status.
- No compose/deploy files were changed.
