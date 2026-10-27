# Elegance AI Commerce — Architecture and Implementation Plan

> **Status:** Approved planning baseline
>
> **Primary repository:** `Elegance-Shawls`
>
> **Scope:** Product ingestion first, followed by lead capture, AI shopping assistance, CRM, automation, and analytics.
>
> **Planning rule:** This document defines the target direction and sequencing. Do not implement every phase at once. Each phase requires an explicit scoped task, acceptance criteria, and independent QA before the next phase starts.

## 1. Executive Decision

Elegance AI Commerce will remain one product centered on the existing `Elegance-Shawls` application.

The initial production-oriented architecture is:

- **Main application:** Existing Next.js storefront and FastAPI backend in `Elegance-Shawls`.
- **Database:** MongoDB Atlas as the initial single source of truth. Do not introduce PostgreSQL and MongoDB as dual sources of truth.
- **Ingestion:** Adapt the reusable scraper logic from `quill-store` into an independent Python worker/runtime.
- **Admin:** Use the existing Elegance admin surface where possible; adapt only the scraper review experience from `quill-panel`. Do not maintain two competing full admin applications.
- **Jobs:** MongoDB-backed durable ingestion jobs with atomic claims, leases, heartbeats, bounded retries, and idempotency.
- **Crawler:** Crawl4AI first, with one authorized source in Phase 1. Add Firecrawl only when a measured source-specific need justifies it.
- **Publishing:** Scraped data always enters staging and requires explicit review and approval before it can appear in the public catalogue.
- **AI:** Keep AI separate from scraping. Add a focused shopping-assistant MVP after ingestion and basic lead capture are reliable.
- **Cost posture:** Start with existing hosting and services. Treat Oracle as an optional worker host, not a hard architecture dependency. Defer Redis, Cloudflare Queues, n8n, Qdrant, Kubernetes, and other infrastructure until evidence justifies them.

This is production-oriented without pretending that free-tier hosting provides enterprise availability. The design prioritizes safe failure, recoverability, auditability, and clear ownership over premature scale.

## 2. Product Vision

Elegance AI Commerce supports the complete retail journey:

```text
Authorized product sourcing
        -> validation and staging
        -> admin review and approval
        -> published catalogue
        -> customer discovery
        -> WhatsApp enquiry or AI assistance
        -> lead capture
        -> CRM follow-up
        -> conversion analytics
```

The platform is not only a scraper and not only a storefront. It is an operational retail system. However, the implementation must progress in small slices, beginning with reliable product ingestion.

## 3. Repository Responsibilities

### 3.1 `Elegance-Shawls` — primary system

Owns the business application and authoritative business rules:

- Customer storefront
- FastAPI API
- Product catalogue and variants
- Publication status
- Inventory/status rules
- Admin authentication and authorization
- Staged-product review endpoints
- Leads and enquiries
- Future orders and CRM
- Audit events
- API contracts and environment configuration
- MongoDB indexes and persistence rules

The API, not the browser or crawler, is authoritative for business state.

### 3.2 `quill-store` — source/reference for ingestion

Reuse and adapt its useful logic for:

- Source configuration
- Crawl4AI browser execution
- Shopify URL discovery
- Product-page extraction
- Image URL extraction
- Normalization
- Validation
- Deduplication candidates
- Retry and timeout behavior
- Staged-product writes through the approved ingestion boundary

It must not:

- Publish products directly
- Bypass admin approval
- Own the public storefront
- Expose an unauthenticated crawler endpoint
- Own the canonical commerce product model

The original repository should remain intact as a reference unless a separately approved maintenance task is requested.

### 3.3 `quill-panel` — UI reference, not a second commerce system

Reuse its useful scraper controls and review table patterns:

- Start/import controls
- Job status
- Staged-product table
- Review, approve, reject, and edit actions
- Pagination and error display

Prefer adapting this experience into the existing Elegance admin. If a separate panel remains temporarily deployed, it must call the Elegance API and must not connect directly to MongoDB or contain a duplicate product business model.

## 4. Target Architecture

```text
                         Customers
                             |
                             v
                    Next.js storefront
                    (Elegance-Shawls)
                             |
                             v
                    FastAPI business API
                             |
       +---------------------+----------------------+
       |                     |                      |
       v                     v                      v
   Catalogue             Ingestion API          Leads/enquiries
   and products          and review             and WhatsApp
       |                     |                      |
       +---------------------+----------------------+
                             |
                             v
                       MongoDB Atlas
       +-------------+----------+-----------+---------+
       |             |          |           |         |
       v             v          v           v         v
    products   staged_products ingestion  leads   audit_events
                              _jobs
                                  ^
                                  |
                       Independent Python worker
                       (adapted quill-store logic)
                                  |
                          Crawl4AI + source parser
                                  |
                       Authorized supplier website
```

