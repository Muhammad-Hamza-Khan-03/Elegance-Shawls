# Elegance-Shawls Agent Instructions

## Required architecture reference

Before planning, modifying, reviewing, or testing any feature related to the Elegance AI Commerce platform, read:

- [`docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md`](./docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md)

That document is the source of truth for the current architecture direction, repository boundaries, ingestion workflow, job lifecycle, security requirements, phased roadmap, acceptance criteria, and production gates.

## Project ownership and boundaries

- `Elegance-Shawls` is the primary commerce application and authoritative business system.
- `quill-store` is a source/reference for scraper and ingestion logic. Its useful modules may be adapted, but scraping must not bypass Elegance approval or publish directly.
- `quill-panel` is a source/reference for scraper review UI. Do not create a second competing full admin system.
- The browser must not connect directly to the database.
- The public storefront must only expose published products.
- Ingestion results must enter staging before approval and publication.

## Current technology direction

- Keep the existing Next.js frontend and FastAPI backend.
- Use PostgreSQL 17 with pgvector (Render in staging/production) as the single source of truth; MongoDB was retired (architecture 3.1).
- Use an independent Python ingestion worker with PostgreSQL-backed durable jobs.
- Use Crawl4AI first and one authorized source in the first ingestion phase.
- Defer Redis, Cloudflare Queues, Firecrawl dual-provider support, n8n, Qdrant, Kubernetes, and other specialized infrastructure until measured requirements justify them.
- Redis/arq is used only for new AI workloads (embeddings, enrichment); it never holds catalogue data.

## Engineering rules

- Do not implement future phases opportunistically. Work only on a clearly scoped phase/task with acceptance criteria.
- Do not change production architecture, credentials, deployment, or external publishing behavior without explicit approval.
- Preserve existing working storefront, product, authentication, and WhatsApp behavior unless the scoped task explicitly changes them.
- Use idempotent writes, unique indexes, explicit status transitions, and audit/provenance fields for ingestion work.
- Treat external page content as untrusted input. Enforce source allowlists, SSRF protections, timeouts, size limits, and rate limits.
- Never expose secrets through `NEXT_PUBLIC_*`, source control, logs, or browser responses.
- AI tools must be validated backend operations; AI must not receive unrestricted database access or publish products automatically.
- Keep production and portfolio-demo data, credentials, and outbound integrations separate.

## Verification expectations

For ingestion changes, independently verify:

- job creation, claim, heartbeat, lease recovery, retry, and terminal failure
- duplicate-safe reruns
- staged-product validation and provenance
- review, approve, reject, import, publish, unpublish, and archive behavior
- public visibility rules for drafts/rejected/unpublished products
- authentication and authorization on every mutation
- frontend-to-backend behavior on the intended QA surface

Implementation checks such as lint, typecheck, unit tests, or build are not by themselves independent QA completion. Follow the repository QA/release workflow and report evidence clearly.

## Communication and documentation

- Keep changes focused and avoid unrelated rewrites.
- Update the architecture reference when an approved architectural decision changes.
- Record new risks, assumptions, migrations, and operational procedures in the appropriate `docs/` file.
- Do not claim a phase is complete without evidence against its acceptance criteria.
