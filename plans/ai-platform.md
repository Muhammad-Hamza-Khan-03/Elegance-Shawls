# Elegance Shawls: AI Commerce Platform Plan

> **Status: HISTORICAL / SUPERSEDED for the database architecture — do not use as current instructions.**
> - PostgreSQL is now the **sole runtime database** (`DATABASE_URL` is required).
> - MongoDB removal was **completed in S4** (code, dependencies, compose, CI and backup scripts).
> - Every MongoDB, Motor, Atlas, archive-to-R2 and Mongo-backup instruction below is **historical only**, kept for audit value. This document must not be used as deployment instructions.
> - Authoritative documents: `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md`, `DEPLOYMENT.md`, `OPERATIONS.md`.
> - The roadmap content below is otherwise unchanged.

> Turning a catalogue + WhatsApp storefront into a shop that understands its customers, built mostly on free and open-source tooling, and used as a structured path through AI engineering, data science, ML/LLMOps and DevOps.

| | |
|---|---|
| **Owner** | Muhammad Hamza Khan |
| **Repository** | `Muhammad-Hamza-Khan-03/Elegance-Shawls` (reviewed at `23e33e2`) |
| **Document status** | **v2.0, final baseline for development.** Changes from here go through ADRs ([section 27](#27-architecture-decision-records)) and the version history ([section 2](#2-version-history)) |
| **Last updated** | 2026-10-29 |
| **Budget** | **Stage 1: ~$0/month** (current hosts + free tiers). **Stage 2: ~$8–16/month VPS** + optional serverless GPU, when affordable ([section 23](#23-budget)) |

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Version history](#2-version-history)
3. [Purpose](#3-purpose)
4. [Problem](#4-problem)
5. [Goals, non-goals and constraints](#5-goals-non-goals-and-constraints)
6. [Current state of the repository](#6-current-state-of-the-repository)
7. [The golden journey](#7-the-golden-journey)
8. [Final technology decisions](#8-final-technology-decisions)
9. [Target architecture](#9-target-architecture)
10. [Detailed design](#10-detailed-design)
11. [Data model](#11-data-model)
12. [API and streaming design](#12-api-and-streaming-design)
13. [Models and AI cost](#13-models-and-ai-cost)
14. [Infrastructure and hosting](#14-infrastructure-and-hosting)
15. [MLOps and LLMOps](#15-mlops-and-llmops)
16. [DevOps and platform engineering](#16-devops-and-platform-engineering)
17. [Engineering practices and evidence](#17-engineering-practices-and-evidence)
18. [Testing strategy](#18-testing-strategy)
19. [Security, privacy and guardrails](#19-security-privacy-and-guardrails)
20. [Reliability, backups and incidents](#20-reliability-backups-and-incidents)
21. [Roadmap: milestones](#21-roadmap-milestones)
22. [Postponed tracks](#22-postponed-tracks)
23. [Budget](#23-budget)
24. [Success metrics and measurement](#24-success-metrics-and-measurement)
25. [Risks and mitigations](#25-risks-and-mitigations)
26. [Repository structure](#26-repository-structure)
27. [Architecture decision records](#27-architecture-decision-records)
28. [Learning outcomes and portfolio deliverables](#28-learning-outcomes-and-portfolio-deliverables)
29. [Resource triage (models and repos)](#29-resource-triage-models-and-repos)
30. [Glossary](#30-glossary)
31. [References](#31-references)

---

## 1. Executive summary

**What we're building.** A shop that understands its customers. A customer can say, in English or Urdu, by text or voice, "brown stole under 4,000". The system finds the **right in-stock variant**, shows it, helps them into a **verified cart**, hands off to **WhatsApp** with an enquiry reference, and records the **outcome**. Over time it remembers what the customer has asked it to remember and explains its suggestions.

**Why.** Today customers browse a grid, search only the first 100 products in the browser, and leave for WhatsApp. The store learns nothing from visits, can't personalise, and catalogue work is manual. The project is also the vehicle for learning how dependable AI systems are built and operated.

**How.**

- **Fix the foundation first:** complete server-side search, variant-correct filters, trustworthy attributes with provenance, and recovery basics.
- **One search service** shared by the product browser and the assistant: exact filters for hard constraints, lexical + semantic ranking for relevance.
- **An assistant whose actions are validated by application code**, reusing the existing cart verification and WhatsApp handoff.
- **Explicit, controllable memory** with correction and deletion that actually stick.
- **Eval-gated LLMOps**: prompts, models, retrieval index and configuration are versioned together; empty evals never authorise a release.
- **Two hosting stages.** **Stage 1** builds everything on the current hosts and free tiers, with Groq/Gemini models behind LiteLLM. **Stage 2** moves to one budget VPS and self-hosted models (local LLM, embeddings, speech) when affordable, as a configuration change rather than a rewrite.
- **Local LLM track in parallel:** open models and fine-tuning practised for free on Kaggle/Colab and a laptop, ready to serve in Stage 2.
- **Compose first**; Kubernetes/GitOps learned separately and adopted when justified.

**Strategy.** Make one journey excellent before widening scope:

> "brown stole under 4,000" → correct in-stock variant → verified cart → WhatsApp enquiry → recorded outcome

Each milestone produces something usable even if work pauses there. The timeline is a planning hypothesis, not a commitment.

---

## 2. Version history

| Version | Date | Summary |
|---|---|---|
| v1.0 | 2026-10-29 | First complete plan |
| v1.1 | 2026-10-29 | External design review adopted (table below) |
| v1.2 | 2026-10-29 | ADR-002 accepted: catalogue consolidated into PostgreSQL; production MongoDB holds one product, so it's a direct switch, not a migration |
| **v2.0** | 2026-10-29 | **Final baseline:** two hosting stages (free now, VPS later); provider interfaces for LLM, embeddings and speech; local LLM track (CPU sub-task model, fine-tuning on Kaggle, optional serverless GPU); privacy gate before customer memory |

### Changes adopted in v1.1

An external design review of v1.0 was checked against the code at `23e33e2` and against vendor documentation.

| Area | v1.0 | v1.1 |
|---|---|---|
| Starting point | Start with AI foundations | **Start with a reliable catalogue**: the storefront only fetches `limit=100` without following the cursor and searches that subset in the browser |
| Matching | Product-level filters | **All hard conditions must match the same purchasable variant** |
| Constraint relaxation | Price relaxed automatically when nothing matches | **Hard constraints are never relaxed automatically**; the assistant asks. Soft constraints ("around 4,000") have a disclosed tolerance |
| Ranking | Semantic only | **Lexical + semantic**, fused, inside exact filters |
| Two databases | Mongo catalogue + Postgres, sync understated | **Decided (ADR-002, accepted): the catalogue moves into PostgreSQL**; MongoDB is removed after the switch (it holds one product, so no data migration) |
| Agent actions | UI tools executed as streamed | **Model proposes, application validates**; actions reuse existing cart and WhatsApp code; action IDs, idempotency, bound and expiring confirmations |
| Streaming | Custom SSE events with Vercel AI SDK | **AI SDK UI message stream protocol** (or an explicit adapter) |
| Memory | Stated vs. observed | Five categories (persistent preference, session constraint, weak signal, purchase context, deletion), **deletion that survives queued jobs**, conservative anonymous merge |
| Enrichment | Vision LLM could suggest fabric | **Provenance per attribute**; fabric/composition only from supplier or staff; unknowns stay unknown |
| Embeddings | Separate text and image models | **Benchmark EmbeddingGemma 2's shared multimodal space** against separate models first |
| Voice | WER as promotion metric | **Task success and critical-entity accuracy** (prices, negations, category) gate promotion; custom ASR is a research experiment |
| Order of ops work | Backups and k3s late | **Off-server backups, restore verification, alerts and rollback come before memory and voice**; k3s/GitOps learned separately |
| Existing environments | "No staging" | **Inventory and reuse** existing staging and the current Vercel/Render/Atlas configuration referenced in the runbooks |
| Frontend images | "Same image across environments" | Requires **runtime configuration** first; `NEXT_PUBLIC_*` values are baked in at build time today |
| Mongo driver | Motor | **Removed with MongoDB** (Motor deprecated May 14, 2026, so no driver migration is needed) |
| Schema | Nullable column inside a primary key | **Separate product and variant embedding tables** |
| Evals | Empty sets pass | **Empty set = "not evaluated", which blocks AI releases**; critical constraints scored separately |
| Rollback | Containers and prompts | **Retrieval index and configuration versioned too**; expand/contract migrations |
| Business loop | WhatsApp click as success | **Enquiry reference + staff-recorded outcome**; log recommendation **impressions and positions**; **randomised** comparisons |
| Budget | Fixed VPS price | Treated as an **assumption**; inventory current hosting and benchmark first |
| Wording | "Roman Urdu" as a spoken language; "MongoDB has no transactions" | Customers **speak Urdu**; transcripts are rendered in Urdu script or Roman Urdu. MongoDB **does** support transactions; Postgres is chosen for relationships and operations |

---

## 3. Purpose

**Business purpose.** Help a Pakistan-first shawl, stole, scarf and hijab store sell more by making online shopping feel like talking to a knowledgeable shop assistant who remembers you.

**Learning purpose.** Build the system the way a dependable engineering team would (clear architecture, documented decisions, evaluation-gated AI, observability, recovery, infrastructure as code) and gain real experience in:

- **AI engineering:** agents, tool use, retrieval, memory, speech.
- **Data science and ML:** embeddings, ranking, evaluation design, experimentation.
- **MLOps / LLMOps:** versioning, registries, eval gates, rollouts, monitoring.
- **DevOps / platform:** containers, CI/CD, IaC, observability, recovery, later Kubernetes and GitOps.

**Operator purpose.** At any time, be able to answer: *Why did this customer receive this recommendation? Which model, prompt and catalogue revision were involved? Did the browser execute the action? What did it cost? Can I disable or roll back the feature?*

---

## 4. Problem

### 4.1 Customer problems

| Problem | Effect |
|---|---|
| Storefront loads at most 100 products and searches them in the browser | Beyond 100 published products, some become undiscoverable |
| Search matches text only (name, material); no colour family, price or stock filters | "Brown stole under 4,000" can't be expressed |
| Colour names are inconsistent ("chocolate", "coffee", "camel") | A "brown" search misses relevant products |
| No memory between visits | Every visit starts from zero |
| Many customers prefer speaking Urdu | Typed English search excludes how people actually shop |
| Ordering leaves for WhatsApp with no reference | No link between what was shown, what was asked and what sold |

### 4.2 Business and operational problems

| Problem | Effect |
|---|---|
| Descriptions, tags and SEO text written by hand | Slow catalogue updates; inconsistent attributes |
| No data on searches, impressions or outcomes | No basis for decisions, ranking or forecasting |
| Shared admin key | No individual accountability; unsafe for AI-assisted approvals |

### 4.3 Technical problems

| Problem | Effect |
|---|---|
| No server-side search service | Browser and future assistant would implement search differently |
| No relational store or vector index | No joins for customers/events; no semantic retrieval |
| Catalogue in MongoDB (Motor driver, deprecated May 2026) while new domains need PostgreSQL | Two stores to sync, back up and operate; resolved by ADR-002 (production holds one product, so no data migration) |
| Frontend config baked in at build time | The same image can't be promoted between environments |
| No AI evaluation process | Changes could silently make the assistant worse |

### 4.4 Learning problem

Previous Next.js + FastAPI projects worked but didn't scale and didn't follow dependable-engineering practice. There's no experience yet with how teams design, ship, evaluate and operate AI systems.

---

## 5. Goals, non-goals and constraints

### 5.1 Goals

1. **Reliable catalogue:** complete server-side browsing and search; variant-correct filters; attributes with provenance.
2. **Shared search service:** exact filters + lexical + semantic ranking, used by both the browser and the assistant.
3. **Shopping assistant:** understands requests, shows cards, opens pages and helps with the cart through validated actions.
4. **Returning-customer experience:** explicit memory with correction and deletion; explainable recommendations.
5. **AI catalogue assistance for staff:** drafts and suggestions with provenance and approval.
6. **Voice:** Urdu and English speech input measured by task success.
7. **Dependable operations:** backups, verified restores, alerts, rollback, versioned AI releases, traces.
8. **Closed business loop:** enquiry reference and recorded outcomes without building an order system.

### 5.2 Non-goals

- Microservices for their own sake.
- Full CRM, WhatsApp Business API automation, order management and the analytics data platform (postponed, [section 22](#22-postponed-tracks)).
- Payment processing.
- Pretraining or self-hosting large language models.
- AI image generation for storefront content.
- High availability. A single-server setup has one host failure domain; recovery is the goal, not zero downtime.

### 5.3 Constraints

| Constraint | Consequence |
|---|---|
| Solo developer, part-time | Small milestones; each usable on its own; no gold-plating |
| Small budget | One server; free tiers elsewhere; lean resource use |
| Production catalogue holds one product | Switching databases is cheap now; full re-indexing is trivial |
| Pakistan-first users | Urdu (spoken), Urdu script and Roman Urdu text; PKR prices; low latency from Pakistan |
| Free LLM tiers may train on data | No personal data to those tiers; paid no-training model with real users |
| WhatsApp ordering is intentional | Keep it; add references and outcomes rather than an order system |

---

## 6. Current state of the repository

Reviewed at commit `23e33e2` on 2026-10-29.

### 6.1 Strengths to preserve

- **Cart verification** (`CartPage.tsx`, `lib/cart.ts`): rechecks current prices and availability, asks the customer to acknowledge changes, and blocks the WhatsApp handoff when the catalogue can't be verified.
- **Product lifecycle:** published products are separated from drafts and archived products.
- **Admin hardening:** signed admin sessions, constant-time key comparison, login throttling, same-origin checks on admin writes.
- **Operability:** health and readiness probes, rate limiting, request logging, Compose stack with Caddy, backup/restore-drill/rollback/watchdog scripts.
- **CI:** lint, typecheck, unit tests, `npm audit`, `pip-audit`, build, Playwright E2E (mocked and live).
- **Evidence discipline:** `docs/qa/2026-10-28-local-acceptance.md` records recovery and cart checks and states its own scope (local only).

### 6.2 Gaps

| Gap | Evidence | Addressed in |
|---|---|---|
| Storefront fetches `/products/?limit=100` and never follows the cursor | `apps/frontend/src/lib/api.ts` | M1 |
| Search, filtering and pagination happen in the browser on that subset | `ProductBrowser.tsx`, `lib/catalog.ts` | M1 |
| No colour family, price-range or stock filters; no variant-level matching | `lib/catalog.ts`, product routes | M1 |
| Free-text variant colour; no normalised attributes or provenance | `models/product_model.py` | M1–M2 |
| Shared `ADMIN_API_KEY`; no individual admin identity | `security/admin_auth.py`, `lib/admin-session.ts` | M1 |
| Catalogue in MongoDB via Motor | `database/db.py` | M1 (ADR-002: move to PostgreSQL) |
| `NEXT_PUBLIC_*` baked in at build time | `compose.yaml`, frontend `Dockerfile` | M6 |
| No embeddings, LLM integration, evals or traces | — | M2–M3 |
| Off-host backup upload not yet verified | QA doc "Not covered" list | M1 |

### 6.3 Existing environments (to inventory)

The runbooks reference a **staging** environment, a separate admin panel (**Quill**) that writes through `/products/admin/*`, and production configuration on **Vercel, Render and MongoDB Atlas**. The repository alone doesn't establish their current state. Milestone 1 starts by inventorying them (plans, regions, limits, costs, who has access) and reusing what works.

---

## 7. The golden journey

Everything in this plan serves one end-to-end journey first:

```
Ayesha: "Mujhe brown stole chahiye, 4,000 se kam."
  1. Understand   → category=stole · color_family=brown · max_price=4000 (hard) · in_stock=true
  2. Search       → only variants where ALL hard conditions hold on the same variant
  3. Show         → cards (or open the page if exactly one match)
  4. Choose       → "show me the second one" opens the right product
  5. Cart         → add_to_cart proposed → existing cart rules validate → customer confirms
  6. Verify       → existing cart verification rechecks price and stock
  7. Hand off     → WhatsApp message prefilled with an enquiry reference (e.g. ES-7F3K)
  8. Outcome      → staff marks the enquiry contacted / converted / lost
  9. Learn        → impressions, positions, actions and outcome are logged for evaluation
```

If nothing matches all hard conditions, the assistant does **not** quietly change them:

> "Nothing matches all of those right now. Would you like a different colour within your budget, or brown options slightly above 4,000?"

---

## 8. Final technology decisions

| Layer | Decision | Notes |
|---|---|---|
| Backend | **Modular monolith (FastAPI)** + bounded worker processes | Services extracted only for different hardware/scaling needs |
| Frontend | **Next.js 16** (existing) with runtime configuration | Needed for image promotion |
| Database | **PostgreSQL 17 + pgvector, the single database** (ADR-002, accepted) | Catalogue, embeddings, customers, memory, events, enquiries, audit. MongoDB and Motor removed after the switch |
| Catalogue IDs | **Existing 24-character hex IDs preserved** (`CHAR(24)`); new IDs in the same format | Browser carts and Quill keep working; public API contract unchanged |
| Data access | **`CatalogRepository` interface**, async SQLAlchemy + asyncpg | Single PostgreSQL implementation; no dual-running |
| ORM / migrations | **SQLAlchemy 2 + Alembic**, expand/contract migrations | Safe rollbacks |
| Lexical search | **PostgreSQL full-text search + `pg_trgm`** | Names, SKUs, distinctive phrases, typos |
| Semantic search | **pgvector (HNSW)** | No separate vector DB |
| Rank fusion | **Reciprocal rank fusion** of lexical and semantic | Inside exact filters |
| Embeddings | **Benchmark EmbeddingGemma 2 (shared text/image space)** vs. separate text + image models | Decided by retrieval eval |
| Provider interfaces | **`EmbeddingProvider`** and **`SpeechProvider`** interfaces, like LiteLLM for chat models | Stage 1 → Stage 2 is a config change |
| Queue | **Redis + arq**, separate queues per workload with concurrency limits | Customer requests never starved by batch jobs |
| LLM gateway | **LiteLLM**; code only calls logical names (`agent`, `parser`, `enrich`) | Routing, fallback, budgets |
| LLM providers, Stage 1 | **Groq and Gemini free tiers** (OpenRouter as extra fallback) | Development and anonymous use only (see privacy gate) |
| LLM providers, Stage 2 | **Local small model on the VPS (llama.cpp, GGUF)** for sub-tasks; main agent on a **paid no-training API** or an **open 7–14B model on serverless GPU (RunPod, vLLM)**, chosen by evals | OpenAI-compatible endpoints behind LiteLLM |
| Local LLM training | **LoRA fine-tuning (Unsloth) on Kaggle/Colab**; weights in a private Hugging Face repo; GGUF quantization | First target: the query-parsing model |
| Agent loop | **Own loop on LiteLLM tool calling** | Transparent and testable |
| Assistant UI | **Vercel AI SDK `useChat`** with the **UI message stream protocol** | FastAPI emits that protocol (`x-vercel-ai-ui-message-stream: v1`) |
| ASR | Stage 1: **Groq Whisper (free)**; Stage 2: **faster-whisper** on the VPS; custom Urdu ASR as research | Promotion by task success |
| Memory | **Own `MemoryProvider` (Postgres)**; Honcho as later experiment | Adopted only if better on correction, forgetting, relevance, privacy |
| Admin identity | **Individual admin accounts + audit** in M1 (simple, e.g. per-user credentials or OIDC via Google); **Keycloak** optional later | Accountability before AI approvals |
| Customer identity | Anonymous ID → Google / phone OTP login (M4) | Conservative merge |
| Observability | **OpenTelemetry → Grafana Cloud Free**; **Langfuse** for LLM traces | |
| ML tracking | **MLflow**; **DVC** with R2 remote | |
| Hosting, Stage 1 | **Current hosts** (inventoried in M1) + **managed free PostgreSQL** (Neon or Supabase) replacing Atlas | $0; free compute may sleep when idle |
| Hosting, Stage 2 | **One budget VPS** (Contabo Cloud VPS 20/30 or Hetzner CX33/CX43, chosen by benchmark) running Docker Compose | When budget allows |
| Kubernetes / GitOps | **k3s + Argo CD**, learned in a lab first; migrate when justified | One node = one failure domain |
| IaC | **OpenTofu** (Cloudflare, R2) + **Ansible** (server) | |
| Secrets | **SOPS + age** | |
| Edge | **Cloudflare** (DNS, CDN, TLS, R2 backups) | |
| CI/CD | **GitHub Actions + GHCR** | |

---

## 9. Target architecture

```
┌──────────────────────────── Next.js storefront ──────────────────────────────┐
│  /products  ── server-side search (shared service) ── variant-correct cards  │
│  /product/[slug] · cart (existing verification) · WhatsApp handoff + ref     │
│  Assistant panel (AI SDK useChat, UI message stream)                         │
│    • renders text, product cards, confirmations                              │
│    • executes validated UI actions once (action IDs, acknowledgements)       │
│  Voice input · event tracker (impressions, positions, clicks, actions)       │
│  "What the assistant remembers" page                                         │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ Cloudflare → reverse proxy
┌────────────────────────── FastAPI (modular monolith) ────────────────────────┐
│ catalog/     products, variants, attributes + provenance, vocabulary         │
│ search/      query parsing, exact variant filters, lexical + semantic, RRF   │
│ agent/       loop, tool registry, prompts (versioned), action validator      │
│ cart/        server-side validation shared with existing cart rules          │
│ enquiries/   references, WhatsApp message, staff outcomes                    │
│ memory/      MemoryProvider (Postgres), tombstones, consent                  │
│ identity/    admin users, customers (anon → login), sessions                 │
│ events/      impressions, positions, clicks, actions, outcomes               │
│ audit/       admin and agent write actions                                   │
│ core/        config, db, telemetry, rate limits, feature flags               │
└───────┬────────────────┬──────────────────┬───────────────────┬──────────────┘
        │                │                  │                   │
   PostgreSQL + pgvector (single database)    Redis                  LiteLLM (logical names)
   catalogue (products, variants,             queues: interactive    Stage 1 → Groq / Gemini free
   attributes + provenance), outbox,          / enrich / embed       Stage 2 → local llama.cpp (parser)
   embeddings, customers, memory, events,     / memory / asr                  + paid API or RunPod (agent)
   enquiries, audit                           concurrency-limited    EmbeddingProvider · SpeechProvider
                                  │
                ┌─────────────────┴──────────────────┐
                │ Workers (bounded, separate queues) │
                │ embed (reads outbox) · enrich ·    │
                │ memory · asr                       │
                └────────────────────────────────────┘

MLOps: evals/ (gates, "not evaluated" blocks) · MLflow · DVC (R2) · Kaggle · HF Hub
Obs  : OpenTelemetry → Grafana Cloud · Langfuse
Ops  : Stage 1: GitHub Actions → current hosts + Neon/Supabase Postgres
       Stage 2: GitHub Actions → GHCR → Compose on one VPS
       → k3s + Argo CD when justified · Cloudflare · OpenTofu + Ansible · SOPS
```

### 9.1 Architectural principles

1. **Hard constraints are enforced by code, never by the model.**
2. **The model proposes; application code decides** whether an action is valid and permitted.
3. **One search service** for browser and assistant, so both see the same truth.
4. **Every derived representation carries its source revision** (embeddings, memory). Filters always read live catalogue rows.
5. **Slow or CPU-heavy work runs in bounded workers** on separate queues.
6. **Everything degrades gracefully**: without the LLM, search and browsing still work.
7. **Provider-agnostic**: LLMs behind LiteLLM, memory behind `MemoryProvider`, hosting behind IaC.
8. **Evidence over claims**: every milestone records what was verified, where, and what wasn't.

### 9.2 Catalogue data architecture (ADR-002, accepted)

**The catalogue moves into PostgreSQL; MongoDB is removed after the switch.** Full decision, schema and switch-over steps: `docs/adr/002-consolidate-catalogue-into-postgresql.md`.

```
Staff / Quill change
   → one PostgreSQL transaction: products + variants + attribute_values + outbox row
   → embed worker reads outbox: retry, deduplicate by (id, revision), handle archive
   → product/variant embeddings (with source_revision, index_version)
Search → live products/variants rows (hard filters) + full-text/trigram + embeddings (ranking)
```

Why this design:

- **One source of truth and one transaction boundary.** A catalogue change and its "re-embed" record can't diverge.
- **No search projection, change-stream consumer or reconciliation job.** Filters read live rows, so an archived or out-of-stock variant is never shown as available. Only embeddings are derived; a stale embedding can change ranking order but never eligibility.
- **No Motor migration.** Motor is removed with MongoDB.
- **One backup/restore path.**
- **Nothing to migrate:** production MongoDB holds a single product, so this is a switch, not a migration.

Compatibility rules:

- **IDs preserved:** existing 24-character hex product and variant IDs become `CHAR(24)` primary keys; new IDs use the same format.
- **API contract unchanged:** response shapes, `_id`/`id`, `next_cursor` keyset pagination (`created_at DESC, id DESC`) and statuses stay identical, so the storefront, browser carts and the Quill panel need no changes.
- **Switch-over path:** archive the MongoDB data to R2 → build the PostgreSQL implementation behind the same API contract → re-create the one product with its existing IDs → verify in staging (incl. Quill) → deploy → remove Mongo, Motor and Atlas.

---

## 10. Detailed design

### 10.1 Catalogue attributes with provenance

| Field | Example | Allowed sources |
|---|---|---|
| `color_family` | `brown` | Visual suggestion → staff approval |
| `color_name` | `chocolate` | Visual suggestion → staff approval |
| `pattern` | `embroidered`, `plain`, `printed`, `jacquard` | Visual suggestion → staff approval |
| `fabric` / composition | `pashmina`, `70% wool / 30% silk` | **Supplier-declared or staff-confirmed only.** A photo cannot establish genuine pashmina, fibre composition or authenticity |
| `occasion`, `season`, `style_tags` | `wedding`, `winter`, `elegant` | Visual/text suggestion → staff approval |
| `description`, SEO text | — | AI draft → staff approval |

Every attribute value stores:

- `value` (or explicit `unknown`)
- `source`: `visual_suggestion` · `supplier_declared` · `staff_approved` · `imported`
- `approved_by`, `approved_at`, `model_version` (for suggestions)

**Target:** required fields complete, with **explicit unknowns where appropriate**. Never fill gaps with guesses.

A controlled vocabulary (`catalog/vocab.yaml`) is the single source of truth for filters, tool schemas and UI labels, including English, Urdu-script and Roman Urdu synonyms (e.g. `brown`: `bhoora`, `bhura`, `بھورا`, `chocolate`, `coffee`, `camel`).

### 10.2 Search service

**Constraint types**

| Type | Example | Behaviour |
|---|---|---|
| Hard | "under 4,000", "brown", "stole", "in stock", "not red" | Enforced exactly; **never relaxed automatically** |
| Soft | "around 4,000", "something elegant", "for a wedding" | Ranking signal; numeric soft values use a **disclosed** tolerance (default ±10%) |

**Pipeline**

1. **Parse** into hard and soft constraints (LLM tool arguments for the assistant; structured UI filters for the browser).
2. **Normalise** values against the vocabulary.
3. **Filter at variant level:** every hard condition must hold on the **same purchasable variant** (colour, price, stock, size). A product with a brown variant at 4,500 and a black variant at 3,500 does **not** match "brown under 4,000".
4. **Rank** eligible variants by reciprocal rank fusion of:
   - lexical relevance (Postgres full-text + trigram: names, SKUs, distinctive phrases),
   - semantic similarity (embeddings),
   - later, a personal boost from explicit preferences.
5. **Paginate server-side** with stable cursors.
6. **Live eligibility:** hard filters run on live `products`/`variants` rows in the same query, so status and stock are always current.
7. **Empty result:** return structured "near misses" (which hard constraint blocked what) so the UI or assistant can **ask** rather than relax.
8. **Log** query, parsed constraints, result IDs with **positions** (impressions), and later clicks.

### 10.3 Shopping assistant

**Loop:** LLM with tool calling via LiteLLM; maximum 6 steps per turn; per-turn timeout; streaming via the AI SDK UI message stream protocol.

**System prompt sections** (versioned in `agent/prompts/`): role and tone; language (reply in the customer's script: English, Urdu script or Roman Urdu); grounding (facts only from tools); constraint policy (never change hard constraints without asking); action policy (propose, never assume); personalisation policy.

**Backend tools (read-only unless stated)**

| Tool | Purpose |
|---|---|
| `search_products(hard, soft, sort, cursor)` | Shared search service |
| `get_product(slug)` | Details incl. variants and provenance |
| `check_stock(variant_id)` | Live stock |
| `find_similar(product_id)` | Similar items in the same embedding space |
| `get_profile()` | Explicit preferences (M4) |
| `remember_preference(...)` / `forget_preference(...)` | Memory writes, only on explicit customer request (M4) |

**UI actions (proposed by the model, validated by the app, executed once by the browser)**

| Action | Validation |
|---|---|
| `show_products(variant_ids)` | IDs exist, are published and match the last search result set |
| `open_product(slug, variant_id?)` | Exists and is published |
| `apply_filters(filters)` | Values from the vocabulary |
| `add_to_cart(variant_id, qty)` | **Existing cart rules** (price, stock, limits) via `cart/`; requires a **confirmation** |
| `start_whatsapp_order()` | **Existing cart verification and message builder**; adds enquiry reference; never declares an order confirmed |

**Action safety**

- Every action has an `action_id`. The browser acknowledges execution; replays after reconnection are ignored (no double add-to-cart).
- A confirmation is bound to the exact `variant_id` and `qty`, **expires** (e.g. 2 minutes), and becomes invalid if the proposed action changes.
- The model never supplies prices or stock; those come from the catalogue at execution time.
- Every action, acknowledgement and confirmation is logged with the trace ID.

**Conversation references:** "the second one" resolves against the **last displayed result set**, stored server-side per conversation.

### 10.4 Memory and personalisation

| Information | Example | Treatment |
|---|---|---|
| Explicit persistent preference | "Remember that I prefer plain designs" | Saved; shown on memory page; used in ranking |
| Session constraint | "My budget today is 4,000" | Conversation only; not persisted as a preference |
| Weak behavioural signal | Viewed three brown products | Low-weight ranking signal; decays; not stated back as fact |
| Purchase context | "This gift is for my mother" | Applies to this purchase only; does **not** make maroon Ayesha's preference |
| Deletion | "Forget my colour preference" | Deleted **and** prevented from being recreated |

**Deletion that sticks**

- Deleting writes a **tombstone** (key + timestamp) and bumps a per-customer `memory_version`.
- Queued extraction jobs check, before writing: memory still enabled? Input newer than the latest tombstone for that key? `memory_version` unchanged? Otherwise the job discards its result.
- Turning memory off stops extraction and hides stored items; "delete all" removes them.

**Anonymous identity**

- Anonymous memory belongs to a **browser**, not a verified person.
- On login, merge **conservatively**: show the customer what would be merged and let them accept; never merge into an account that already has conflicting preferences without asking; never merge across different logged-in accounts on a shared device.

**Recommendations ("anything new for me?")**

- Candidates from explicit preferences + newest/seasonal items, filtered by the same search service.
- Each suggestion carries a **reason** ("matches your saved preference for plain designs").
- Stage 2 (learned ranker) only after impressions, positions and outcomes have accumulated.

**Honcho** remains a later experiment behind `MemoryProvider`. It's adopted only if it beats the Postgres provider on the memory eval set for **correction, forgetting, relevance and privacy**, not on richer-looking summaries.

### 10.5 Staff assistant: catalogue enrichment

1. Staff uploads photos (and supplier details if available).
2. Vision model suggests colour family/name, pattern, style, occasion, and drafts description and SEO text.
3. Suggestions are validated against the vocabulary; fabric and composition fields are **not** filled from images.
4. The admin UI highlights missing required fields and shows provenance badges.
5. An individually identified staff member approves; approval is audited.
6. On approval, the change goes through the catalogue's durable change path, and the embedding worker updates the product.

This can deliver value **before** personalisation, because it saves staff time immediately.

### 10.6 Voice

- Customers **speak Urdu** (or English). Transcripts are rendered in **Urdu script or Roman Urdu**; the same search and assistant handle them.
- Baseline: faster-whisper (`small`, int8, CPU) in a bounded ASR worker; clips ≤ 30 s; text fallback always available.
- **Evaluation measures whether the shopping request survived:**
  - critical entities: prices ("4,000" must not become "14,000"), colours, categories, sizes;
  - negations ("not red");
  - final task success (did the resulting search satisfy the request?);
  - WER as a supporting metric.
- **Custom Urdu ASR** (e.g. EmbeddingGemma 2's audio encoder with a CTC head) is a **research experiment** with its own hypothesis, run on Kaggle, tracked in MLflow; promoted only if it beats the baseline on task success and critical-entity accuracy within CPU latency targets.
- Raw audio deleted after transcription by default.

### 10.7 Enquiries and outcomes

- Each WhatsApp handoff creates an **enquiry** with a short reference (e.g. `ES-7F3K`) included in the prefilled message, plus the cart snapshot and the session/conversation IDs.
- Staff can mark an enquiry `contacted`, `converted` or `lost` (with an optional reason) in the admin panel.
- This links recommendations and assistant sessions to real outcomes without building order management.

### 10.8 Internationalisation and accessibility

- Right-to-left rendering for Urdu script in the assistant panel and cards.
- PKR formatting; numerals handled consistently in both scripts.
- Keyboard navigation and screen-reader labels; voice always has a text alternative.
- Existing accessibility tests extended to new components.

---

## 11. Data model

One PostgreSQL database, managed by Alembic. The full catalogue DDL is in ADR-002.

```
-- Catalogue (source of truth; IDs are preserved 24-char hex)
products            id CHAR(24) · slug · name · category · status · cover_image_url · images
                    main_description · price_amount · currency · material · sizing · weight
                    item_number · revision · created_at · updated_at
                    search_tsv (generated tsvector) · trigram index on name
variants            id CHAR(24) · product_id · position · name · color (original text)
                    color_family · size · image_url · price_amount · currency · stock
                    description · is_active · revision
attribute_values    id · product_id · variant_id (nullable; not part of a primary key)
                    key · value (NULL = explicitly unknown)
                    source (visual_suggestion|supplier_declared|staff_approved|imported)
                    model_version · approved_by · approved_at

-- Embeddings (separate tables: no nullable column in a primary key)
product_embeddings  product_id · model_name · model_version · index_version · embedding (vector)
                    source_revision · PRIMARY KEY (product_id, model_version)
variant_embeddings  variant_id · model_name · model_version · index_version · embedding (vector)
                    source_revision · PRIMARY KEY (variant_id, model_version)

-- Change propagation
outbox              id · aggregate (product|variant) · aggregate_id · revision · event_type
                    created_at · processed_at · attempts · last_error

-- Customers and memory
customers           id · status (anonymous|registered) · memory_enabled · memory_version · created_at
customer_identities id · customer_id · provider (anon|google|phone) · subject · UNIQUE(provider, subject)
memory_items        id · customer_id · key · value · category (persistent) · source_message_id
                    created_at · updated_at
memory_tombstones   customer_id · key · deleted_at

-- Conversations and actions
conversations       id · customer_id · channel · prompt_version · model · index_version · started_at
messages            id · conversation_id · role · content · script (en|ur|roman_ur) · tokens · latency_ms
result_sets         id · conversation_id · variant_ids (ordered) · created_at     -- for "the second one"
tool_calls          id · message_id · tool · arguments · result_summary · status · duration_ms
ui_actions          action_id · conversation_id · type · payload · status
                    (proposed|confirmed|executed|rejected|expired) · confirmed_at · executed_at

-- Measurement and business loop
events              id · customer_id · session_id · type (search|impression|click|add_to_cart|
                    ui_action|voice|handoff) · payload (incl. positions, experiment arm) · created_at
enquiries           id · reference · customer_id · session_id · conversation_id · cart_snapshot
                    status (handed_off|contacted|converted|lost) · reason · updated_by · created_at
experiments         id · name · arms · started_at · ended_at
assignments         experiment_id · subject_id · arm · assigned_at

-- Jobs and audit
enrichment_jobs     id · product_id · status · output · model_version · prompt_version · reviewed_by
voice_jobs          id · customer_id · status · transcript · script · model_version · duration_ms
admin_users         id · email · role (owner|staff|viewer) · status
audit_log           id · actor_type · actor_id · action · target · before · after · created_at
```

**Migrations** follow expand/contract: add new columns/tables, backfill, switch reads, then remove old ones in a later release, so any single release can be rolled back.

**Retention:** raw audio deleted after transcription; events 18 months; conversations 12 months unless deleted by the customer; enquiries and audit log kept.

---

## 12. API and streaming design

All new endpoints under `/v1`; OpenAPI checked in CI with contract tests.

| Method & path | Purpose | Auth |
|---|---|---|
| `GET /v1/search` | Shared search (hard/soft constraints, cursor) | Public |
| `GET /v1/products/{slug}` | Product with variants and provenance | Public |
| `GET /v1/products/{slug}/similar` | Similar items | Public |
| `POST /v1/cart/validate` | Server-side cart validation (shared rules) | Public |
| `POST /v1/enquiries` | Create enquiry reference at handoff | Public (rate-limited) |
| `PATCH /v1/admin/enquiries/{id}` | Record outcome | Staff |
| `POST /v1/agent/chat` | Assistant turn (UI message stream) | Customer |
| `POST /v1/agent/actions/{action_id}/ack` | Browser acknowledges execution | Customer |
| `POST /v1/agent/actions/{action_id}/confirm` | Customer confirms a bound action | Customer |
| `POST /v1/voice` · `GET /v1/voice/{id}` | Voice upload and transcript | Customer |
| `GET/PATCH/DELETE /v1/me/memory[...]` | View, correct, delete memory | Customer |
| `POST /v1/me/memory/disable` | Turn memory off | Customer |
| `POST /v1/events` | Batched impressions, clicks, actions | Customer |
| `POST /v1/admin/enrichment/{product_id}` · `/approve` | Staff enrichment | Staff |

### 12.1 Agent stream

FastAPI emits the **Vercel AI SDK UI message stream protocol** over SSE with the header `x-vercel-ai-ui-message-stream: v1`, so `useChat` consumes it directly:

- Text parts for assistant prose.
- Tool parts (`tool-input-*`, `tool-output-available`) for backend tools.
- **Tool approval parts** (`tool-approval-request` / response) for confirmations such as `add_to_cart`.
- **Custom `data-*` parts** for UI actions, e.g. `data-ui-action` carrying `{action_id, type, payload}` and `data-products` carrying validated variant IDs.

The browser executes each `data-ui-action` at most once, acknowledges it, and ignores replays with a known `action_id`.

---

## 13. Models and AI cost

> Free-tier limits change often; figures were checked in October 2026 and must be rechecked before relying on them.

### 13.1 Agent LLM

| Option | Cost | Notes |
|---|---|---|
| Groq free tier | $0 | gpt-oss and Qwen-class models; reported ~1,000 requests/day per model. May retain data for a period. |
| Gemini API free tier | $0 | Flash/Flash-Lite free; low reported Flash limits. Free-tier data used to improve Google products and may be human-reviewed. |
| OpenRouter free models | $0 | Small daily cap. |
| Local small model (e.g. LFM2.5-2.6B) | $0 | Sub-tasks only (language/script detection, simple parsing). |
| Paid flash-class model | Traffic-based | Production with real customer data. |

**Policy**

- **Stage 1:** Groq/Gemini free tiers via LiteLLM for development and anonymous product search.
- **Before customer memory goes live (M4):** the agent must run on a **paid no-training model or a self-hosted model** ([privacy gate](#192-privacy)).
- **Stage 2:** local model for sub-tasks; agent on the model that wins the evals at acceptable latency and cost.
- Any model is adopted only after passing the agent, grounding and constraint evals.

### 13.2 Embeddings

- **Primary candidate: EmbeddingGemma 2.** It maps text, images (and audio, video) into one 768-dimensional space. Text + image only loads 440M parameters; dimensions can be truncated to 512/256 with little loss (128 degrades multimodal quality). On CPU it should run in `float32` (`float16` can produce NaN or degraded embeddings). It supports 100+ languages, but **Urdu performance must be measured**, not assumed.
- **Comparison:** separate text model + small SigLIP/CLIP-class image model.
- **Decision rule:** whichever wins on the retrieval eval set (incl. Urdu/Roman Urdu queries) within CPU latency budget.
- **Never compare vectors from different embedding spaces.** Each vector stores `model_version` and `index_version`; changing models means building a new index version and switching atomically.
- **Stage 1 (no server RAM for models):** product embeddings are computed in a batch job (GitHub Actions or Kaggle) and written to Postgres; query embeddings come from a free embedding API **only if it uses the same model**. Otherwise semantic ranking waits for Stage 2 and search runs on filters + lexical ranking, which already covers the golden journey.
- **Stage 2:** the chosen model runs on the VPS CPU behind `EmbeddingProvider`; switching creates a new `index_version`.

### 13.3 ASR

| Option | Stage | Cost |
|---|---|---|
| Groq Whisper (free tier) | Stage 1, development and anonymous use | $0 |
| faster-whisper `small` (CPU, int8) | Stage 2, on the VPS | $0 |
| Custom Urdu ASR experiment (Kaggle) | Research, any time | $0 |

### 13.4 Cost controls

- LiteLLM budgets per environment and per day; alert at 80%.
- Rate limits per customer and per IP on agent and voice endpoints.
- Token and step caps per turn.
- Cache identical normalised query parses.
- Cost per conversation in Langfuse and Grafana.

### 13.5 Local LLM track

Open model weights are downloaded free from Hugging Face and served with **llama.cpp, Ollama or vLLM**. All of these, plus Hugging Face's router and RunPod's vLLM worker, expose an **OpenAI-compatible API**, so they plug into LiteLLM without changing application code.

**Where models can run**

| Where | Fits | Cost (checked Oct 2026) | Use |
|---|---|---|---|
| Laptop (Ollama / llama.cpp) | Small models | $0 | Experiments, local development |
| Kaggle / Colab GPUs | Training and evaluation | $0 | Fine-tuning, benchmarking open models |
| VPS CPU (llama.cpp, GGUF, 4-bit) | 1.5–3B models (~2–3 GB RAM) | $0 extra | **Stage 2 sub-tasks:** query parsing, language/script detection, intent |
| RunPod serverless GPU (vLLM) | 7–14B models | 24 GB class ~$0.69/hr, billed per second, scales to zero; loading time is billed and adds first-request delay | **Stage 2 option** for the main agent at low traffic |
| Hugging Face Inference Endpoints | Any size | T4 $0.50/hr, L4 $0.70–0.80/hr, per minute (24/7 L4 ≈ $580/month) | Short experiments only |
| Hugging Face Inference Providers | Hosted open models | Free users: no credits; PRO: $2/month | Trying models quickly (not self-hosted) |

CPU expectations: reported generation speeds are around 20 tokens/s for 3B 4-bit models on a laptop CPU, slower for 4B+ and for long prompts. That suits short sub-tasks, not the main multi-step agent.

**Plan of work**

1. **Stage 1 (free):** benchmark open models on Kaggle and the laptop against the eval sets (constraint parsing, Urdu/Roman Urdu, tool calling).
2. **Fine-tune the query parser:** LoRA (Unsloth) on a 1.5–3B instruct model using the constraint-parsing dataset; track in MLflow; push to a private Hugging Face repo; quantize to GGUF; compare with the API model on the same evals.
3. **Stage 2:** serve the parser on the VPS with llama.cpp (CPU and memory capped, internal network only); route `parser` to it in LiteLLM.
4. **Optional:** serve a 7–14B open model on RunPod serverless for `agent`; adopt only if it passes agent, grounding and action-safety evals at acceptable latency and cost.

**Things to verify per model:** tool-calling support (chat template; llama.cpp needs `--jinja`), Urdu and Roman Urdu quality, RAM next to ASR and embeddings.

**Wiring (Stage 2 example)**

```yaml
# docker compose service
llm:
  image: ghcr.io/ggml-org/llama.cpp:server
  command: -m /models/parser-3b-q4_k_m.gguf --host 0.0.0.0 --port 8080 --ctx-size 4096 --threads 4 --jinja
  volumes: ["./models:/models:ro"]
  deploy: { resources: { limits: { cpus: "3", memory: 4g } } }
  networks: [internal]

# litellm config
model_list:
  - model_name: parser
    litellm_params: { model: openai/parser-3b, api_base: "http://llm:8080/v1", api_key: none }
  - model_name: agent
    litellm_params: { model: openai/qwen-14b-instruct, api_base: "https://api.runpod.ai/v2/<endpoint-id>/openai/v1", api_key: os.environ/RUNPOD_API_KEY }
  - model_name: agent-fallback
    litellm_params: { model: groq/openai/gpt-oss-120b, api_key: os.environ/GROQ_API_KEY }
router_settings:
  fallbacks: [{"agent": ["agent-fallback"]}]
```

---

## 14. Infrastructure and hosting

### 14.1 Hosting stages

| | **Stage 1: build (now)** | **Stage 2: self-host (when affordable)** |
|---|---|---|
| Frontend | Current host (Vercel) | Current host or the VPS behind Cloudflare |
| Backend + workers | Current host (Render) | VPS, Docker Compose |
| PostgreSQL + pgvector | **Neon Free or Supabase free** (replaces Atlas) | Postgres on the VPS |
| Redis | Small managed free tier or the backend host, only if needed in Stage 1 (queues can start as in-process tasks) | Redis on the VPS |
| Chat LLM | Groq / Gemini free tiers via LiteLLM | Local parser on the VPS; agent on paid API or RunPod serverless |
| Embeddings | Batch job for products; same-model API for queries, or lexical-only until Stage 2 | EmbeddingGemma 2 (or winner) on the VPS |
| Speech | Groq Whisper free | faster-whisper on the VPS |
| Cost | ~$0/month | ~$8–16/month VPS + optional GPU seconds |

**Stage 1 limits to accept:** free compute that sleeps when idle (first request slower), free-tier rate limits, Vercel Hobby being for non-commercial use, and the privacy gate before customer memory.

**Moving to Stage 2** is a checklist, not a rewrite:

- [ ] Provision VPS (Ansible), Cloudflare DNS (OpenTofu).
- [ ] Deploy the same images with Compose; restore Postgres from the latest R2 backup; verify counts.
- [ ] Point `DATABASE_URL`, LiteLLM routes, `EmbeddingProvider` and `SpeechProvider` at self-hosted services.
- [ ] Run all eval sets; switch traffic; keep Stage 1 services for a week as fallback.

### 14.2 Inventory what exists (M1)

Record for the current Vercel, Render, Atlas and staging setup: plan tier, region, limits, monthly cost, backups, who has access, and whether commercial use is allowed.

### 14.3 Stage 2 server choice: benchmark, then buy

Run the stack (API, workers, Postgres, Redis, embedding model, parser model, ASR) on a candidate server for a few days and measure memory, CPU, CPU steal, p95 latencies and embedding throughput before committing.

**Candidate servers** (prices checked late October 2026; treat as assumptions):

| Provider / plan | vCPU / RAM | Price / month | Notes |
|---|---|---|---|
| Contabo Cloud VPS 20 | 6 / 12 GB, 100 GB NVMe | ~$7.95 | Cheapest 12 GB; Singapore/Mumbai locations. Oversubscribed hosts, slower support, occasional IP-reputation issues. |
| Contabo Cloud VPS 30 | 8 / 24 GB, 200 GB NVMe | ~$14.95 | Upgrade path. |
| Hetzner CX33 | 4 / 8 GB, 80 GB NVMe | €8.49 + VAT + IPv4 | Better quality per price; EU only; limited availability. |
| Hetzner CX43 | 16 GB tier | €15.99 + VAT + IPv4 | EU only. |
| OVHcloud VPS-2 | 4 / 8 GB, 75 GB NVMe | €8.49 | Alternative. |
| DigitalOcean / Linode / Vultr | 4 / 8 GB | $40–48 | Too expensive for this budget. |

**Sizing guide:** ~8 GB with LLMs via API; **12 GB** with the local parser model and ASR; **16–24 GB** with Kubernetes and room to grow. Contabo VPS 20 (12 GB) is the starting candidate, with an in-place upgrade to VPS 30 (24 GB).

### 14.4 Services around the server

| Need | Choice |
|---|---|
| Storefront | Existing host or the server behind Cloudflare; confirm commercial-use terms |
| PostgreSQL + pgvector | Stage 1: Neon Free (1 GB storage, 100 CU-hours/project/month; compute suspends after 5 minutes idle) or Supabase free. Stage 2: on the VPS. Backups to R2 in both |
| Redis | Stage 2: on the VPS |
| MongoDB Atlas | Final archive to R2, then deleted (ADR-002) |
| CDN, DNS, TLS, object storage | Cloudflare + R2 |
| Observability | Grafana Cloud Free; Langfuse Cloud free tier |
| CI/CD, registry | GitHub Actions, GHCR |
| GPU experiments and fine-tuning | Kaggle, Colab |
| Serverless GPU (optional) | RunPod serverless (vLLM) |
| Model artifacts | Hugging Face Hub (private) |
| Kubernetes lab | k3d/kind on laptop; k3s on a staging server when justified |

### 14.5 Resource isolation

- Separate Redis queues: `interactive` (agent sub-tasks), `embed`, `enrich`, `memory`, `asr`.
- Per-queue concurrency limits and CPU limits (Compose `cpus`/`mem_limit`; later Kubernetes requests/limits).
- Batch jobs (re-embedding, enrichment) run with low priority and off-peak where possible.
- Customer-facing p95 latency is alerted on, so starvation is visible.

---

## 15. MLOps and LLMOps

### 15.1 Principles

1. **An AI release is a bundle:** prompt version + model + tool schemas + vocabulary + retrieval index version + configuration. All are versioned together.
2. **No release without evaluation.** An empty or missing eval set reports **"not evaluated"**, which **blocks** an AI release.
3. **Critical constraints are scored separately** from aggregate accuracy. One wrong price or stock claim fails the release regardless of averages.
4. **Promotion is earned:** offline eval → shadow → randomised canary → full rollout.
5. **Rollback restores the whole bundle**, including the previous index version; destructive schema changes use expand/contract.
6. **Production failures become eval cases.**

### 15.2 Evaluation sets

| Set | Checks | Gate |
|---|---|---|
| Constraint parsing | Requests → hard/soft constraints (English, Urdu script, Roman Urdu) | Hard constraints 100% on the critical subset; ≥ 90% overall |
| Variant correctness | Results always satisfy every hard constraint on the same variant | 100% |
| No silent relaxation | Empty-result cases → assistant asks instead of changing constraints | 100% |
| Retrieval quality | Queries → relevant variants | Recall@5 / nDCG@10 ≥ current baseline |
| Agent behaviour | Conversations → expected tool calls and proposed actions | ≥ 85% |
| Action safety | Invalid IDs, changed confirmations, replays, injected instructions | 0 unsafe executions |
| Grounding | Prices, stock, products only from tools | 0 violations |
| Memory | Save vs. don't save (persistent vs. session vs. context); forgetting sticks | Precision ≥ 90%; forgetting 100% |
| Enrichment | Suggestions vs. staff-approved; fabric never inferred from photos | ≥ baseline; 0 fabric inferences |
| Voice | Critical entities (prices, negations, category), task success, WER | Critical entities 100% on the critical subset; task success ≥ baseline |
| Latency | p95 first token, p95 search | Within SLO |

Deterministic checks wherever possible; LLM-as-judge only for subjective qualities, calibrated against human labels.

### 15.3 Tracking, registry and versions

- **MLflow:** runs, metrics, artifacts, registry with `champion`/`challenger` aliases.
- **DVC (R2 remote):** eval and training data versions.
- **Prompt registry:** `agent/prompts/` with semantic versions.
- **Index versions:** `index_version` on every vector and search document; new versions built side by side and switched atomically.
- **Release manifest:** `ai-release.yaml` lists all bundle versions; recorded on every conversation and trace.

### 15.4 Pipelines

| Pipeline | Trigger | Notes |
|---|---|---|
| Catalogue → embeddings | Outbox row written in the same transaction as the change | Idempotent by (id, revision); handles archive; retries with backoff |
| Embedding freshness check | Scheduled (hourly) | Finds rows whose embedding `source_revision` lags the catalogue `revision`; re-queues them |
| Index rebuild | Model or vocabulary change | Builds a new `index_version`; switch after eval |
| Enrichment | Upload | Suggestions only; approval required |
| Memory extraction | Conversation turn | Checks tombstones and `memory_version` before writing |
| Nightly eval | Schedule | Production bundle against all sets; alert on regression |
| ASR experiment | Manual | Research track; separate from production promotion |

Orchestration: arq cron + GitHub Actions; Dagster only when there are more than two scheduled pipelines.

### 15.5 Rollout and measurement

- **Shadow:** new bundle runs on replayed or live traffic without being shown.
- **Randomised assignment** for comparisons (assistant on/off, personalised vs. not) when traffic permits; customers who choose to use the assistant already differ from those who don't, so self-selected comparisons can't establish cause.
- **Impressions and positions** are logged for every result set, so later rankers know what was shown, not just what was clicked.
- **Outcomes** come from enquiries marked by staff.

### 15.6 Operator questions the system must answer

For any recommendation or action: the trace shows the customer/session, prompt version, model, index version, catalogue revisions, tool calls, proposed and executed actions, acknowledgements, cost, and the feature flag/experiment arm, and the release can be disabled or rolled back from one place.

---

## 16. DevOps and platform engineering

### 16.1 Environments

| Environment | Notes |
|---|---|
| `local` | Docker Compose (existing) |
| `staging` | Stage 1: existing staging + a Neon/Supabase branch or project. Stage 2: a Compose project or namespace on the VPS |
| `production` | Stage 1: current hosts + managed free Postgres. Stage 2: the VPS |

### 16.2 Configuration

- Backend: environment variables and secrets only.
- **Frontend:** move from build-time `NEXT_PUBLIC_*` to **runtime configuration** (server-provided config or same-origin API routing) before claiming one image can be promoted across environments.

### 16.3 CI/CD

1. **Pull request:** lint, typecheck, unit, contract and integration tests; **evals** for AI-touching changes; security scans (Trivy, CodeQL, gitleaks, dependency audit); build.
2. **Merge:** images tagged with the git SHA to GHCR (multi-arch); SBOM (Syft).
3. **Deploy (first AI release):** Compose on the server via the existing rollout/rollback scripts, extended with migrations (expand/contract) and smoke tests.
4. **Post-deploy:** smoke tests and live Playwright checks.

### 16.4 Kubernetes and GitOps (separate learning track)

- Learn k3s, Helm and Argo CD in a lab (k3d/kind or a staging server).
- Migrate production only when there's an operational reason (several independently deployed services, need for declarative rollouts).
- A single-node cluster still has one host failure domain; recovery remains the reliability strategy.

### 16.5 IaC and secrets

- OpenTofu for Cloudflare DNS, cache rules and R2; Ansible for server setup and hardening; SOPS + age for secrets.

### 16.6 Observability and SLOs

- OpenTelemetry in frontend, API and workers → Grafana Cloud; Langfuse for LLM traces; one trace ID from browser action to tool call.
- Dashboards: API, search, agent, workers/queues, infrastructure (incl. CPU steal on budget servers), cost.

| SLO | Target |
|---|---|
| Product page availability | 99.5% monthly |
| Search p95 | < 600 ms |
| Agent first token p95 | < 2.5 s |
| Voice transcript p95 | < 6 s for clips ≤ 15 s |
| Embedding freshness | 99% of catalogue changes re-embedded within 2 minutes (filters are always live) |

---

## 17. Engineering practices and evidence

- Trunk-based development, small PRs, conventional commits, semantic versioning.
- **ADRs** for significant decisions; **C4 diagrams** updated per milestone.
- PR template: what/why, screenshots, eval results, migration plan (expand/contract), rollback plan.
- **Definition of done:** tests and evals passing; telemetry added; docs/ADR updated; feature flag or graceful degradation in place; verified in staging.
- **Evidence discipline** (as in `docs/qa/2026-10-28-local-acceptance.md`): every milestone ends with an acceptance record stating what was verified, in which environment, with what data, and what was **not** covered.

---

## 18. Testing strategy

| Level | Tooling | Covers |
|---|---|---|
| Unit | pytest, Vitest | Parsers, vocabulary, constraint logic, action validator, memory rules |
| Property-based | Hypothesis | "Every result satisfies every hard constraint on the same variant" |
| Contract | OpenAPI + generated client; stream protocol fixtures | Backend ↔ frontend, incl. agent stream |
| Integration | pytest + Testcontainers (Postgres, Redis) | Search, outbox, embedding worker, migrations |
| Concurrency | Targeted tests | Action replay, expired confirmations, deletion vs. queued jobs |
| AI evals | `evals/` runner | [Section 15.2](#152-evaluation-sets) |
| E2E | Playwright (mocked + live) | Golden journey, memory page, admin enrichment, enquiry outcomes |
| Load | k6 | Search, agent, voice at expected peak ×3 |
| Accessibility | Existing tests extended | Assistant panel, cards, RTL |
| Recovery | Restore drill | Backups actually restore, including Postgres |

Live-model evals run on PRs touching agent, prompts, search or model config; other PRs use recorded responses.

---

## 19. Security, privacy and guardrails

### 19.1 Agent guardrails

- Allow-listed tools; schema-validated arguments.
- Model proposes; `agent/validator` checks every action against catalogue state, cart rules and permissions.
- Prices, stock and IDs only from tools/catalogue; never from model text.
- Action IDs, acknowledgements, bound and expiring confirmations.
- Product descriptions and customer messages are treated as data, never as instructions.
- Rate limits, token caps and step caps.

### 19.2 Privacy

- Memory only on explicit request or clearly disclosed weak signals; customer-visible memory page with correction, deletion and turn-off.
- Deletion enforced against queued jobs (tombstones, `memory_version`).
- Conservative anonymous-to-account merge.
- No personal data to free tiers that train on inputs.
- **Privacy gate before M4 goes live:** customer memory and personal conversations require the agent (and memory extraction) to run on a paid no-training model or a self-hosted model. Free tiers stay limited to development and anonymous product search.
- Raw audio deleted after transcription by default.
- Privacy policy updated for AI features; check current Pakistani data-protection requirements before launch.

### 19.3 Platform security

- Individual admin identities and audit before AI-assisted approvals; MFA for the owner.
- Secrets via SOPS; least-privilege database users; image and dependency scanning; server hardening via Ansible.

---

## 20. Reliability, backups and incidents

These come **before** customer memory and voice.

| Item | Target / practice |
|---|---|
| Off-server backups | PostgreSQL (`pg_dump`, custom format) nightly to R2, encrypted; 14 daily + 8 weekly. Existing Mongo backup scripts are replaced in M1 |
| Restore verification | Automated restore into a throwaway environment monthly; full drill quarterly; results recorded |
| RPO / RTO | 24 h / 4 h |
| Alerts | Availability, error rate, backup failure, disk, queue backlog, outbox backlog / embedding freshness, LLM budget |
| Release rollback | Previous images + previous AI release manifest + previous index version; expand/contract migrations |
| Graceful degradation | LLM down → search and browsing work. ASR down → text only. Vector search down → lexical + filters |
| Runbooks | LLM outage, quota exhaustion, bad AI release, outbox backlog, disk full, server suspended |
| Incidents | Severity levels, status note for major outages, blameless postmortems in `docs/postmortems/` |

---

## 21. Roadmap: milestones

Each milestone produces something usable even if work pauses there. Durations are **planning hypotheses** for part-time work.

### M1: Reliable catalogue (3–5 weeks, including the switch to PostgreSQL)

**Ship:** complete, correct browsing and filtering, plus recovery basics.

- [ ] Inventory existing environments (Vercel, Render, Atlas, staging, Quill) and record them.
- [x] **ADR-002 accepted:** consolidate the catalogue into PostgreSQL.
- [ ] Archive the MongoDB data (one product) encrypted to R2 and verify it restores.
- [ ] Postgres + pgvector in Compose and CI; Alembic schema from ADR-002; `CatalogRepository` (Postgres) behind the unchanged API contract; existing API tests pass.
- [ ] Stage 1 production and staging PostgreSQL on Neon or Supabase (free); confirm the `vector` and `pg_trgm` extensions are available; nightly `pg_dump` to R2.
- [ ] Seed script re-creating the product with its existing IDs (or re-enter via Quill).
- [ ] `EmbeddingProvider` and `SpeechProvider` interfaces alongside LiteLLM, so Stage 2 is a configuration change (ADR-017).
- [ ] Staging verification incl. Quill flows; acceptance record.
- [ ] Remove Mongo, Motor, `bson`, Mongo services/scripts/env vars; replace backup and restore drill with `pg_dump`-based versions; delete Atlas.
- [ ] Server-side `GET /v1/search` with cursor pagination; storefront uses it (fixes the 100-product limit).
- [ ] Variant-level hard filters: category, colour family, price range, size, in-stock; lexical search (full-text + trigram).
- [ ] Controlled vocabulary with multilingual synonyms; attribute model with provenance and explicit unknowns.
- [ ] Individual admin accounts with audit log (replacing the shared key for people).
- [ ] Enquiry references in the WhatsApp message; staff outcome marking.
- [ ] Impression and position logging for listings.
- [ ] Off-server backups to R2, automated restore verification, basic alerts, rollback procedure tested.
- [ ] Property-based tests for variant correctness; acceptance record.

**Done when:** the catalogue runs on PostgreSQL with Quill working and MongoDB removed; every published product is discoverable; "brown, under 4,000, in stock" returns only variants satisfying all three; a restore from R2 succeeds; an enquiry reference flows from cart to WhatsApp to a staff outcome.

### M2: Useful intelligence (3–4 weeks)

**Ship:** multilingual search and staff enrichment with measurable quality.

- [ ] Labelled eval sets: constraint parsing (English, Urdu script, Roman Urdu), variant correctness, retrieval quality.
- [ ] Embedding benchmark: EmbeddingGemma 2 (shared space) vs. separate models → ADR-008.
- [ ] Semantic ranking with pgvector; reciprocal rank fusion with lexical; `index_version`.
- [ ] Natural-language query parsing into hard/soft constraints (also usable from the search box).
- [ ] Staff enrichment: suggestions with provenance, no fabric from photos, approval and audit.
- [ ] Bounded worker queues; OpenTelemetry + Langfuse; eval runner with "not evaluated" blocking.

**Done when:** search quality is measured against a baseline and improved; staff publish products faster with provenance recorded.

### M3: Shopping assistant (3–5 weeks)

**Ship:** the golden journey through the assistant.

- [ ] Agent loop, tool registry, versioned prompts, AI release manifest.
- [ ] FastAPI emitting the AI SDK UI message stream; `useChat` panel with RTL support.
- [ ] Actions: `show_products`, `open_product`, `apply_filters`, `add_to_cart` (existing cart rules, bound confirmation), `start_whatsapp_order` (existing verification + enquiry reference).
- [ ] Action IDs, acknowledgements, replay protection, expiring confirmations; "the second one" via stored result sets.
- [ ] Graceful degradation; feature flag; randomised assignment where traffic allows.
- [ ] Eval sets: agent behaviour, action safety, grounding, no silent relaxation.

**Done when:** "brown stole under 4,000" → correct in-stock variant → verified cart → WhatsApp enquiry → recorded outcome works end to end in English and Urdu, with zero grounding and action-safety violations.

### M4: Returning-customer experience (3–4 weeks)

**Ship:** explicit memory with real control and explainable suggestions.

- [ ] Anonymous ID; Google / phone OTP login; conservative merge.
- [ ] `MemoryProvider` (Postgres): persistent preferences, session constraints, purchase context, weak signals.
- [ ] Tombstones and `memory_version` enforced in queued jobs.
- [ ] Memory page: view, correct, delete, turn off.
- [ ] "Anything new for me?" with reasons; impressions logged; randomised comparison.
- [ ] Memory eval set (saving, not saving, forgetting).
- [ ] **Privacy gate passed:** agent and memory extraction on a paid no-training or self-hosted model before real customers use memory.

**Done when:** a returning customer gets explained suggestions from explicit preferences, and corrections and deletions demonstrably stick.

### M5: Voice (3–5 weeks + optional research)

**Ship:** measured speech input on the same journey.

- [ ] faster-whisper ASR worker (bounded); mic input with text fallback.
- [ ] Voice eval set: critical entities, negations, task success, WER.
- [ ] Transcript script handling (Urdu script / Roman Urdu) into the same parser.
- [ ] Audio retention job.
- [ ] *(Research, optional)* custom Urdu ASR experiment with a written hypothesis, MLflow tracking and promotion criteria.

**Done when:** spoken Urdu requests complete the golden journey with 100% critical-entity accuracy on the critical subset.

### Track L: Local LLMs (parallel, from M2; $0 until Stage 2)

- [ ] Benchmark open models (1.5–14B) on Kaggle/laptop against constraint-parsing, Urdu/Roman Urdu and tool-calling evals; record results.
- [ ] Fine-tune a 1.5–3B query-parser model with LoRA (Unsloth) on Kaggle; MLflow tracking; DVC data; private Hugging Face repo.
- [ ] Quantize to GGUF; run with llama.cpp on the laptop; compare with the API model on the same evals.
- [ ] Model card and promotion decision (champion/challenger).
- [ ] *(Stage 2)* Serve the parser on the VPS; route `parser` in LiteLLM.
- [ ] *(Stage 2, optional)* 7–14B open model on RunPod serverless for `agent`, adopted only if it passes the evals.

**Done when:** a self-trained model either beats or is shown not to beat the API model on the parsing evals, with the evidence recorded, and is ready to serve.

### M6: Operational maturity and Stage 2 move (ongoing; can overlap from M2)

- [ ] Runtime frontend configuration; one image promoted across environments.
- [ ] Stage 2: benchmark and buy the VPS; Ansible + OpenTofu; SOPS; run the move checklist ([14.1](#141-hosting-stages)).
- [ ] SLO dashboards and alerts; nightly evals; drift report; k6 load tests.
- [ ] k3s + Helm + Argo CD in a lab; production migration only with an ADR showing why.
- [ ] Runbooks and postmortem template; quarterly restore drills.

**Done when:** deployments are reproducible, recovery is tested, AI releases are versioned and reversible, and infrastructure changes are justified by ADRs.

### Later / optional

- Honcho experiment behind `MemoryProvider`.
- Learned ranker (needs impressions, positions and outcomes).
- Admin copilot for staff.
- Voice replies (TTS); virtual try-on demo (GPU, showcase only).

### Timeline hypothesis

| Milestone | Weeks (part-time) |
|---|---|
| M1 Reliable catalogue (incl. switch to PostgreSQL) | 3–5 |
| M2 Useful intelligence | 3–4 |
| M3 Shopping assistant | 3–5 |
| M4 Returning customers | 3–4 |
| M5 Voice | 3–5 (+ research) |
| Track L Local LLMs | Parallel from M2 (~3–5 weeks of effort) |
| M6 Operational maturity + Stage 2 move | Ongoing, overlapping; Stage 2 when budget allows |

Roughly 15–23 weeks for M1–M5, revisited at the end of each milestone.

---

## 22. Postponed tracks

### 22.1 CRM

Builds on `customers`, `conversations`, `events` and `enquiries`: timelines, tags, segments.

### 22.2 WhatsApp Business Platform

- Today's `wa.me` link gives the app no visibility into conversations; the enquiry reference is the bridge until then.
- Use the Meta Cloud API directly when ready; customer-initiated messages aren't charged, and free-form replies and utility templates within the 24-hour customer service window are free.
- Coexistence allows the same number on the WhatsApp Business app and the API (Business app required, eligibility rules, app opened at least every 13 days).
- Later: webhook → enquiry/customer timeline → voice notes → the same ASR and assistant (`channel = whatsapp`) → draft order for staff approval.

### 22.3 Orders

Captured orders with a state machine, inventory reservation and idempotency; cash on delivery first; payment providers behind an interface later.

### 22.4 Data platform and market intelligence

dlt → DuckDB/ClickHouse → dbt → Dagster → Metabase/Superset; competitor and pricing sources; forecasting and co-purchase recommendations once confirmed sales history exists.

---

## 23. Budget

All figures are **assumptions** until the inventory ([14.2](#142-inventory-what-exists-m1)) and benchmark ([14.3](#143-stage-2-server-choice-benchmark-then-buy)) are done.

| Item | Stage 1 (now) | Stage 2 (when affordable) |
|---|---|---|
| Hosting | $0 (current hosts; confirm their plans) | VPS ~$8 (12 GB) to ~$16 (16–24 GB)/month |
| PostgreSQL | $0 (Neon/Supabase free) | Included in VPS |
| Chat LLM | $0 (Groq/Gemini free) | Local parser $0; agent: small paid API budget, or RunPod GPU seconds (~$10–15/month at ~200 conversations/day, illustrative) |
| Embeddings, ASR | $0 (batch job; Groq Whisper free) | $0 (self-hosted) |
| Model training | $0 (Kaggle/Colab) | $0 |
| Backups (R2) | Likely within free allowance; confirm | Same |
| Domain | Existing or ~$10–15/year | Same |
| Phone OTP | Only if phone login is used; Google login is free | Same |
| Cloudflare, Grafana Cloud, Langfuse, GitHub | $0 | $0 |
| Headroom | — | ~20% above the sum |

**Required spend before M4 goes live:** the privacy gate needs either a paid no-training API (small, capped) or Stage 2 self-hosting.

---

## 24. Success metrics and measurement

| Area | Metric | Notes |
|---|---|---|
| Catalogue | % published products discoverable via search | Target 100% |
| Catalogue | Required fields complete (with explicit unknowns) | Target 100%; no guessed values |
| Catalogue | Time to publish a product | Before vs. after enrichment |
| Search | Zero-result rate; search → product view rate | vs. M1 baseline |
| Search | Hard-constraint violations | 0 |
| Assistant | Golden-journey success rate (evals) | ≥ 85% overall; 100% on critical constraints |
| Assistant | Thumbs-up rate | ≥ 70% of rated turns |
| Business loop | Enquiries with recorded outcome | ≥ 80% marked within 7 days |
| Business loop | Conversion (converted / handed off) | Randomised arms when traffic permits |
| Personalisation | CTR and conversion on suggestions vs. control | Randomised; impressions-based |
| Voice | Critical-entity accuracy; task success; WER | Per model version |
| Reliability | SLO attainment; restore drill success | Recorded |
| Cost | Monthly spend vs. budget | Including LLM |

---

## 25. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Switch to PostgreSQL breaks Quill or the storefront | Low | Medium | Same API contract and ID format; existing API tests; Quill flows verified in staging; archived MongoDB data |
| Embeddings lag catalogue changes | Medium | Low | Outbox in the same transaction; freshness check; filters always live, so lag affects ranking only |
| Hard constraint violated by ranking or the model | Medium | High | Variant-level filtering in code; property tests; 100% gate |
| Assistant action duplicated or applied to the wrong item | Medium | High | Action IDs, acknowledgements, bound expiring confirmations, existing cart rules |
| Memory recreated after deletion | Medium | High | Tombstones and `memory_version` checks in jobs |
| Fabric or authenticity misstated | Medium | High | Provenance; fabric only from supplier/staff; unknowns allowed |
| Free LLM tiers change or train on data | High | Medium | LiteLLM fallbacks; privacy gate before memory; self-hosted models in Stage 2 |
| Stage 1 free hosts sleep or hit limits | High | Low | Accept during build; warm-up pings only where terms allow; Stage 2 move checklist ready |
| Local models too weak for the agent | Medium | Low | Use them for sub-tasks; agent model chosen by evals; paid API or serverless GPU fallback |
| Stage 2 VPS RAM too small for local models + ASR | Medium | Medium | Benchmark before buying; caps per service; in-place upgrade to 24 GB |
| Urdu quality (embeddings or ASR) insufficient | Medium | Medium | Measured in evals; text fallback; research track separate |
| Budget server slowdowns | Medium | Medium | Bounded queues, caching, alerts, benchmark before choosing |
| Rollback can't undo data changes | Medium | High | Expand/contract migrations; index versions; restore drills |
| Misleading success metrics | Medium | Medium | Impressions, enquiry outcomes, randomised assignment |
| Scope creep / burnout | High | High | Golden journey first; each milestone usable alone; ADR before new tools |

---

## 26. Repository structure

```
apps/
  frontend/                  # storefront, assistant panel, memory page, admin
  backend/
    app/
      catalog/               # products, variants, attributes + provenance, vocab.yaml
      search/                # parsing, variant filters, lexical, semantic, fusion
      agent/                 # loop, tools/, prompts/, validator/, stream/ (AI SDK protocol)
      cart/                  # server-side validation shared with existing rules
      enquiries/
      memory/                # MemoryProvider, postgres/, tombstones
      identity/
      events/
      audit/
      core/
    workers/                 # embed (outbox), enrich, memory, asr (separate queues)
    scripts/                 # seed_catalog.py, import_legacy_catalog.py
    migrations/              # Alembic (expand/contract)
    tests/
evals/
  datasets/                  # constraint, variant, retrieval, agent, action-safety,
                             # grounding, memory, enrichment, voice (DVC)
  thresholds.yaml
  run_evals.py
ml/
  embeddings_benchmark/
  llm_benchmark/             # open-model comparisons on the eval sets
  parser_finetune/           # LoRA training (Kaggle), GGUF export, model card
  asr_research/
ai-release.yaml              # prompt, model, tools, vocab, index versions
docs/
  adr/ · architecture/ · qa/ · postmortems/ · PLAN.md
deploy/
  compose/ (incl. llm service, Stage 2) · litellm/ (config per stage)
  ansible/ · tofu/ · helm/ (lab) · argocd/ (lab)
.github/workflows/
```

---

## 27. Architecture decision records

| ADR | Decision | Milestone |
|---|---|---|
| 001 | Modular monolith with bounded workers | M1 |
| 002 | **Consolidate the catalogue into PostgreSQL** (accepted 2026-10-29; `docs/adr/002-consolidate-catalogue-into-postgresql.md`) | M1 |
| 003 | Shared search service; hard vs. soft constraints; no automatic relaxation | M1 |
| 004 | Attribute provenance and explicit unknowns | M1 |
| 005 | Individual admin identity and audit (Keycloak optional) | M1 |
| 006 | Enquiry references and staff-recorded outcomes | M1 |
| 007 | Backups, restore verification and rollback policy | M1 |
| 008 | Embedding model choice (shared multimodal vs. separate) and index versioning | M2 |
| 009 | AI release bundle and eval gating ("not evaluated" blocks) | M2 |
| 010 | LiteLLM gateway and provider policy | M2 |
| 011 | Agent actions: propose/validate, idempotency, confirmations | M3 |
| 012 | AI SDK UI message stream protocol from FastAPI | M3 |
| 013 | Memory categories, deletion semantics and anonymous merge | M4 |
| 014 | Voice evaluation (critical entities, task success) and ASR baseline | M5 |
| 015 | Stage 2 VPS choice from benchmark; Compose → Kubernetes criteria | M6 |
| 017 | Hosting stages and provider interfaces (LLM, embeddings, speech); privacy gate | M1 |
| 018 | Local LLM serving (llama.cpp/vLLM), fine-tuning workflow and promotion criteria | Track L |
| 016 | Frontend runtime configuration for image promotion | M6 |

Template: **Context → Decision → Alternatives → Consequences → Status → Evidence.**

---

## 28. Learning outcomes and portfolio deliverables

| Milestone | Skills | Deliverable |
|---|---|---|
| M1 | Data modelling, search, consistency, backups, ADRs | "Fixing the foundation before adding AI": ADR-002 write-up, variant-correctness tests, restore evidence |
| M2 | Embeddings, hybrid retrieval, eval design, provenance | Embedding benchmark (incl. Urdu) and before/after search metrics |
| M3 | Agents, tool calling, stream protocols, action safety | Golden-journey video; action-safety eval report |
| M4 | Memory systems, privacy by design, experimentation | "Memory that forgets properly": design + eval results |
| M5 | Speech, evaluation beyond WER, research method | Voice eval report; optional ASR research note |
| Track L | Open models, LoRA fine-tuning, quantization, serving, model evaluation | "Fine-tuning a small model to replace an API call": benchmark, model card, cost/latency comparison |
| M6 | IaC, observability, SRE, Kubernetes/GitOps, migration to self-hosting | Operator dashboard answering "why did this happen?"; Stage 2 move write-up |

---

## 29. Resource triage (models and repos)

### Use

| Resource | Use for |
|---|---|
| EmbeddingGemma 2 (+ ONNX variants), sentence-transformers | Shared text/image embeddings (benchmark first); audio encoder for ASR research |
| Qwen3-VL-Embedding | Offline comparison only (GPU) |
| LFM2.5-2.6B, tiny-aya | Local sub-tasks after testing Urdu/Roman Urdu |
| embed2asr and EmbeddingGemma-2 ASR repos, ep-hindi-asr | ASR research references |
| SAM 3.1 | Product photo segmentation in enrichment |
| Qwen-Image-Edit + opentryon | Try-on showcase (GPU demo only) |
| pipecat, huggingface/speech-to-speech | Future voice agent |
| MemPalace | Compare with Honcho later |

### Skip

| Resource | Why |
|---|---|
| Flux-Uncensored, Qwen-Image Turbo Uncensored | Not useful for a storefront; brand risk |
| DeepSeek-V3.1, Grok-2, Qwen3.5-35B, DeepSeek-Math-V2 | Too large to self-host; not needed |
| Hunyuan3D, ActionMesh, Magma | Unrelated |
| Phi-lthy4, Phi-Line_14B | Roleplay fine-tunes |
| VibeVoice, whistle, neudecide, taiga-s1, anime image models | Not relevant now |

---

## 30. Glossary

| Term | Meaning |
|---|---|
| **Hard constraint** | A requirement that must hold exactly (max price, colour, stock) |
| **Soft constraint** | A preference used for ranking ("around", "elegant") |
| **Variant** | A purchasable version of a product (colour, size, price, stock) |
| **Provenance** | Where an attribute value came from and who approved it |
| **Outbox** | A table of change records written in the same transaction as the data change, processed by workers |
| **Reciprocal rank fusion (RRF)** | Combining several rankings into one |
| **Index version** | Version label for a set of embeddings/search documents built together |
| **AI release bundle** | Prompt + model + tools + vocabulary + index + config versioned together |
| **Tombstone** | A record that something was deleted, so it isn't recreated |
| **Critical entity** | A value that must be exactly right (price, negation, category) |
| **Impression** | A product shown to a customer, with its position |
| **Expand/contract** | Migration pattern that keeps every release reversible |
| **WER** | Word error rate for speech recognition |
| **GGUF** | File format for quantized models run by llama.cpp/Ollama |
| **Quantization** | Storing weights at lower precision (e.g. 4-bit) so models fit in less memory and run faster |
| **LoRA** | Fine-tuning method that trains small adapter weights instead of the whole model |
| **Serverless GPU** | GPU workers that start on demand and bill per second, scaling to zero when idle |
| **Stage 1 / Stage 2** | Build on current hosts and free tiers / move to a VPS and self-hosted models |

---

## 31. References

**Repository (commit `23e33e2`)**

- `apps/frontend/src/lib/api.ts`, `components/product/ProductBrowser.tsx`, `components/cart/CartPage.tsx`, `docs/qa/2026-10-28-local-acceptance.md`

**AI and search**

- [EmbeddingGemma 2 model card — Google AI for Developers](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)
- [AI SDK UI stream protocol — ai-sdk.dev](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
- [Honcho (Plastic Labs) review — DEV Community](https://dev.to/andrew-ooo/honcho-review-plastic-labs-agent-memory-layer-2026-2kb4)
- [Gemini API pricing changes and free alternatives — agentdeals.dev](https://agentdeals.dev/gemini-api-pricing-changes)

**Local and open models**

- [Hugging Face Inference Endpoints pricing](https://huggingface.co/docs/inference-endpoints/pricing)
- [Hugging Face Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)
- [RunPod pricing](https://www.runpod.io/pricing)
- [RunPod Serverless pricing docs](https://docs.runpod.io/serverless/pricing)
- [Running LLMs on CPUs: practical guide and benchmarks](https://putty-p.it.com/a/26676.html)

**Databases**

- [Neon free plan limits and quotas](https://neon.com/faqs/free-plan-limits-and-quotas)

- [Migrating from Motor to PyMongo Async — MongoDB Docs](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)

**Hosting and infrastructure**

- [Is Hetzner still the cheapest VPS? 24 alternatives priced (Oct 2026) — DEV Community](https://dev.to/hostingsift/is-hetzner-still-the-cheapest-vps-we-priced-24-alternatives-october-2026-271g)
- [Hetzner price adjustment, 15 June 2026 — Hetzner Docs](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- [Contabo VPS review 2026 — learnwithhasan](https://learnwithhasan.com/vps-providers/contabo-vps/)
- [16 GB RAM VPS comparison (Oct 2026) — stackrates](https://stackrates.ai/vps/16gb-ram/)
- [Grafana Cloud Free tier](https://grafana.com/products/cloud/free-tier)
- [Hugging Face Spaces overview](https://huggingface.co/docs/hub/spaces-overview)

**WhatsApp (postponed track)**

- [WhatsApp Business Platform pricing — Meta](https://developers.facebook.com/docs/whatsapp/pricing)
- [WhatsApp Coexistence — 360dialog docs](https://docs.360dialog.com/docs/hub/embedded-signup/whatsapp-coexistence)
