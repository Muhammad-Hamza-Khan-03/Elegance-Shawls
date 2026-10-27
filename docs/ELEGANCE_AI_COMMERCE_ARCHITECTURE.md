# Elegance AI Commerce — Architecture and Implementation Plan

> **Status:** Approved planning baseline
>
> **Primary repository:** `Elegance-Shawls`
>
> **Scope:** Product ingestion first, followed by catalogue operations, external CRM/lead management, AI shopping assistance, and workflow automation.
>
> **Planning rule:** This document defines the target direction and sequencing. Do not implement every phase at once. Each phase requires an explicit scoped task, acceptance criteria, and independent QA before the next phase starts.

## 1. Executive Decision

Elegance AI Commerce will remain one product centered on the existing `Elegance-Shawls` application. The application will own product, catalogue, ingestion, and business rules, while suitable generic services will be integrated instead of rebuilt unnecessarily.

The approved cost-efficient architecture is:

- **Main application:** Existing Next.js storefront/admin and FastAPI backend in `Elegance-Shawls`.
- **Product database:** MongoDB Atlas as the initial authoritative store for products, staged products, ingestion jobs, and integration state. Do not introduce PostgreSQL and MongoDB as dual sources of truth.
- **Ingestion:** Adapt useful `quill-store` scraper logic into an independent Python worker/runtime.
- **Admin:** Use the existing Elegance admin surface where possible; adapt scraper review patterns from `quill-panel`. Do not maintain two competing full admin applications.
- **Jobs:** MongoDB-backed durable ingestion jobs with atomic claims, leases, heartbeats, bounded retries, and idempotency.
- **Crawler:** Crawl4AI + Playwright first, with one authorized source in Phase 1.
- **Review/publishing:** Scraped data always enters staging and requires explicit review, approval, import, and publish actions before public visibility.
- **CRM and leads:** Use **HubSpot Free CRM** as the external CRM and lead source of truth once lead capture begins. Integrate through the HubSpot API rather than building a duplicate full CRM inside Elegance.
- **Lead capture:** Use the existing Elegance product/enquiry UI for product-aware leads. Use Tally only for separate landing-page or external forms where it saves work.
- **Customer messaging:** Use direct WhatsApp `wa.me` handoff first. Add Meta WhatsApp Cloud API later for official automation. Use Twilio only if voice, SMS, or a specific provider abstraction is required.
- **Email:** Use Brevo for transactional and optional marketing email. Do not duplicate the entire CRM contact database into multiple systems without a defined sync purpose.
- **Automation:** Use the application and Python worker for business-critical state transitions. Add self-hosted n8n later for external integrations and notifications, not as the primary business backend.
- **Analytics/monitoring:** Use PostHog for product analytics and Sentry for error/performance monitoring, subject to current free-tier limits.
- **Media:** Keep validated source URLs initially. Add Cloudflare R2 only when image ownership, caching, or artifact storage requires it.
- **Cost posture:** Prefer free tiers and self-hosted/open-source components where they are reliable and operationally manageable. Verify current quotas, commercial-use terms, billing triggers, and data-retention policies before activation.

This is production-oriented without pretending that free-tier hosting provides enterprise availability. The design prioritizes safe failure, recoverability, auditability, portability, and one clear owner for every data domain.

## 2. Product Vision

Elegance AI Commerce supports the complete retail journey:

```text
Authorized product sourcing
        -> validation and staging
        -> admin review and approval
        -> catalogue import and publishing
        -> customer discovery
        -> WhatsApp enquiry or AI assistance
        -> lead capture in HubSpot
        -> sales follow-up and CRM pipeline
        -> approved external automation
        -> conversion analytics
```

The platform is not only a scraper and not only a storefront. It is an operational retail system. However, implementation must progress in small slices, beginning with reliable product ingestion and the existing production-readiness blockers.

The final platform should be presentable as several portfolio case studies without becoming several disconnected products:

1. AI product ingestion and ETL.
2. Full-stack AI commerce SaaS.
3. AI-powered ecommerce assistant.
4. AI lead qualification and CRM integration.
5. Business automation and external-system integration.

Voice, document processing, appointment booking, and multi-agent research are separate future projects unless a real business requirement appears.

## 3. Delivery Order and Governance

Existing P0 production-readiness work comes before new AI Commerce implementation.

```text
P0 production blockers
        -> stable release baseline
        -> Phase 0 contracts and hardening
        -> Phase 1 product ingestion
        -> Phase 2 catalogue operations
        -> Phase 3 lead capture and HubSpot integration
        -> Phase 4 AI shopping assistant
        -> Phase 5 CRM qualification and n8n automation
        -> Phase 6 scale and specialized integrations
```

Do not start AI, CRM automation, or scraper architecture changes on top of unresolved security, authentication, data-integrity, database, deployment, or independent-QA blockers.

### Current prerequisite categories

Prioritize existing P0 board work covering:

- Dependency and security remediation.
- Admin authentication and authorization.
- Product stock and price correctness.
- Checkout/WhatsApp handoff revalidation.
- Private/authenticated production MongoDB.
- Backup and isolated restore.
- HTTPS deployment and readiness.
- Monitoring and rollback.
- Live admin/storefront QA.
- Real WhatsApp customer QA.
- Final CI and release certification.
- Business contact and policy approval.

Do not wait for every lower-priority feature issue to close. After the P0 release foundation is stable, create a clearly scoped Phase 0/Phase 1 task contract.

