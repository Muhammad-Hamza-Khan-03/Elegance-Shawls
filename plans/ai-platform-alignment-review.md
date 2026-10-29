# Plan alignment review

Compares `elegance-shawls-ai-platform-plan.md` (v1.0, 2026-10-29) against the repository on branch `phase-1/one-source-ingestion`.

Verdict: the plan matches the **foundation** very well. It diverges on **backend shape, queueing, and what "Phase 1" means**. It does not mention the ingestion pipeline that is already built.

---

## 1. Aligns perfectly

| Plan item | Evidence in repo |
|---|---|
| Next.js 16 / React 19 storefront: catalogue, product pages by slug, cart, WhatsApp handoff | `apps/frontend/src/app/product/[slug]`, `src/lib/cart.ts`, `src/lib/whatsapp.ts` |
| FastAPI + Motor product API with cursor pagination, slug lookup, admin create/update/publish/stock/archive | `routes/product_routes.py`, `utils/pagination.py` |
| MongoDB keeps the catalogue (ADR 002) | `database/db.py`; the architecture doc names Mongo the single source of truth |
| Rate limiting, request logging, health/ready probes | `security/rate_limit.py`, `observability/request_log.py`, `/health/`, `/ready/` |
| Compose stack with Caddy TLS proxy, only the proxy publishes ports | `compose.yaml`, `deploy/Caddyfile` |
| Backup, restore drill, rollback, watchdog scripts | `deploy/backup/*`, `deploy/rollback.sh`, `deploy/monitoring/watchdog.sh` |
| CI: lint, typecheck, tests, `npm audit`, `pip-audit`, build, Playwright E2E | `.github/workflows/ci.yml` |
| Runbooks | `DEPLOYMENT.md`, `OPERATIONS.md`, `LAUNCH_RUNBOOK.md` |
| Gap: shared `ADMIN_API_KEY`, no users, roles or audit log | Still true (`security/admin_auth.py`). Closing it in Phase 3 is sensible. |
| Gap: free-text variant `color` | `schemas/variant_schema.py:12` is `Optional[str]` |
| Gap: no LLM, embeddings, events, staging env, tracing | None exist (`requirements.txt` has no LLM/vector/OTel libs) |
| Gap: Orders page is a placeholder | `app/admin/(shell)/orders/page.tsx` |
| Orders, CRM, WhatsApp Business API postponed | The architecture doc also lists them as out of scope |
| Proxy pattern for admin calls from the browser | The plan's new admin endpoints fit the existing Next route-handler proxy |
| Conventional commits, ADRs, runbooks culture | `CONTRIBUTING.md`, `docs/` |

## 2. Aligns partially

| Plan item | What exists | What differs / needs deciding |
|---|---|---|
| **"Phase 1: Catalogue intelligence"** | The repo's own "Phase 1" is *one-source ingestion*: scrape, stage, review, publish (`ingestion/`, `docs/phase-1-one-source-ingestion.md`, `/admin/staging`). | Same name, different scope. The plan's Phase 1 is vocab, enrichment, embeddings and hybrid search. Rename one, or treat the ingestion work as "Phase 0.5". |
| **AI catalogue enrichment** (photo → attributes, description, SEO, staff approval) | A human-in-the-loop review flow already exists: `staged_products` with `pending_review → approve → draft → publish`, normalisation, markdown descriptions, a PKR suggestion route. | There is no vision LLM, and the plan does not use the staging model. Enrichment should plug into `staged_products` review, not add a parallel `enrichment_jobs` flow. |
| **Workers / queue** | `ingestion/worker.py` and `jobs.py` use **Mongo-backed jobs**, with `monthly_refresh.sh`. | The plan says Redis + arq. The architecture doc says "queues outside MongoDB" are out of scope. Either adopt arq and migrate the ingestion worker, or keep Mongo jobs for ingestion and use arq only for new AI work (two systems). Needs an ADR. |
| **Audit log** | `models/audit_entry` exists in the ingestion model. | It is Mongo, ingestion-only. The plan wants a Postgres `audit_log` covering admin and agent writes. |
| **Admin identity** | HMAC-signed session cookie, 8h TTL, login throttle (`admin-session.ts`, `admin-login-throttle.ts`). | Still one shared key. Keycloak (Phase 3) is a large step. A lighter option (a users collection with roles) could meet the roles/audit goal. |
| **Backend modular monolith** | Flat layout: `routes/ schemas/ models/ ingestion/ security/ utils/`. | The plan wants `app/{catalog,identity,agent,memory,...}`. This is a restructure of every import (top-level module style, tests, Dockerfile). Do it once, early, and explicitly. |
| **API versioning `/v1`** | Routes live at `/products/...` and `/products/admin/...`. | New plan endpoints are `/v1/...`. Decide whether to version the existing routes too. Frontend `src/lib/api.ts` and the e2e mock API depend on current paths. |
| **Docker Compose** | `compose.yaml` and `compose.local.yaml` exist. | No Postgres, pgvector or Redis. Phase 0 adds these. Memory budget on the VPS needs rechecking with the extra services. |
| **CI/CD** | Solid CI, no image publishing. | Missing: GHCR multi-arch images, Trivy, gitleaks, CodeQL, SBOM, evals job. |
| **Search** | Cursor-paginated feed with category filter (`ProductBrowser`, `CategoryFilter`). | No attribute filters, no text query, no ranking. The plan's hybrid search is a new subsystem. |
| **Accessibility tests** | `accessibility.test.tsx` exists. | The plan says to extend them for the assistant panel. The panel does not exist yet. |
| **Hosting** | Self-hosted compose + Caddy, plus a `vercel.json` in the frontend. | The plan targets one VPS and warns against Vercel Hobby for commercial use. Check whether `vercel.json` is a leftover or an active deploy path. |
| **Interaction logging "from day one"** | Request logging only. | No storefront event tracker or `events` store. This is net-new, and it is the cheapest item to do first. |
| **Product IDs across stores** | Mongo `ObjectId`s via `utils/bson.py`. | The plan references them as strings in Postgres. This is workable, but `product_id` stability on archive/re-import should be confirmed. |

