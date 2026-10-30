# Phase 1: one-source product ingestion

## Scope

Ingest products from **one explicitly authorized, configurable source** into an isolated staging area. A human approves each product, then manually publishes it. Nothing becomes public automatically.

Development uses fixtures and a throwaway PostgreSQL (Testcontainers) only. No real source is configured: `INGESTION_SOURCE_DOMAIN` is empty by default and the source record must have `authorized=true`, set deliberately by an operator.

## Excluded

Shopify Admin/private APIs and credentials, orders/customers/inventory APIs, webhooks, multiple sources, Redis or cloud queues, Kubernetes, n8n, AI assistant, CRM, WhatsApp automation, LLM/OpenAI dependencies, automatic publishing, production data or credentials, a second admin system.

## Reused from quill-store

Ported with minimal change into `apps/backend/ingestion/quill_scraper.py`: `is_likely_product_image`, `sanitize_product_html`, `extract_shopify_product_images`, `is_valid_shopify_product_url`, `normalize_shopify_product_url`, and the `ProductShawl` field set.

Not ported: CSV storage, Quill DB models, API routes, service layer, credentials, notification email, auto-upsert behavior.

**Field extraction.** In quill-store, title/description/material/sizing/weight/origin/price come from an LLM step (`extract_product_with_llm`). Phase 1 forbids LLM dependencies, so that step is the `FieldExtractor` interface, implemented deterministically by `ingestion/extractors.py::ShopifyHtmlExtractor` over static HTML: schema.org JSON-LD `Product` first, then Open Graph / `product:*` meta tags, then theme selectors, then `Label: value` spec lines in the description. It never reads stock from availability markup, never guesses a currency, and fails the job (non-retryable) when the title, description or category cannot be determined. Category policy: an explicit term (scarf, shawl, wrap, pashmina, stole) in the JSON-LD category, title or URL handle maps to the Elegance `shawls` category; no term means the job fails. Material, size, weight, origin, stock and currency are only taken from structured fields or explicit `Label: value` lines, never inferred from titles or prose. A browser runtime is not used; add one only if static HTML is shown to be insufficient.

**Fetching.** quill-store fetches through a Crawl4AI browser, which follows redirects internally and cannot be pinned to a validated IP. Phase 1 fetches through `SafeFetcher` (httpx) so every hop is validated. Crawl4AI can be added later as a second `PageFetcher` only with request interception that enforces the same rules.

## Data flow

1. Admin creates a job for a configured source (`POST /products/admin/ingestion/jobs`) with a product URL path. The browser never supplies a full URL; the path is joined to the configured source domain.
2. The worker atomically claims a queued job, fetches the page via `SafeFetcher`, sanitizes HTML, extracts images, runs the `FieldExtractor`.
3. The result is normalized to the Elegance product shape and validated.
4. A `staged_products` document is upserted by `(source_id, source_product_id)` or, without an ID, by `(source_id, canonical_url)`. A content hash detects changes.
5. A reviewer approves or rejects. Approval creates a `products` document with `status=draft`, `is_active=false`.
6. Publish sets `status=active`, `is_active=true`. This is the only path to public visibility.

## Staged product states

`pending_review -> approved | rejected`, `approved -> published | archived`, `published -> unpublished | archived`, `unpublished -> published | archived`, `rejected -> archived`. Any other transition returns 409. `needs_review` flags (missing price, missing stock, missing images) must be cleared by an admin edit before approval.

## Job states

`queued -> running -> succeeded | retrying | failed`, `retrying -> running`, `queued|retrying -> cancelled`. A running job holds a lease; an expired lease is recovered to `retrying` (or `failed` when attempts are exhausted). Retries use exponential backoff and are bounded by `max_attempts`. `failed` is terminal and records `last_error`.

## Approval rules

- Approval requires: name, at least one image, a human-entered PKR price, and acknowledged stock. Source price is provenance and is never converted or applied automatically. On the review screen the reviewer can request a reference PKR suggestion (`GET .../staged/{id}/pkr-suggestion`, rates from the free fawazahmed0 currency API, cached 6 hours). It is not stored and excludes margin, shipping, duty and tax; the reviewer still types and confirms the retail price. Ingestion and the monthly refresh never call the rate API.
- Scraped stock is unknown, so staged variants start at stock 0 and flag `needs_review`.
- Publish requires the staged product to be `approved` and the linked product to exist.

## Security rules

- Every ingestion route sits under the existing admin router (`X-Admin-Key`, constant-time compare). The frontend uses `proxyAdminRequest`.
- Source allowlist by exact host: `INGESTION_SOURCE_DOMAIN` plus any exact hosts in `INGESTION_ALLOWED_HOSTS` (for example the `www.` variant). Subdomains and look-alike hosts are rejected. HTTPS only; no userinfo; standard port only. All hosts of the source share one rate-limit bucket, and staged URLs are rewritten to the canonical `INGESTION_SOURCE_DOMAIN` so apex and `www` pages are the same product.
- DNS is resolved once, every address must be public, and the connection is pinned to the validated address. Private, loopback, link-local, multicast, reserved, and cloud metadata ranges are rejected. Redirects are followed manually (limit 3) and revalidated per hop.
- Connect/read timeouts, response-size cap, bounded retries, per-domain rate limit.
- Remote content is untrusted: HTML is parsed, never executed; text is stripped of markup and length-capped; image URLs must be https on the allowed host or its CDN allowlist.

## QA requirements

Backend and frontend suites must pass in CI. Independent QA is separate from implementation tests and runs on isolated staging with staging-only credentials. QA evidence (commit SHA, URLs, job IDs, results) is recorded in `docs/qa/phase-1-handoff.md`.

## Rollback

All Phase 1 collections are new and additive; the public `products` read path is unchanged. Roll back by redeploying the previous build. Staged data may be left in place or its collections dropped on staging. No production migration is performed.

## Open items

1. The extractor was written against standard Shopify/schema.org structures and fixtures; no real source page has been observed by the developer. Staging QA is the first real-markup check.
2. Hosts other than those configured are rejected, including on redirects.
3. Pages that need JavaScript rendering are unsupported.
