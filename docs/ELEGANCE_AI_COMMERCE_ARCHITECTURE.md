# Elegance Architecture

Current-state architecture and the direction for catalogue ingestion. Only facts verifiable in this repository are stated here; deployment identifiers and release SHAs belong in release records, not in this file.

## Systems

| Component | Responsibility |
|---|---|
| `apps/frontend` | Next.js storefront and admin UI. Admin browser calls go through Next route handlers that attach the server-only `X-Admin-Key`. |
| `apps/backend` | FastAPI API. Owns products, staged products, ingestion jobs and publication state. |
| MongoDB | Single source of truth for `products`, `staged_products`, `ingestion_jobs`. |
| `quill-store` (reference repo) | Source of the scraper helpers ported into `apps/backend/ingestion/`. It is not deployed with Elegance and is never a second product store. |

The API is authoritative for publication state. Neither the crawler, a browser, nor any external tool may make a product public.

## Product lifecycle

Ingested data never enters `products` directly. See [phase-1-one-source-ingestion.md](phase-1-one-source-ingestion.md) for states, rules and the security model.

```text
source -> ingestion job -> fetched page -> extracted fields -> normalized product
       -> staged_products (pending_review) -> approve -> products (draft) -> publish (active)
```

## Out of scope until separately scheduled

Multiple sources, AI shopping assistance, CRM, WhatsApp automation, queues outside MongoDB, automatic publishing, and production catalogue migration.
