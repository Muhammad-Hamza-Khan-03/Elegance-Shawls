# Phase 1 QA handoff — one-source product ingestion

**Status: implementation complete on fixtures; independent QA NOT yet performed.** Implementation tests below are not independent QA. This record must not be treated as staging evidence.

**Code under test:** branch `phase-1/one-source-ingestion`, commit `32c9520405e4926c91840386b000d5ca7bd06113` (docs-only commits may follow; re-record the SHA QA actually deploys).

## Blocking inputs (not provided yet)

| Needed for QA | Value |
|---|---|
| Authorized source domain + written authorization | **not provided** |
| Isolated staging API URL | **not provided** |
| Isolated staging frontend URL | **not provided** |
| Staging database name / staging-only admin key | **not provided** (never share the key in this file) |
| FieldExtractor for the real source | **not implemented** (see Open items) |
| Job IDs from a staging run | none — no staging run has happened |

## Implementation evidence (developer-run, local fixtures)

- Backend `pytest -q`: 157 passed (31 baseline). `python -m compileall -q .` PASS. `pip-audit -r requirements.txt`: no known vulnerabilities.
- Frontend `npm test`: 149 passed (95 baseline). `npm run lint`, `npm run typecheck`, `npm run build` PASS.
- Not run: `npm run test:e2e` (Playwright mock API has no ingestion endpoints), any Docker/compose stack, any real network fetch.

## Required environment (staging only)

```
INGESTION_SOURCE_ID=primary
INGESTION_SOURCE_NAME=<source name>
INGESTION_SOURCE_DOMAIN=<authorized host, no scheme>
INGESTION_SOURCE_AUTHORIZED=true     # operator's explicit statement of authorization
INGESTION_IMAGE_HOSTS=<cdn host, optional>
MONGODB_URI / MONGO_DB_NAME=<isolated staging database>
ADMIN_API_KEY=<staging-only key>
```

Worker: `cd apps/backend && python -m ingestion.worker` (separate process; requires a wired FieldExtractor).

## QA script

1. Confirm the target is staging: separate DB, staging-only key, no production data.
2. Unauthenticated and wrong-key calls to every `/products/admin/ingestion/*` route return 401; the browser proxy returns 401 without a session and 403 cross-origin.
3. `POST /products/admin/ingestion/jobs` with a full URL, `//host/...`, or `/products/../x` returns 422.
4. Queue a real product path. Record the job ID. Job goes queued → running → succeeded (`GET .../jobs/{id}`).
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

- **No field extractor.** quill-store obtains title, description, material, sizing, weight, origin and price with an LLM step; Phase 1 forbids LLM dependencies. `ingestion/quill_scraper.FieldExtractor` is the seam, `UnconfiguredExtractor` is the default, and every job fails with a clear non-retryable error until one is wired in.
- **Crawl4AI not used.** It follows redirects inside a browser and cannot be pinned to a validated IP. Fetching uses `SafeFetcher` (httpx). Pages that require JavaScript rendering will not work until a browser fetcher with equivalent request interception exists.
- **One quill-store behavior changed:** image extraction runs on raw HTML (quill-store ran it after `<img>` tags were removed).
- Source price is stored as provenance only; the PKR retail price and stock are entered at approval.
- Generic status changes to inactive on a published ingested product do not update the staged record's status.
- The rate limiter and job claiming are per-database/per-process as appropriate; a single worker is assumed for the per-domain fetch limiter.
- No compose/deploy file changes were made; the worker is not deployed anywhere.