## 4. Repository Responsibilities

### 4.1 `Elegance-Shawls` — primary system

Owns the business application and authoritative business rules:

- Customer storefront.
- FastAPI API.
- Product catalogue and variants.
- Publication status.
- Inventory/status rules.
- Admin authentication and authorization.
- Staged-product review endpoints.
- Product-aware enquiry creation.
- Ingestion job contracts.
- HubSpot/Brevo integration adapters and sync state.
- AI tool boundary.
- Audit events and provenance.
- API contracts and environment configuration.
- MongoDB indexes and persistence rules.

The API, not the browser, crawler, AI model, n8n workflow, or CRM UI, is authoritative for Elegance product and publication state.

### 4.2 `quill-store` — source/reference for ingestion

Reuse and adapt useful logic for:

- Source configuration.
- Crawl4AI browser execution.
- Shopify URL discovery.
- Product-page extraction.
- Image URL extraction.
- Normalization.
- Validation.
- Deduplication candidates.
- Retry and timeout behavior.
- Staged-product writes through the approved Elegance ingestion boundary.

It must not:

- Publish products directly.
- Bypass admin approval.
- Own the public storefront.
- Expose an unauthenticated crawler endpoint.
- Own the canonical commerce product model.
- Become a second product database.

The original repository should remain intact as a reference unless a separately approved maintenance task is requested.

### 4.3 `quill-panel` — UI reference, not a second commerce system

Reuse useful patterns for:

- Start/import controls.
- Job status.
- Staged-product tables.
- Review, approve, reject, and edit actions.
- Pagination and error display.

Prefer adapting this experience into the existing Elegance admin. If a separate panel remains temporarily deployed, it must call the Elegance API and must not connect directly to MongoDB or contain a duplicate product business model.

### 4.4 External services — integrated capabilities

External services may own generic capabilities, but each integration must have a documented purpose and source-of-truth boundary:

- **HubSpot:** contacts, leads, deals, pipeline, CRM activities, and follow-up tasks.
- **Brevo:** transactional email and optional email marketing delivery.
- **Meta WhatsApp Cloud API:** later official WhatsApp messaging and webhooks.
- **Twilio:** optional later SMS/voice/WhatsApp provider; not required for initial handoff.
- **n8n:** later external workflow orchestration and notifications.
- **Tally:** optional landing-page/external form capture.
- **PostHog:** product analytics events.
- **Sentry:** error and performance monitoring.
- **Cloudflare R2:** optional owned media and artifact storage.

No external service may silently create a second source of truth for products, publication state, or ingestion jobs.

## 5. Target Architecture

```text
                              Customers
                                  |
                                  v
                         Next.js storefront
                         (Elegance-Shawls)
                                  |
                                  v
                         FastAPI business API
              +-------------------+--------------------+
              |                   |                    |
              v                   v                    v
        Catalogue           Ingestion API        Enquiry/AI API
        and products        and review            and lead request
              |                   |                    |
              +-------------------+--------------------+
                                  |
                                  v
                            MongoDB Atlas
       +-------------+----------+----------+-----------+-------------+
       |             |          |          |           |             |
       v             v          v          v           v             v
   products   staged_products jobs   integration  audit_events  ai metadata
                                      _sync
                                  ^
                                  |
                         Independent Python worker
                         (adapted quill-store logic)
                                  |
                          Crawl4AI + Playwright
                                  |
                         Authorized supplier website

FastAPI integrations:
    -> HubSpot CRM API       contacts, deals, activities, tasks
    -> Brevo API             transactional/marketing email
    -> WhatsApp link/API     customer handoff or approved messaging
    -> LLM provider          validated AI tools only
    -> PostHog               product analytics events
    -> Sentry                errors/performance

Optional external automation:
    FastAPI events -> n8n -> Discord/email/sheets/calendar/other integrations
```

### Runtime boundaries

- The public API must not wait for browser crawling to finish.
- The worker is a separate process/runtime even if it initially runs on the same host.
- The worker may use the Elegance ingestion API or a tightly controlled staging writer. The API boundary is preferred as the system matures.
- The browser never connects directly to MongoDB.
- The browser never receives HubSpot, Brevo, MongoDB, or other integration secrets.
- AI tools never receive unrestricted database access.
- n8n never becomes the only place where critical product or lead state exists.
- External provider failures must not silently publish products or lose a lead.

## 6. Data Ownership and Integration Boundaries

| Data domain | Authoritative owner | Local data retained |
|---|---|---|
| Published products | Elegance API + MongoDB `products` | Full product record |
| Product review state | Elegance API + `staged_products` | Full staged record and provenance |
| Crawl job state | MongoDB `ingestion_jobs`/`ingestion_items` | Full job state |
| Source configuration | Elegance configuration + MongoDB | Source policy/configuration |
| CRM contacts | HubSpot CRM | HubSpot IDs, sync status, minimal correlation data |
| CRM deals/pipeline | HubSpot CRM | Deal IDs, related enquiry IDs, sync status |
| CRM activities/tasks | HubSpot CRM | Provider IDs and delivery/error state |
| Product enquiries | Elegance API first, then synced to HubSpot | Product/variant snapshot, consent, idempotency, sync status |
| Transactional email delivery | Brevo | Template/event ID, provider message ID, status/error |
| WhatsApp handoff | Customer WhatsApp session; enquiry record in Elegance/HubSpot | Generated message/reference and consent |
| AI conversation | Elegance AI service | Minimal conversation metadata and audit record; no unnecessary PII |
| Product analytics | PostHog | Event correlation ID only where necessary |
| Errors/performance | Sentry | Redacted event reference |
| Media/artifacts | Source URL initially; R2 later if adopted | Object key and provenance |
| Audit history | Elegance API + MongoDB audit collections | Full business audit record |