## 3. Does not align (or is not in the plan at all)

### In the plan, absent from the repo (all planned, expected)
- Postgres / pgvector / SQLAlchemy / Alembic
- Redis / arq
- LiteLLM, any LLM call, agent loop, tool registry, prompts, SSE chat endpoint
- Assistant panel and Vercel AI SDK in the frontend
- Embeddings (text or image), `vocab.yaml`, multilingual synonyms, normalised attributes
- Customer identity, memory, recommendations
- Voice / ASR
- `evals/`, MLflow, DVC, Langfuse, OpenTelemetry, Grafana
- k3s, Helm, Argo CD, OpenTofu, Ansible, SOPS
- Staging environment
- `docs/adr/`, C4 diagrams

### In the repo, missing from the plan (the plan's biggest blind spot)
- **The whole ingestion subsystem** (`apps/backend/ingestion/`, 13 modules, about 15 test files, `/admin/staging`, `docs/phase-1-one-source-ingestion.md`). Section 5 "Current state" never mentions it. The plan's "Time to publish a product ↓ 50%" and "Products with complete attributes" metrics should build on it.
- **SSRF and fetch hardening** (`safe_fetch.py`, `staging_guard.py`) and **FX / PKR conversion** (`fx.py`). The plan's "PKR prices" assumption already has code behind it.
- **Existing state machine** (`schemas/can_transition`, `StagedStatus`, `JobStatus`). Reuse it for the enrichment status instead of adding a new one.
- **Sitemap / robots / OpenGraph** SEO work. The plan's "SEO text" enrichment should target these.
- **`INTERNAL_API_TOKEN`** (frontend ↔ backend internal calls) and the admin login throttle. These are security building blocks the plan's Keycloak section ignores.
- **`docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md` explicitly lists "AI shopping assistance" as out of scope until separately scheduled.** Adopting this plan means updating that doc, which is a formal scope decision.

### Points where the plan conflicts with current repo rules
- Repo `CLAUDE.md` / architecture doc: *the API is authoritative for publication state; no external tool may make a product public.* The plan's admin-copilot write tools (`set_status`, `apply_enrichment`) must go through the same approval path.
- Frontend proxy rule: new admin endpoints must use `proxyAdminRequest`. Plan routes under `/v1/admin/enrichment/...` need matching Next route handlers.
- CSP in `next.config.ts` is strict. The assistant (SSE, voice mic, any new connect target) needs explicit allowances.

---

## 4. Suggested adjustments before starting

1. **Rename phases.** Call the finished ingestion work "Phase 0.5" or fold it into Phase 0, and add it to section 5.
2. **Add one ADR on queues.** Mongo jobs vs. arq; choose one story for workers.
3. **Add one ADR on backend layout and `/v1`.** Do the restructure as its own PR with no behaviour change.
4. **Reuse staging for enrichment.** Make AI enrichment a producer of `staged_products` review items.
5. **Start with `events` logging and the Postgres base.** It is the plan's own Phase 0 and has no dependency on LLM choices.
6. **Right-size identity.** Keep the signed-cookie admin session and add roles/users before committing to Keycloak's RAM cost.
7. **Update `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md`** to move AI assistance in scope.

## 5. Scorecard

| Area | Fit |
|---|---|
| Current storefront / API / ops baseline (plan §5) | Perfect |
| Goals, gaps and postponed tracks | Perfect |
| Data stores (Mongo + Postgres split) | Good, with the new infra still to add |
| Workers, enrichment, backend layout, API paths, admin identity | Partial: needs ADRs |
| Ingestion pipeline | Not in the plan |
| LLM / agent / memory / voice / MLOps / k8s | Greenfield; consistent with the repo, nothing to conflict with |