### Runtime boundaries

- The public API must not wait for browser crawling to finish.
- The worker is a separate process/runtime even if it initially runs on the same host.
- The worker may use the Elegance ingestion API or a tightly controlled staging writer. The API boundary is preferred as the system matures.
- The browser never connects directly to MongoDB.
- AI tools never receive unrestricted database access.

## 5. Data Ownership

| Data | Authoritative owner |
|---|---|
| Published products | Elegance API + MongoDB `products` |
| Product review state | Elegance API + `staged_products` |
| Crawl job state | `ingestion_jobs` and `ingestion_items` |
| Raw/source provenance | Staged records and optional artifact storage |
| Leads/enquiries | Elegance API + lead collections |
| Admin identity/session | Backend authentication boundary |
| Images | Initially validated source URLs; object storage later if required |
| Audit history | Elegance API + `ingestion_events`/`audit_events` |

No service may silently create a second source of truth.

## 6. MongoDB Collections and Core Records

Initial logical collections:

```text
products
staged_products
ingestion_sources
ingestion_jobs
ingestion_items
ingestion_events
leads
enquiries
audit_events
```

### 6.1 Published product rules

The canonical product record should preserve the existing Elegance schema and explicitly represent:

- Stable internal product ID
- Name/title and slug
- Description
- Category/type
- Variants
- Color/material/sizing/weight where supported
- Price and explicit currency
- Images/media references
- Availability/status
- Source/provenance reference where appropriate
- Created/updated timestamps

Do not silently invent material, origin, weight, price, or availability when source data is missing. Missing values should remain visible for review or use an explicitly labelled business default approved by the owner.

### 6.2 Staged product rules

Every staged product should retain:

- `source_id`
- `source_product_id` when available
- Canonical `source_url`
- Source domain
- Crawl timestamp
- Extracted/raw values required for review
- Normalized values
- Content hash where useful
- Validation errors/warnings
- Deduplication key
- Review status
- Reviewer and decision timestamp
- `catalog_product_id` after import
- Import/publish timestamps

### 6.3 Stable identity and deduplication

Preferred identity:

```text
source_id + source_product_id
```

Fallback identity:

```text
source_id + canonical_source_url
```

A content hash can detect changed records but must not replace a stable source identity. Use unique indexes and idempotent upserts. Re-running a job must not create duplicate catalogue products.

## 7. Source Configuration and Multi-Source Foundation

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

- Explicit domain/path allowlist
- `authorized` flag and owner approval
- Per-domain rate/concurrency limit
- Pagination and timeout limits
- Parser/provider selection
- Crawl schedule when scheduling is introduced
- Terms/compliance notes
- Source identity rules

Do not implement multiple full connectors in Phase 1. Implement the adapter boundary and one real connector.

## 8. Ingestion Pipeline

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
       Explicit publish action
```

Preferred extraction order:

1. Official API, feed, or structured source data where authorized.
2. Static/structured HTML parsing.
3. Crawl4AI/browser rendering only when required.
4. Optional AI enrichment for missing or draft fields.

AI must not be a mandatory dependency for basic ingestion success.

## 9. MongoDB-Backed Job System

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
9. Back off polling when no job is available; do not hot-poll Atlas M0.
10. Preserve per-item errors so one bad product does not fail the entire run.

Redis, Celery, Cloudflare Queues, and other queue infrastructure are deferred until measured workload requires them.

## 10. Product Review and Publication

Product states:

```text
discovered
  -> normalized
  -> needs_review
  -> approved
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

## 11. API Contract Direction