### Lead ownership decision

HubSpot is the canonical CRM system for contacts, deals, pipeline, and follow-up work after the HubSpot integration is enabled.

Elegance remains authoritative for:

- Whether an enquiry was created.
- Which product/variant/price snapshot the customer selected.
- Consent captured at the app boundary.
- Idempotency and provider-sync state.
- Product availability and catalogue truth.

This is not an uncontrolled duplicate CRM. The local record is an integration/outbox record that preserves the business event and allows safe retries when HubSpot is unavailable.

## 7. MongoDB Collections and Core Records

Initial logical collections:

```text
products
staged_products
ingestion_sources
ingestion_jobs
ingestion_items
ingestion_events
enquiries
lead_sync_events
integration_sync_state
audit_events
ai_conversation_metadata
```

A full local CRM collection is not required when HubSpot is the selected CRM. If a small local `leads` collection is retained for reliable intake, it must be explicitly treated as an enquiry/outbox record, not a competing CRM pipeline.

### 7.1 Published product rules

The canonical product record should preserve the existing Elegance schema and explicitly represent:

- Stable internal product ID.
- Name/title and slug.
- Description.
- Category/type.
- Variants.
- Color/material/sizing/weight where supported.
- Price and explicit currency.
- Images/media references.
- Availability/status.
- Source/provenance reference where appropriate.
- Created/updated timestamps.

Do not silently invent material, origin, weight, price, or availability when source data is missing. Missing values should remain visible for review or use an explicitly labelled business default approved by the owner.

### 7.2 Staged product rules

Every staged product should retain:

- `source_id`.
- `source_product_id` when available.
- Canonical `source_url`.
- Source domain.
- Crawl timestamp.
- Extracted/raw values required for review.
- Normalized values.
- Content hash where useful.
- Validation errors/warnings.
- Deduplication key.
- Review status.
- Reviewer and decision timestamp.
- `catalog_product_id` after import.
- Import/publish timestamps.

### 7.3 Enquiry and integration records

A product enquiry should preserve:

```text
enquiry_id
product_id
variant_id
quantity
price_snapshot
currency
customer_name_or_redacted_reference
customer_contact_reference
consent
source_page
whatsapp_reference
idempotency_key
hubspot_contact_id
hubspot_deal_id
sync_status
last_sync_error
created_at
updated_at
```

Do not store unnecessary customer PII. Keep provider secrets and access tokens outside MongoDB in the approved secret store/environment.

### 7.4 Stable identity and deduplication

Preferred product identity:

```text
source_id + source_product_id
```

Fallback identity:

```text
source_id + canonical_source_url
```

A content hash can detect changed records but must not replace a stable source identity. Use unique indexes and idempotent upserts. Re-running a job must not create duplicate catalogue products.

For leads/enquiries, use an application-generated idempotency key so browser retries, webhook retries, and n8n retries do not create duplicate HubSpot contacts or deals.

## 8. Source Configuration and Multi-Source Foundation

Phase 1 implements one authorized source, but the core contract should be source-configured rather than hardcoded to one domain.

Example configuration:

```json
{
  "source_id": "supplier_001",
  "name": "Authorized Supplier",
  "domain": "supplier.example",
  "provider": "crawl4ai",
  "parser": "shopify",
  "enabled": true,
  "authorized": true,
  "max_concurrency": 1,
  "crawl_interval_hours": 24
}
```

Required source controls:

- Explicit domain/path allowlist.
- `authorized` flag and owner approval.
- Per-domain rate/concurrency limit.
- Pagination and timeout limits.
- Parser/provider selection.
- Crawl schedule when scheduling is introduced.
- Terms/compliance notes.
- Source identity rules.

Do not implement multiple full connectors in Phase 1. Implement the adapter boundary and one real connector.

## 9. Ingestion Pipeline

```text
Create import job
        |
        v
Worker claims job
        |
        v
Fetch authorized source
        |
        v
Extract structured data / HTML
        |
        v
Normalize product fields
        |
        v
Validate required fields and URLs
        |
        v
Generate stable source identity
        |
        v
Detect new/changed/unchanged/failed item
        |
        v
Upsert staged product
        |
        v
Admin review
   +----+-----+
   |          |
 Reject     Approve
              |
              v
       Validated catalogue draft
              |
              v
       Explicit import action
              |
              v
       Explicit publish action
```

Preferred extraction order:

1. Official API, feed, or structured source data where authorized.
2. Static/structured HTML parsing.
3. Crawl4AI/browser rendering only when required.
4. Optional AI enrichment for missing or draft fields.

AI must not be a mandatory dependency for basic ingestion success.

### 9.1 Product quality control pipeline

Product quality control is part of the ingestion foundation, not a later cosmetic AI feature. Every staged item should receive deterministic validation before it can be approved.

The first quality checks must use normal application code because it is cheaper, faster, predictable, and straightforward to test:

- Missing title, description, category, or required variant fields.
- Missing or invalid image URLs.
- Invalid price, currency, stock, or availability values.
- Broken product URLs or disallowed source domains.
- Duplicate source identity or likely duplicate content.
- Unsupported material, origin, or other ungrounded fallback values.
- Invalid variant combinations and malformed payloads.

Suggested quality states:

```text
CHECK_PENDING
  -> READY_FOR_REVIEW
  -> REVIEW_REQUIRED
  -> BLOCKED
  -> APPROVED
```

The admin review surface should show the failed rule, severity, source value, normalized value, and recommended next action. A corrected item must be revalidated before approval.

AI may assist only where it adds value:

- Suggest a missing description.
- Flag a possible category mismatch.
- Explain a possible duplicate.
- Propose translation or standardized copy.

AI suggestions remain drafts. AI must not replace deterministic validation or silently change a product.

## 10. MongoDB-Backed Job System

A dedicated queue is not required initially. Use durable MongoDB job records and a separate worker.

### Job lifecycle

```text
PENDING
   |
   v
CLAIMED
   |
   v
RUNNING
   +------> COMPLETED
   +------> RETRY_SCHEDULED --> PENDING
   +------> FAILED
```

Job fields:

```text
job_id
job_type
source_id
status
payload
idempotency_key
attempt_count
max_attempts
worker_id
lease_expires_at
heartbeat_at
next_run_at
last_error
created_at
started_at
completed_at
```

### Worker rules

1. Claim a pending job with an atomic `findOneAndUpdate` operation.
2. Set `worker_id`, lease, attempt count, and status in the same claim.
3. Refresh `heartbeat_at` while the job is active.
4. Treat an expired lease as recoverable only after a bounded recovery check.
5. Retry transient failures with exponential backoff.
6. Stop after `max_attempts` and mark the job `FAILED`.
7. Make every product write idempotent so duplicate delivery or worker restart is safe.
8. Use an indexed query on status and next-run time.
9. Back off polling when no job is available; do not hot-poll a free MongoDB cluster.
10. Preserve per-item errors so one bad product does not fail the entire run.

Redis, Celery, Cloudflare Queues, and other queue infrastructure are deferred until measured workload requires them.

## 11. Product Review and Publication

Product states:

```text
discovered
  -> normalized
  -> needs_review
  -> approved
  -> imported
  -> published
```

Alternative terminal states:

```text
rejected
archived
import_failed
unpublished
```

Keep these operations distinct:

- **Import:** create/update a validated catalogue draft.
- **Approve:** reviewer confirms the data is acceptable.
- **Publish:** explicit action makes it visible to customers.

The next crawl must not silently overwrite manual edits. Track imported values separately from approved/manual values or surface a field-level conflict for review.

## 12. API Contract Direction

The exact routes must follow existing Elegance API conventions, but intended capabilities are:

```text
POST  /admin/ingestion/jobs
GET   /admin/ingestion/jobs/{job_id}
POST  /admin/ingestion/jobs/{job_id}/retry
GET   /admin/ingestion/products
GET   /admin/ingestion/products/{id}
POST  /admin/ingestion/products/{id}/approve
POST  /admin/ingestion/products/{id}/reject
PATCH /admin/ingestion/products/{id}
POST  /admin/ingestion/products/{id}/import
POST  /admin/products/{id}/publish
POST  /admin/products/{id}/unpublish

POST  /enquiries
POST  /integrations/hubspot/webhooks
POST  /integrations/brevo/webhooks
POST  /integrations/whatsapp/webhooks
POST  /ai/chat
```

Requirements:

- All mutations authenticated and authorized server-side.
- Idempotency keys on job creation, enquiry creation, and sensitive imports.
- Stable error response shape.
- Pagination for jobs, staged products, and local integration events.
- No secrets in response bodies or logs.
- Public catalogue routes only return published products.
- Provider calls use server-side credentials only.
- Integration failures are visible and retryable.

## 13. External Service Integration Plan

### 13.1 HubSpot Free CRM

HubSpot is the selected external CRM for the initial integrated CRM phase.

Use it for:

- Contact records.
- Deal records.
- Pipeline stages.
- Tasks and follow-ups.
- Notes and activity history.
- Sales ownership.
- CRM reporting available on the selected tier.

Integration pattern:

```text
Elegance enquiry
        |
        v
FastAPI validates product/price/stock/consent
        |
        v
Create or update HubSpot contact
        |
        v
Create or update HubSpot deal
        |
        v
Write provider IDs and sync result locally
```

Rules:

- Never expose HubSpot tokens in browser code.
- Use a server-side integration adapter.
- Use idempotency and provider-ID correlation.
- Handle rate limits and temporary provider failures with bounded retries.
- Do not create a second full local CRM pipeline.
- Exportability must be checked before depending on provider-specific features.
- Verify current free-tier record, seat, automation, API, and retention limits before launch.

Official references:

- [HubSpot Free CRM](https://www.hubspot.com/products/crm)
- [HubSpot Developer Documentation](https://developers.hubspot.com/docs)

### 13.2 Tally forms

Tally is optional for:

- Portfolio landing pages.
- Supplier authorization requests.
- General contact forms outside the storefront.
- Campaign-specific lead forms.

Use a webhook into FastAPI or n8n, then create/update the HubSpot record. Do not make Tally the source of truth for product-aware storefront enquiries.

Official reference: [Tally](https://tally.so/)

### 13.3 Brevo

Brevo is the selected email integration for:

- Transactional enquiry confirmation.
- Admin alerts.
- Scraper/job failure notifications.
- Follow-up email where consent exists.
- Optional email marketing later.

Rules:

- Keep CRM ownership in HubSpot.
- Do not automatically mirror every HubSpot contact into Brevo unless an email purpose and consent exist.
- Store provider message IDs and delivery status where needed.
- Keep unsubscribe and consent state clear.
- Verify current free-tier daily/monthly sending limits before enabling campaigns.

Official reference: [Brevo API](https://developers.brevo.com/)

### 13.4 WhatsApp

Initial customer handoff:

```text
Current product/variant/price/stock validation
        -> enquiry record
        -> generated message/reference
        -> direct wa.me link
```

This does not require Twilio.

Later official messaging options:

- **Meta WhatsApp Cloud API:** preferred direct provider when official automated WhatsApp messaging is needed.
- **Twilio WhatsApp API:** optional abstraction when Twilio SMS/Voice or existing Twilio operations justify it.

Automated messaging must require:

- Customer consent.
- Approved message templates where applicable.
- Delivery/error tracking.
- Human escalation path.
- No claims that a WhatsApp handoff is a confirmed order.

Official reference: [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)

### 13.5 n8n

Use self-hosted n8n Community Edition later for external integration workflows:

```text
New HubSpot lead
        -> n8n
        -> Discord/email notification
        -> optional sheet/calendar/task action
```

```text
Scraper completed
        -> n8n
        -> admin notification
```

n8n must not own critical product or lead state. FastAPI and HubSpot remain responsible for authoritative business state.

Deployment options:

- Self-hosted Docker deployment on a suitable Oracle VM or other portable host.
- Managed n8n only if maintenance cost is worth the convenience.
- Make may be used instead for low-volume workflows when self-hosting is not worthwhile.

Do not run n8n, Redis, high-concurrency Chromium, and a full crawler stack on a low-memory VM without resource validation.

Official references:

- [n8n pricing and Community Edition](https://n8n.io/pricing/)
- [Make pricing](https://www.make.com/pricing)

### 13.6 PostHog

Use PostHog for product analytics:

- Product views.
- Search and filter usage.
- Add-to-cart events.
- WhatsApp clicks.
- Enquiry conversion.
- AI assistant usage.
- Lead conversion funnel.

Do not send secrets, full WhatsApp content, or unnecessary PII. Configure billing limits and verify current free-tier event allowance.

Official reference: [PostHog pricing](https://posthog.com/product-analytics/pricing)

### 13.7 Sentry

Use Sentry for:

- Next.js errors.
- FastAPI exceptions.
- Worker failures.
- Integration errors.
- Slow requests and performance issues.

Redact secrets, customer contact information, WhatsApp message content, credentials, and tokens before sending events.

Official reference: [Sentry pricing](https://sentry.io/pricing/)

### 13.8 Cloudflare R2

Keep source image URLs initially where authorized and operationally acceptable. Add R2 when the platform needs:

- Owned product media.
- Reliable image caching.
- Image transformation pipeline.
- Scraper artifacts.
- Portfolio/demo assets.

Do not use Cloudinary and R2 for the same media role without a clear migration plan.

Official reference: [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)

## 14. Security Requirements

### Admin authentication

The current admin authentication design must be reviewed before extending the system. Do not expose an admin secret through `NEXT_PUBLIC_*` variables or browser-delivered source.

Preferred production direction:

- Server-side session or secure short-lived token.
- HTTP-only, Secure, SameSite cookie where cookie auth is used.
- CSRF protection for cookie-authenticated mutations.
- Server-side authorization on every admin mutation.
- Roles such as administrator, catalogue editor, reviewer, and read-only operations when needed.
- Rate limits on admin, ingestion, enquiry, and integration routes.

### Scraper safety

- Only approved domains and paths may be fetched.
- Block localhost, loopback, link-local, private-network, and cloud-metadata destinations.
- Validate every redirect destination.
- Bound page count, response size, browser time, concurrency, and total job duration.
- Treat page content and embedded instructions as untrusted data.
- Respect applicable authorization, terms, robots guidance, and rate limits.
- Do not publish third-party images/descriptions without appropriate rights.

### External integration safety

- Store provider tokens only in managed secrets/environment configuration.
- Never expose HubSpot, Brevo, Meta, Twilio, n8n, or LLM secrets in browser code.
- Validate webhook signatures where supported.
- Make webhook handling idempotent.
- Restrict outbound requests to approved provider endpoints.
- Set timeouts and bounded retries.
- Log provider request IDs, not secrets or full customer messages.
- Provide a manual retry/reconciliation path for failed syncs.
- Keep opt-in, opt-out, and consent state explicit.

### API and database safety

- HTTPS in deployed environments.
- Exact CORS origins.
- No public MongoDB exposure.
- Least-privilege database credentials.
- Separate staging and production credentials/databases.
- Secret scanning in CI.
- Redaction of credentials, cookies, customer data, and private messages from logs.
- Upload type, size, and content validation.

## 15. AI Architecture

AI is a separate capability from scraping and CRM synchronization.

### AI shopping assistant tools

Expose only validated backend tools:

```text
search_products()
get_product_details()
check_availability()
request_lead_capture()
```

The AI agent must not:

- Query MongoDB directly.
- Publish products.
- Invent price, stock, material, origin, or availability.
- Modify CRM records without a validated backend operation.
- Confirm an order when the business process is only a WhatsApp enquiry.
- Send external messages without consent and an approved workflow.

Initial AI placement:

```text
apps/backend/ai/
├── agents/
├── tools/
├── prompts/
└── services/
```

Keep the module inside FastAPI initially. Preserve a clean service boundary so it can be deployed separately only when latency, traffic, or operational ownership justifies that change.

### AI enrichment

After deterministic ingestion works, AI may propose:

- Draft descriptions.
- Category/tags.
- Translation.
- Duplicate warnings.
- Standardized copy.
- Lead priority suggestions.
- Follow-up message drafts.

Every AI result remains draft content until an operator approves it.

### Controlled MCP business connector — future Phase 5/6

An MCP server may later expose a small set of approved business tools to an admin AI assistant. MCP is an integration boundary, not a reason to expose MongoDB directly.

```text
Admin AI
   -> MCP server
   -> authenticated FastAPI business tool
   -> authorization and validation
   -> MongoDB/provider action
   -> audit event
```

Start with read-only tools:

```text
list_failed_imports()
find_missing_images()
find_duplicate_candidates()
get_import_job_summary()
```

Only later add approval-required proposal/mutation tools:

```text
propose_product_correction()
propose_description_update()
approve_staged_product()
retry_failed_job()
```

Every mutation must follow:

```text
AI suggestion
    -> human review
    -> explicit approval
    -> backend validation
    -> state change
    -> audit log
```

MCP requirements:

- No direct database credentials or unrestricted queries.
- Server-side authentication and per-tool authorization.
- Read-only default and least-privilege scopes.
- Idempotency for retryable actions.
- Clear confirmation for every mutation.
- Provider and database errors returned safely.
- Full actor, tool, target, before/after, and timestamp audit data.
- Separate admin/demo MCP credentials and environments.

## 16. Lead Capture, CRM, and Messaging Roadmap

### Phase 3 lead capture

Use the existing Elegance product-aware form and FastAPI API. Capture:

- Product and variant.
- Quantity.
- Quoted price and currency.
- Customer contact details where consented.
- Generated WhatsApp message/reference.
- Source page/session context.
- Lead state.
- Idempotency key.

Initial flow:

```text
Customer enquiry
        -> FastAPI validates current catalogue state
        -> enquiry record created
        -> HubSpot contact/deal sync
        -> direct WhatsApp handoff
```

Suggested local enquiry states:

```text
initiated -> synced -> contacted -> converted
                         -> cancelled
                         -> expired
                         -> sync_failed
```

### Phase 5 CRM qualification

Use HubSpot rather than custom-building the entire CRM:

- Pipeline stages.
- Assignment.
- Contact activity.
- Follow-up tasks.
- Deal notes.
- Lead qualification fields.
- Human-reviewed AI qualification suggestions.
- Lead-to-order conversion reference.

Elegance should provide only the product-aware intake and integration controls needed by the application. HubSpot should provide the generic CRM workspace.

### Automated follow-up

Start with human-reviewed drafts. Later, n8n or approved provider workflows may:

- Notify the sales owner.
- Create a follow-up task.
- Send an approved email.
- Send an approved WhatsApp template.
- Record delivery status.

No autonomous customer messaging should be enabled without explicit consent, provider compliance, and a rollback/disable path.

## 17. Environment and Hosting Strategy

Initial services:

- Next.js frontend on the existing managed frontend host, such as Vercel where appropriate.
- FastAPI API on the existing backend host, such as Render where appropriate.
- MongoDB Atlas as the initial database.
- Independent Python worker on a portable runtime; Oracle Free VM is optional, not a hard dependency.
- n8n only after its integration use case is approved and the host has sufficient resources.
- Brevo, HubSpot, PostHog, and Sentry credentials stored server-side.
- Direct WhatsApp link before Meta/Twilio activation.
- Object storage only when image ownership or large artifacts require it.
- GitHub Actions for CI and bounded scheduled triggers.

### Oracle VM guidance

If the Oracle VM is used:

- Start worker concurrency at 1.
- Add hard timeouts and memory limits.
- Do not run n8n, Redis, full Firecrawl, and high-concurrency Chromium together without measured resource validation.
- Keep worker and n8n containers portable.
- Monitor CPU, memory, disk, network, and restarts.
- Keep the MongoDB database private and do not use the VM as an unprotected public data store.

### Budget posture

Target **$0–$20/month initially**, subject to provider free-tier limits, commercial-use restrictions, taxes, quotas, and usage patterns.

Before enabling a paid-capable service:

1. Confirm the actual current free-tier allowance from official documentation.
2. Check whether a card is required.
3. Configure usage/billing limits where available.
4. Identify data-retention and export behavior.
5. Define the upgrade trigger.
6. Obtain approval before paid usage, production rollout, or provider migration.

Do not claim guaranteed production availability from free tiers.

## 18. Portfolio Demo Separation

Production and public portfolio demo environments must be separate.

### Production

- Real catalogue and business data.
- Protected admin.
- Real credentials.
- No public admin access.
- Real outbound integrations only with consent and approval.
- Separate HubSpot/WhatsApp/email credentials from demo.

### Portfolio demo

- Synthetic products and customers.
- Demo ingestion jobs.
- Resettable or read-only data.
- Safe AI conversations.
- No production credentials.
- No real outgoing WhatsApp messages.
- No real supplier crawling unless explicitly authorized.
- Clearly labelled `Portfolio Demo — Synthetic Data`.

Never expose production admin credentials, CRM tokens, webhook secrets, or customer data to recruiters or public visitors.

## 19. Phased Implementation Roadmap

### Phase 0 — Contracts and hardening

Deliver:

- Canonical product and staged-product schemas.
- Source authorization policy.
- Currency and image policy.
- Approval states.
- Duplicate identity rules.
- Authentication/authorization review.
- Required MongoDB indexes.
- Backup/export and recovery procedure.
- Environment separation plan.
- Integration boundary design for HubSpot, Brevo, WhatsApp, and monitoring.
- Provider secret and webhook-signature strategy.

Exit gate: data contracts, source-of-truth decisions, security boundaries, and provider integration boundaries are documented and accepted before code changes begin.

### Phase 1 — Reliable product ingestion

Build only:

- One authorized source.
- One Crawl4AI connector.
- Source configuration boundary.
- MongoDB-backed jobs.
- Separate worker.
- Validation and normalization.
- Deterministic product quality checks.
- Quality status, rule failures, and revalidation path.
- Stable identity/deduplication.
- Staged products.
- Per-item errors.
- Review UI.
- Approve/reject/edit.
- Explicit catalogue import and publish.
- Retry, lease recovery, and health status.

Do not add HubSpot CRM, n8n, Twilio, or the AI shopping assistant to Phase 1 unless a narrowly scoped integration test is required by the contract.

Exit gate: rerunning the same source produces no duplicate products; failed items are visible and retryable; only approved products can appear publicly.

### Phase 2 — Catalogue operations

Add:

- Public catalogue/search/filter improvements.
- Product detail and variant management.
- Publish/unpublish/archive.
- Manual correction protection.
- Image handling and basic SEO.
- PostHog product events where useful.

Exit gate: a reviewed product can be safely published, updated, unpublished, and archived without exposing drafts.

### Phase 3 — Lead capture and HubSpot integration

Add:

- Product enquiry flow.
- Current product/price/stock validation.
- Idempotent enquiry record.
- Direct WhatsApp handoff/reference.
- HubSpot contact creation/update.
- HubSpot deal creation/update.
- Provider IDs and sync status.
- Basic error/retry/reconciliation view.
- Sentry coverage for failed integration calls.

Exit gate: one customer enquiry creates one traceable local business event and one correctly correlated HubSpot contact/deal, with safe retry behavior.

### Phase 4 — AI shopping assistant MVP

Add:

- Catalogue search tool.
- Product detail tool.
- Availability tool.
- Conversational recommendations.
- Consent-based lead capture.
- Human fallback.
- Optional AI draft response to HubSpot lead.
- Tests for hallucinated/nonexistent/out-of-stock products and invalid lead data.

Exit gate: assistant recommends only real published products and cannot create unauthorized business mutations.

### Phase 5 — CRM qualification and external automation

Use HubSpot capabilities first. Add n8n only for external workflows that save meaningful time:

- Lead assignment notification.
- Follow-up task creation.
- Discord/email alerts.
- Brevo email delivery.
- Calendar or sheet integration if justified.
- AI qualification suggestions for human review.
- Approved follow-up drafts.
- Read-only MCP admin tools, followed by approval-gated proposal tools only after the underlying workflows are stable.

Add Meta WhatsApp Cloud API or Twilio only if automated messaging, SMS, voice, or provider webhooks are genuinely required.

Exit gate: every automated workflow has an owner, consent boundary, failure path, audit record, and disable mechanism.

### Phase 6 — Scale and specialized infrastructure

Introduce only with evidence:

- Redis or Cloudflare Queues.
- Multiple worker replicas.
- Firecrawl adapter.
- Multi-source schedules.
- R2/object storage.
- Advanced observability.
- Vector search.
- n8n at larger workflow volume.
- Twilio Voice for a separate voice project.
- PostgreSQL migration if transactional requirements justify it.

## 20. Phase 1 Acceptance Criteria

### Ingestion

- One approved source can be crawled successfully.
- The public API does not wait for the crawl to finish.
- A unique job record exists for every run.
- Jobs support atomic claim, heartbeat, lease expiry, bounded retry, and terminal failure.
- A malformed page does not terminate the entire run.
- A rerun is idempotent.
- Source URL and provenance are retained.

### Data quality

- Required fields are validated.
- Currency is explicit and consistent.
- Image URLs are validated.
- Missing fields are visible to reviewers.
- No unsupported default facts are silently invented.
- New/changed/unchanged/failed item status is visible where practical.

### Review and publishing

- Admin can list, inspect, edit, approve, reject, and archive staged records.
- Import and publish are separate actions.
- Only approved/published records appear in the public catalogue.
- Manual edits are not silently overwritten by a later crawl.
- Every approval/import decision has actor and timestamp information.

### Security and operations

- No secrets are committed or exposed through public frontend variables.
- Admin mutations are authorized server-side.
- Source allowlist and SSRF protections are active.
- Health/readiness checks work.
- Structured logs include job/request IDs without leaking sensitive data.
- A database export and recovery procedure are documented.
- At least one automated test covers normalization and deduplication.
- A representative fixture can reproduce an import locally.

## 21. Phase 3 Integration Acceptance Criteria

- Product enquiries validate against the current published catalogue.
- Stale price, removed variant, unpublished product, and unavailable stock are rejected or clearly surfaced.
- Duplicate browser submissions do not create duplicate enquiries.
- A HubSpot contact is created or updated idempotently.
- A HubSpot deal is associated with the correct contact and product/enquiry context.
- Provider IDs are stored without storing provider secrets.
- HubSpot rate limits and temporary failures are handled with bounded retries.
- Failed syncs are visible and manually retryable.
- Direct WhatsApp handoff clearly represents an enquiry/order intent, not a confirmed order.
- Consent state is captured before follow-up messaging.
- Independent QA verifies the real integration on a staging account before production activation.

## 22. Production Gates

Do not call the ingestion or integration system production-ready until:

- Staging and production data/credentials are isolated.
- Admin authentication and authorization are independently verified.
- Worker restart and lease recovery are tested.
- Duplicate rerun behavior is tested.
- A failed item and failed job can be retried safely.
- Public routes exclude staged/draft/rejected products.
- Backups/exports exist and a restore test has succeeded.
- Logs and alerts identify API, worker, and provider failures.
- Source authorization and content-rights assumptions are documented.
- Frontend-to-backend staging acceptance passes.
- HubSpot/Brevo/WhatsApp integration secrets are not browser-accessible.
- Webhook authenticity and idempotency are verified where webhooks are enabled.
- Consent and opt-out behavior is verified.
- Owner approval is recorded for production publication, paid provider activation, and external messaging.

## 23. Migration Trigger for PostgreSQL

MongoDB remains the initial database. PostgreSQL is a future decision, not a parallel database.

Re-evaluate migration when the application requires one or more of:

- Payment-backed checkout.
- Concurrent inventory reservation.
- Multiple warehouses.
- Complex order/item relationships.
- Strong transactional workflows that MongoDB cannot safely support in the existing model.
- Advanced reporting that is difficult to maintain safely.
- MongoDB model limitations causing repeated business logic defects.

HubSpot remains the CRM provider unless a measured CRM requirement, export limitation, cost change, or compliance need justifies migration to another CRM. Do not build PostgreSQL merely to replace HubSpot or to create a second CRM source of truth.

## 24. Major Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Source blocks or changes markup | Authorized sources, isolated adapters, rate limits, fixtures, change detection |
| Duplicate imports | Stable source identity, unique indexes, idempotent upserts |
| Worker crash | Leases, heartbeats, retries, expired-lease recovery |
| Wrong product data | Staging, validation, provenance, human approval |
| Manual edits overwritten | Separate imported/manual values or field-level conflict review |
| AI hallucination | Tool restrictions, draft-only outputs, approval gate |
| CRM duplicate records | Idempotency keys, provider IDs, one HubSpot source of truth |
| CRM provider outage | Local enquiry/outbox record, visible sync failure, bounded retry, reconciliation |
| Email/WhatsApp misuse | Consent, templates, human approval, provider status, disable switch |
| n8n workflow failure | Critical state stays in FastAPI/HubSpot; n8n actions are retryable and observable |
| Database outage | Exports, backup policy, restore drill |
| Credential leakage | Managed secrets, redaction, rotation, secret scanning |
| Admin endpoint exposure | Server-side auth, roles, rate limits, exact CORS |
| Free-tier instability | Portable worker, provider health checks, usage limits, documented upgrade triggers |
| Unexpected provider cost | Billing caps, usage monitoring, no paid activation without approval |
| Public demo contaminates production | Separate environment, synthetic data, no production credentials |

## 25. What Not to Build Yet

Do not add these to Phase 1 without a specific approved task and measured justification:

- Custom full CRM or duplicate local CRM pipeline.
- Kubernetes.
- Service mesh.
- Multiple databases.
- Redis/Celery/Cloudflare Queue.
- Full Firecrawl self-hosting.
- Qdrant or vector search.
- n8n as the business backend.
- Make and n8n together for the same workflows.
- MCP mutation tools before read-only tools, authorization, human approval, and audit logging are independently verified.
- Twilio before official automated messaging, SMS, or voice is required.
- Meta WhatsApp API and Twilio for the same channel without a clear reason.
- Multiple email marketing providers.
- Cloudinary and R2 for the same media role.
- Multi-agent orchestration.
- Automated product publishing.
- Full payment/fulfillment platform.
- Prometheus/Grafana stack.
- Public production admin access.
- Voice receptionist, document-processing agent, appointment agent, or research multi-agent system as part of the first commerce build.

## 26. Definition of Done for This Architecture

The architecture is being implemented correctly when:

1. Elegance-Shawls remains the authoritative commerce application.
2. Scraping is isolated from public request handling.
3. Products are staged before publication.
4. Jobs are durable, retryable, recoverable, and idempotent.
5. Admin decisions are authenticated, audited, and explicit.
6. HubSpot owns CRM contacts, deals, pipeline, and follow-up work without uncontrolled duplication.
7. WhatsApp, email, n8n, analytics, and monitoring integrations have clear boundaries and failure handling.
8. AI can be added without unrestricted data access or autonomous publication/messaging.
9. Production and portfolio demo data are isolated.
10. The system can begin on free/low-cost infrastructure without making unsupported free-tier availability claims.
11. Every provider has a documented replacement/exit path where practical.
12. Future scaling components have clear evidence-based triggers.
13. Each phase is independently tested and accepted before the next phase begins.
