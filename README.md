# Elegance Shawls

[Portfolio case study](https://hamza-khan-portfolio.hamzakhan102003.chatgpt.site/projects/elegance-shawls/) · [Author portfolio](https://hamza-khan-portfolio.hamzakhan102003.chatgpt.site/) · [LinkedIn](https://www.linkedin.com/in/muhammadhamzakhan/)

[![Main Branch](https://img.shields.io/badge/branch-main-111827?style=flat-square)](https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/tree/main)
[![Frontend](https://img.shields.io/badge/frontend-Next.js_16-000000?style=flat-square&logo=next.js)](./apps/frontend)
[![Backend](https://img.shields.io/badge/backend-FastAPI-05998b?style=flat-square&logo=fastapi)](./apps/backend)
[![Database](https://img.shields.io/badge/database-PostgreSQL-336791?style=flat-square&logo=postgresql&logoColor=white)](./apps/backend)
[![Ordering](https://img.shields.io/badge/orders-WhatsApp-25D366?style=flat-square&logo=whatsapp&logoColor=white)](./apps/frontend)
[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)](./.github/workflows/ci.yml)

Production-grade e-commerce platform for shawls and stoles, built around a modern customer storefront, a FastAPI product service, and WhatsApp-first ordering.

This repository contains the customer-facing storefront and the backend product API that powers catalogue discovery, product detail pages, stock-aware selection, and order handoff to WhatsApp.

## At a glance

- *Storefront:* Next.js customer experience for browsing and order handoff
- *API:* FastAPI product service with authenticated admin write routes
- *Database:* PostgreSQL (required); the sole source of truth for the catalogue and ingestion
- *Ordering model:* WhatsApp-first purchase intent flow
- *Ops posture:* health checks, readiness checks, CI, deployment docs, and operations runbooks

## Quick links

- [Architecture overview](#architecture-overview)
- [Local development setup](#local-development-setup)
- [Verification commands](#verification-commands)
- [Docker-based deployment](#docker-based-deployment)
- [Production operations](#production-operations)
- [Contributing](./CONTRIBUTING.md)

## Why this repo exists

Elegance Shawls is designed for a real retail workflow where the public storefront must stay fast, catalogue updates must be controlled, and production operations must be documented beyond just `npm run dev`.

This README is written for:
- developers onboarding to the codebase
- operators preparing a deployment
- collaborators trying to understand system boundaries quickly
- future maintainers who need setup, verification, and production references in one place

## What’s inside

### Applications
- `apps/frontend` — Next.js storefront for browsing products and sending order intent to WhatsApp
- `apps/backend` — FastAPI + PostgreSQL product API with public catalogue routes and authenticated admin product management routes

### Production docs
- `DEPLOYMENT.md` — production environment and rollout requirements
- `OPERATIONS.md` — health, backup, restore, monitoring, and incident-response guidance
- `LAUNCH_RUNBOOK.md` — launch gates and end-to-end acceptance checks
- `plans/` — all system and store plans (start with `plans/README.md`)
- `docs/phase-1-one-source-ingestion.md` — staged product ingestion design, states and security rules

## Core capabilities

### Storefront
- product catalogue browsing
- product detail pages by slug
- WhatsApp-first order handoff
- environment-backed public site and API configuration
- storefront health and readiness probes
- frontend typechecking, linting, unit tests, and Playwright E2E coverage

### Backend API
- public product listing with cursor pagination
- public product lookup by slug
- authenticated product creation, update, publish/unpublish, stock updates, and archive
- PostgreSQL-backed persistence (SQLAlchemy/asyncpg, Alembic migrations)
- CORS configuration via environment
- readiness checks for database connectivity
- request rate limiting middleware

## Architecture overview

```text
Customer Browser
   |
   v
Next.js Storefront (apps/frontend)
   |
   v
FastAPI Product API (apps/backend)
   |
   v
PostgreSQL

Admin operations are authenticated per individual account: the Next.js server signs the admin in and forwards an opaque `X-Admin-Session` token; the browser never calls the backend admin routes. Mutations are role-checked and audited.
Customer order completion happens through WhatsApp handoff from the storefront.
```

## Tech stack

### Frontend
- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4
- Vitest
- Playwright

### Backend
- FastAPI
- Python 3.11
- SQLAlchemy 2 (async) / asyncpg / Alembic
- Pydantic v2
- PostgreSQL 17 + pgvector
- Pytest

### Delivery / ops
- Docker / Docker Compose
- GitHub Actions CI

## Repository structure

```text
Elegance-Shawls/
├── apps/
│   ├── frontend/
│   │   ├── src/
│   │   ├── __tests__/
│   │   ├── e2e/
│   │   ├── package.json
│   │   └── .env.example
│   └── backend/
│       ├── configuration/
│       ├── database/
│       ├── models/
│       ├── routes/
│       ├── schemas/
│       ├── security/
│       ├── tests/
│       ├── main.py
│       ├── requirements.txt
│       └── .env.example
├── compose.yaml
├── DEPLOYMENT.md
├── OPERATIONS.md
├── LAUNCH_RUNBOOK.md
└── README.md
```

## Quick start

### Prerequisites
- Node.js 22 recommended for parity with CI
- npm
- Python 3.11
- PostgreSQL 17 (required; local via `compose.ai.yaml`)
- Git

## Local development setup

### 1) Clone the repository

```bash
git clone https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls.git
cd Elegance-Shawls
```

### 2) Configure environment files

#### Frontend
Copy `apps/frontend/.env.example` to `apps/frontend/.env`:

```bash
cp apps/frontend/.env.example apps/frontend/.env
```

Frontend environment variables:

| Variable | Purpose | Example |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Public base URL for the backend API | `http://localhost:8000` |
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | WhatsApp destination in international digits | `923001234567` |
| `NEXT_PUBLIC_SITE_URL` | Canonical storefront URL | `http://localhost:3000` |

#### Backend
Copy `apps/backend/.env.example` to `apps/backend/.env`:

```bash
cp apps/backend/.env.example apps/backend/.env
```

Backend environment variables:

| Variable | Purpose | Example |
|---|---|---|
| `DATABASE_URL` | **Required.** PostgreSQL connection string (run `alembic upgrade head` first) | `postgresql+asyncpg://elegance_app:...@localhost:5432/elegance_shawls` |
| `ALLOWED_ORIGINS` | Comma-separated allowed storefront origins | `http://localhost:3000` |
| `ADMIN_API_KEY` | **Legacy** shared key (`X-Admin-Key`); ignored unless `ADMIN_LEGACY_KEY_EXPIRES_AT` is a future instant. Leave empty once admin accounts exist | empty |
| `ADMIN_LEGACY_KEY_EXPIRES_AT` | ISO 8601 instant with offset after which the legacy key stops working (no redeploy needed) | `2026-12-31T00:00:00+00:00` |
| `ADMIN_SESSION_TTL_SECONDS`, `ADMIN_LOGIN_MAX_FAILURES`, `ADMIN_LOGIN_LOCKOUT_SECONDS` | Admin session lifetime (8h), failed sign-ins before lockout (5) and lockout length (15 min) | `28800`, `5`, `900` |
| `ENVIRONMENT` | Runtime environment label | `development` |
| `PUBLIC_RATE_LIMIT_PER_MINUTE` | Public route request limit | `120` |
| `ASSISTANT_CATALOGUE` | `true` makes `/v1/assistant/stream` answer from the live catalogue (parser + search); default is the scripted demo | `false` |
| `ADMIN_RATE_LIMIT_PER_MINUTE` | Admin route request limit | `60` |

### 3) Start the backend

```bash
cd apps/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

### 4) Start the frontend

Open a second terminal:

```bash
cd apps/frontend
npm ci
npm run dev
```

Storefront will be available at:
- `http://localhost:3000`

Backend will be available at:
- `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

## Verification commands

### Frontend
```bash
cd apps/frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

### Backend
```bash
cd apps/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
python -m compileall -q .
```

## One-command local store

From `apps/backend` with the venv active and `npm ci` done in `apps/frontend`:

```bash
ADMIN_ACCOUNT_PASSWORD='choose-a-long-passphrase' bash scripts/dev_local.sh
```

Set `LOCAL_ENV_FILE=/path/to/apps/backend/.env` to also load provider keys, `LLM_CHAIN_DEFAULT` (turns on LLM wording) and the `CUSTOMER_AUTH_*` Google values (the frontend client id is taken from `CUSTOMER_AUTH_AUDIENCE`).

Starts a pgvector Postgres container (data kept in a docker volume), runs migrations, creates the owner account (`owner@elegance.local`), seeds a synthetic 36-product catalogue (`scripts/seed_local.py`, development only), then runs the API on :8000 (CORS allows `localhost`/`127.0.0.1` on :3000 and :3001, because Next moves to 3001 when 3000 is busy) and the storefront with the assistant enabled (`NEXT_PUBLIC_ASSISTANT_ENABLED=1`).

### Semantic search, assistant wording, voice and customer sign-in (all optional)

- **Semantic search.** `pip install -r requirements-local-e5.txt` (CPU torch first, see the file), `python scripts/fetch_e5_model.py`, then `dev_local.sh` embeds the catalogue and `/v1/search` and the assistant rank with `intfloat/multilingual-e5-base` (keyword search stays the fallback). Choice and eval numbers: `docs/qa/local-e5-evaluation-manifest.md` on branch `ai/local-e5-v2-evidence` (recall@10 0.954; Roman Urdu 0.892 on that small, easy set). A larger set (`evals/roman_urdu_retrieval_eval.py`, 362 labelled English / Roman Urdu / Urdu queries, synthetic and unreviewed) puts raw E5 at 0.57 recall@10 on Roman Urdu, keyword search at 0.78, and the real pipeline (query parser, then colour filter, then E5) at 0.94. Sets written after tuning started score 0.94 and 0.89; the first time the weak cases (no product word, misspellings) were scored on queries not yet seen, the pipeline got 0.70, so expect 0.7-0.9 on real traffic, not 0.94. Off-topic queries (no shopping word) keep semantic neighbours only within `SEMANTIC_MAX_DISTANCE` (default 0.18); 0% of the off-topic probes returned products. Misspelt product, fabric and season words are corrected as search terms only; a misspelt colour is never turned into a filter.
- **LLM wording.** `ASSISTANT_LLM=true` plus `LLM_CHAIN_DEFAULT` (for example `groq/...`, `gemini/...`, `ollama/qwen2.5`) and that provider's key. The model only writes the reply text; products, prices and cart suggestions still come from the database and the action kernel. Any failure falls back to fixed sentences. Outside `ENVIRONMENT=development` the assistant sends customer text only to `LLM_PRODUCTION_CHAIN` (no-training providers; free tiers such as Groq/Gemini free are refused), after scrubbing emails, URLs and long numbers; with no such chain it silently uses the fixed sentences. In development the free `LLM_CHAIN_DEFAULT` is allowed so you can try real models.
- **Voice.** The Speak button uses the browser's speech recognition (Chrome sends audio to its speech service) and only fills the message box. Spoken queries pass the voice bridge: uncertain or negated speech asks the customer to repeat. Urdu-script speech is not parsed yet, so use English or Roman Urdu wording.
- **Assistant UI.** The storefront shows a "Shopping concierge" panel (launcher at the bottom right, full-screen on mobile; `NEXT_PUBLIC_ASSISTANT_ENABLED=1`; hidden on `/admin` and `/cart`). Answers come from the real backend stream; each product card shows its picture, colour and price, links to the product, and has an "Add to cart" that asks first ("Yes, add") and is checked on the server again before the cart changes. The design comes from the `feat/elegance-assistant-ui-ai-sdk-clean` preview, rebuilt on this project's validated stream (no AI SDK dependency).
- **Memory in the assistant.** For a signed-in customer who opted in, saved `favourite_colour` and `budget_max_pkr` only re-order results the assistant already found (never filter), and it says so ("Using your saved preference ..."). A colour named in the query wins. The assistant saves nothing itself: only an explicit "remember ..." / "yaad rakho ..." produces a Save card, and the memory API still applies consent, validation and audit. Saved values enter an LLM prompt only if every model in the personal chain is declared `no_training` or `self_hosted` in `LLM_PROVIDER_TRAINING_POLICIES` (and then via `LLM_PRODUCTION_CHAIN`); otherwise they stay out.
- **Customer sign-in and memory.** Create a Google OAuth web client, set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` and the five `CUSTOMER_AUTH_*` values in `apps/backend/.env.example`; `/account` then offers sign-in and leads to `/memory`.

## Local AI platform services (optional)

PostgreSQL 17 + pgvector, Redis and the arq worker run from `compose.ai.yaml` for local development only (internal network, no published ports; the production stack is `compose.yaml`).

```bash
cp .env.ai.example .env.ai      # replace placeholders with `openssl rand -hex 32`
docker compose --env-file .env.ai -f compose.ai.yaml up -d --wait
docker compose --env-file .env.ai -f compose.ai.yaml run --rm migrate            # alembic upgrade head
docker compose --env-file .env.ai -f compose.ai.yaml --profile worker up -d worker
```

To run the API, worker or Alembic **on your host** against that database, add the loopback-only override and use `127.0.0.1:5433`:

```bash
docker compose --env-file .env.ai -f compose.ai.yaml -f compose.ai.host.yaml up -d --wait postgres
cd apps/backend && export DATABASE_URL=postgresql+asyncpg://elegance_app:<POSTGRES_APP_PASSWORD>@127.0.0.1:5433/elegance_shawls
alembic upgrade head && uvicorn main:app --port 8000
python -m ingestion.worker      # long-running ingestion worker (separate process)
```

Backend integration tests (real PostgreSQL and Redis through Testcontainers; skipped cleanly without Docker) and the evaluation runner:

```bash
cd apps/backend && pytest -q -m integration      # default `pytest -q` stays container-free
python evals/run_evals.py                        # from the repo root; recorded responses, no LLM quota
```

## Health and readiness

### Frontend
- `/api/health`
- `/api/ready`

### Backend
- `/health/`: liveness, dependency-free.
- `/ready/`: 503 when PostgreSQL (the database for the catalogue, staged products and ingestion jobs) is down; `{"status": "not_ready", "database": "unavailable"}`. It also reports `redis` and `worker` as `disabled`, `connected`/`alive` or `unavailable`/`not_seen`; those never fail readiness because the catalogue works without them. Startup fails fast if `DATABASE_URL` is unset.

Use these endpoints for deployment checks, uptime probes, and alerting.

## Docker-based deployment

A compose-based deployment path is included in `compose.yaml`.

### Required runtime values
The compose stack expects these values:
- `SITE_URL`
- `API_URL`
- `WHATSAPP_NUMBER`
- `ADMIN_API_KEY` (still required by `compose.yaml`; it is only the legacy fallback)
- `POSTGRES_ADMIN_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_BACKUP_PASSWORD` (see `.env.example`; the backend gets `DATABASE_URL` from them)

### Typical flow
```bash
docker compose build --pull
docker compose up -d
```

The compose file:
- runs PostgreSQL on an internal network with no published port (least-privilege application and backup roles)
- builds the backend from `apps/backend` and the frontend from `apps/frontend`
- publishes host ports only on the Caddy proxy
- ships a one-shot `migrate` service (`alembic upgrade head`) that is never started by `up`; running it is a deliberate, approved step (`DEPLOYMENT.md`, "Database migrations")

For a real production rollout, read `DEPLOYMENT.md` and `OPERATIONS.md` first.

## CI

GitHub Actions CI runs on pushes and pull requests to `main`.

Current pipeline covers:
- frontend install, lint, typecheck, build, and tests
- backend dependency install, tests, and Python compile checks
- Playwright E2E execution when present
- backend and frontend container builds

CI definition:
- `.github/workflows/ci.yml`

## Security notes

- Never commit `.env` files or real credentials
- Admins sign in with individual accounts (scrypt password hashes, opaque server-side sessions, roles `viewer`/`editor`/`owner`, durable audit log). Create the first owner with `python scripts/admin_accounts.py bootstrap-owner --email you@example.com` from `apps/backend` after `alembic upgrade head` (see `DEPLOYMENT.md`)
- `ADMIN_API_KEY` is a legacy, expiring fallback: treat it as a production secret, rotate it if exposed, and retire it by leaving it and `ADMIN_LEGACY_KEY_EXPIRES_AT` empty once accounts exist
- Keep PostgreSQL private (internal network, no published port) and use the least-privilege application role
- Restrict `ALLOWED_ORIGINS` to exact HTTPS origins
- Do not place credentials in screenshots, logs, tickets, or browser-delivered code

## Production operations

For launch and maintenance, use the dedicated docs instead of relying only on this README:
- `DEPLOYMENT.md` — environment and rollout requirements
- `OPERATIONS.md` — monitoring, backups, incidents, and key rotation
- `LAUNCH_RUNBOOK.md` — launch gates and customer/admin acceptance checks

## Common development workflows

### Run frontend only
```bash
cd apps/frontend
npm ci
npm run dev
```

### Run backend only
```bash
cd apps/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Rebuild production containers locally
```bash
docker compose build --pull
```

## Known integration boundary

This repository owns the production storefront and product API. Any external admin panel integrating with authenticated product-write routes must match the backend contract documented in the OpenAPI schema and deployment docs, and must keep admin secrets out of browser-delivered code.

## Suggested onboarding order

If you are new to the project, read in this order:
1. this `README.md`
2. `DEPLOYMENT.md`
3. `OPERATIONS.md`
4. `LAUNCH_RUNBOOK.md`
5. `apps/backend/routes/product_routes.py`
6. `apps/frontend/src/`

## License / ownership

No license is declared in the inspected repository files at the time of writing. Add one explicitly if you plan to open-source or redistribute the code.