The exact routes must follow the existing Elegance API conventions, but the intended capabilities are:

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
```

Requirements:

- All mutations authenticated and authorized server-side.
- Idempotency keys on job creation and sensitive imports.
- Stable error response shape.
- Pagination for jobs and staged products.
- No secrets in response bodies or logs.
- Public catalogue routes only return published products.

## 12. Security Requirements

### Admin authentication

The current admin authentication design must be reviewed before extending the system. Do not expose an admin secret through `NEXT_PUBLIC_*` variables or browser-delivered source.

Preferred production direction:

- Server-side session or secure short-lived token
- HTTP-only, Secure, SameSite cookie where cookie auth is used
- CSRF protection for cookie-authenticated mutations
- Server-side authorization on every admin mutation
- Roles such as administrator, catalogue editor, reviewer, and read-only operations when needed
- Rate limits on admin and ingestion routes

### Scraper safety

- Only approved domains and paths may be fetched.
- Block localhost, loopback, link-local, private-network, and cloud-metadata destinations.
- Validate every redirect destination.
- Bound page count, response size, browser time, concurrency, and total job duration.
- Treat page content and embedded instructions as untrusted data.
- Respect applicable authorization, terms, robots guidance, and rate limits.
- Do not publish third-party images/descriptions without appropriate rights.

### API and database safety

- HTTPS in deployed environments.
- Exact CORS origins.
- No public MongoDB exposure.
- Least-privilege database credentials.
- Separate staging and production credentials/databases.
- Secret scanning in CI.
- Redaction of credentials, cookies, customer data, and private messages from logs.
- Upload type, size, and content validation.

## 13. AI Architecture

AI is a separate capability from scraping.

### AI shopping assistant tools

Expose only validated backend tools:

```text
search_products()
get_product_details()
check_availability()
request_lead_capture()
```

The AI agent must not:

- Query MongoDB directly
- Publish products
- Invent price, stock, material, origin, or availability
- Modify orders without validated authorization
- Send external messages without consent and an approved workflow

Initial AI placement:

```text
apps/backend/ai/
├── agents/
├── tools/
├── prompts/
└── services/
```

Keep the module inside the FastAPI application initially. Preserve a clean service boundary so it can be deployed separately only when latency, traffic, or operational ownership justifies that change.

### AI enrichment

After deterministic ingestion works, AI may propose:

- Draft descriptions
- Category/tags
- Translation
- Duplicate warnings
- Standardized copy

Every AI result remains draft content until an operator approves it.

## 14. Lead, WhatsApp, and CRM Roadmap

Do not treat a WhatsApp handoff as a completed order.

### Phase 2 lead capture

Record:

- Product and variant
- Quantity
- Quoted price and currency
- Customer contact details where consented
- Generated WhatsApp message/reference
- Source page/session context
- Lead state

Suggested states:

```text
initiated -> contacted -> converted
                    -> cancelled
                    -> expired
```

### Later CRM

Only after lead capture works reliably, add:

- Lead search/filtering
- Assignment
- Pipeline stages
- Contact activity
- Follow-up tasks
- Lead-to-order conversion
- Audit history

AI qualification and automated follow-up drafts must remain human-reviewed initially.

## 15. Environment and Hosting Strategy

Initial services:

- Next.js frontend on the existing managed frontend host.
- FastAPI API on the existing backend host.
- MongoDB Atlas as the initial database.
- Independent Python worker on a portable runtime; Oracle Free VM is optional, not a hard dependency.
- Existing hosted Firecrawl remains optional.
- Object storage is added only when image ownership or large artifacts require it.
- GitHub Actions handles CI and can later trigger bounded scheduled jobs.

### Oracle VM guidance

If the Oracle VM is used:

- Start worker concurrency at 1.
- Add hard timeouts and memory limits.
- Do not run n8n, Redis, a full Firecrawl stack, and high-concurrency Chromium together without measured resource validation.
- Keep the worker container portable.
- Monitor CPU, memory, disk, and restarts.

### Budget posture

Target $0–$20/month initially, subject to provider free-tier and commercial-use restrictions. Do not claim guaranteed production availability from free tiers. Upgrade only when a measured bottleneck or business requirement exists.

## 16. Portfolio Demo Separation

Production and public portfolio demo environments must be separate.

### Production

- Real catalogue and business data
- Protected admin
- Real credentials
- No public admin access
- Real outbound integrations only with consent and approval

### Portfolio demo

- Synthetic products and customers
- Demo ingestion jobs
- Resettable or read-only data
- Safe AI conversations
- No production credentials
- No real outgoing WhatsApp messages
- Clearly labelled `Portfolio Demo — Synthetic Data`

Never expose production admin credentials to recruiters or public visitors.

## 17. Phased Implementation Roadmap

### Phase 0 — Contracts and hardening

Deliver:

- Canonical product and staged-product schemas
- Source authorization policy
- Currency and image policy
- Approval states
- Duplicate identity rules
- Authentication/authorization review
- Required MongoDB indexes
- Backup/export and recovery procedure
- Environment separation plan

Exit gate: the data contract and security boundaries are documented and accepted before code changes begin.

### Phase 1 — Reliable product ingestion

Build only:

- One authorized source
- One Crawl4AI connector
- Source configuration boundary
- MongoDB-backed jobs
- Separate worker
- Validation and normalization
- Stable identity/deduplication
- Staged products
- Per-item errors
- Review UI
- Approve/reject/edit
- Explicit catalogue import and publish
- Retry, lease recovery, and health status

Exit gate: rerunning the same source produces no duplicate products; failed items are visible and retryable; only approved products can appear publicly.

### Phase 2 — Catalogue operations

Add:

- Public catalogue/search/filter improvements
- Product detail and variant management
- Publish/unpublish/archive
- Manual correction protection
- Image handling and basic SEO

Exit gate: a reviewed product can be safely published, updated, unpublished, and archived without exposing drafts.

### Phase 3 — Lead capture

Add:

- Product enquiry flow
- WhatsApp handoff/reference
- Lead record and status
- Product/price snapshot
- Basic admin lead view

Exit gate: a customer enquiry creates one traceable, idempotent lead record.

### Phase 4 — AI shopping assistant MVP

Add:

- Catalogue search tool
- Product detail tool
- Availability tool
- Conversational recommendations
- Consent-based lead capture
- Human fallback
- Tests for hallucinated/nonexistent/out-of-stock products and invalid lead data

Exit gate: the assistant recommends only real published products and cannot create unauthorized business mutations.

### Phase 5 — CRM and automation

Add only after real lead volume justifies it:

- Pipeline
- Assignment
- Follow-ups
- Activity history
- AI qualification drafts
- Human-reviewed notifications

### Phase 6 — Scale and specialized infrastructure

Introduce only with evidence:

- Redis or Cloudflare Queues
- Multiple worker replicas
- Firecrawl adapter
- Multi-source schedules
- R2/object storage
- Advanced observability
- Vector search
- n8n
- PostgreSQL migration if transactional requirements justify it

## 18. Phase 1 Acceptance Criteria

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

## 19. Production Gates

Do not call the ingestion system production-ready until:

- Staging and production data/credentials are isolated.
- Admin authentication and authorization are independently verified.
- Worker restart and lease recovery are tested.
- Duplicate rerun behavior is tested.
- A failed item and failed job can be retried safely.
- Public routes exclude staged/draft/rejected products.
- Backups/exports exist and a restore test has succeeded.
- Logs and alerts identify API and worker failures.
- Source authorization and content-rights assumptions are documented.
- Frontend-to-backend staging acceptance passes.
- Owner approval is recorded for production publication and external messaging.

## 20. Migration Trigger for PostgreSQL

MongoDB remains the initial database. PostgreSQL is a future decision, not a parallel database.

Re-evaluate migration when the application requires one or more of:

- Payment-backed checkout
- Concurrent inventory reservation
- Multiple warehouses
- Complex order/item relationships
- Strong relational CRM workflows
- Advanced reporting that is difficult to maintain safely
- MongoDB model limitations causing repeated business logic defects

If migration is approved:

1. Freeze catalogue writes for a bounded window.
2. Export MongoDB data.
3. Transform and validate products, variants, slugs, prices, and statuses.
4. Load PostgreSQL staging tables.
5. Reconcile counts and representative records.
6. Switch the API once verification passes.
7. Retain the MongoDB export as a protected rollback/archive artifact.
8. Do not dual-write indefinitely.

## 21. Major Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Source blocks or changes markup | Authorized sources, isolated adapters, rate limits, fixtures, change detection |
| Duplicate imports | Stable source identity, unique indexes, idempotent upserts |
| Worker crash | Leases, heartbeats, retries, expired-lease recovery |
| Wrong product data | Staging, validation, provenance, human approval |
| Manual edits overwritten | Separate imported/manual values or field-level conflict review |
| AI hallucination | Tool restrictions, draft-only outputs, approval gate, spending limits |
| Database outage | Exports, backup policy, restore drill |
| Credential leakage | Managed secrets, redaction, rotation, secret scanning |
| Admin endpoint exposure | Server-side auth, roles, rate limits, exact CORS |
| Free-tier instability | Portable worker, provider health checks, documented upgrade triggers |
| Public demo contaminates production | Separate environment, synthetic data, no production credentials |

## 22. What Not to Build Yet

Do not add these to Phase 1 without a specific approved task and measured justification:

- Kubernetes
- Service mesh
- Multiple databases
- Redis/Celery/Cloudflare Queue
- Full Firecrawl self-hosting
- Qdrant or vector search
- n8n as the business backend
- Multi-agent orchestration
- Automated product publishing
- Full payment/fulfillment platform
- Prometheus/Grafana stack
- Public production admin access

## 23. Definition of Done for This Architecture

The architecture is being implemented correctly when:

1. Elegance-Shawls remains the only authoritative commerce application.
2. Scraping is isolated from public request handling.
3. Products are staged before publication.
4. Jobs are durable, retryable, recoverable, and idempotent.
5. Admin decisions are authenticated, audited, and explicit.
6. AI can be added without granting unrestricted data access.
7. Production and portfolio demo data are isolated.
8. The system can begin on free/low-cost infrastructure without making free-tier availability claims.
9. Future scaling components have clear evidence-based triggers.
10. Each phase is independently tested and accepted before the next phase begins.
