# Elegance Shawls

[![Main Branch](https://img.shields.io/badge/branch-main-111827?style=flat-square)](https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/tree/main)
[![Frontend](https://img.shields.io/badge/frontend-Next.js_16-000000?style=flat-square&logo=next.js)](./apps/frontend)
[![Backend](https://img.shields.io/badge/backend-FastAPI-05998b?style=flat-square&logo=fastapi)](./apps/backend)
[![Database](https://img.shields.io/badge/database-MongoDB-0f7a43?style=flat-square&logo=mongodb)](./apps/backend)
[![Ordering](https://img.shields.io/badge/orders-WhatsApp-25D366?style=flat-square&logo=whatsapp&logoColor=white)](./apps/frontend)
[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)](./.github/workflows/ci.yml)

Production-grade e-commerce platform for shawls and stoles, built around a modern customer storefront, a FastAPI product service, and WhatsApp-first ordering.

This repository contains the customer-facing storefront and the backend product API that powers catalogue discovery, product detail pages, stock-aware selection, and order handoff to WhatsApp.

## At a glance

- *Storefront:* Next.js customer experience for browsing and order handoff
- *API:* FastAPI product service with authenticated admin write routes
- *Database:* MongoDB-backed product catalogue
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
- `apps/backend` — FastAPI + MongoDB product API with public catalogue routes and authenticated admin product management routes

### Production docs
- `DEPLOYMENT.md` — production environment and rollout requirements
- `OPERATIONS.md` — health, backup, restore, monitoring, and incident-response guidance
- `LAUNCH_RUNBOOK.md` — launch gates and end-to-end acceptance checks
- `PRODUCTION_LAUNCH_PLAN.md` — launch planning notes

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
- MongoDB-backed persistence
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
MongoDB

Admin write operations are authenticated with X-Admin-Key.
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
- Motor / PyMongo
- Pydantic v2
- MongoDB
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
- MongoDB (local or remote)
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
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | Database name | `elegance_shawls` |
| `ALLOWED_ORIGINS` | Comma-separated allowed storefront origins | `http://localhost:3000` |
| `ADMIN_API_KEY` | Secret required for authenticated admin writes | `replace-with-a-long-random-secret` |
| `ENVIRONMENT` | Runtime environment label | `development` |
| `PUBLIC_RATE_LIMIT_PER_MINUTE` | Public route request limit | `120` |
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

## Health and readiness

### Frontend
- `/api/health`
- `/api/ready`

### Backend
- `/health/`
- `/ready/`

Use these endpoints for deployment checks, uptime probes, and alerting.

## Docker-based deployment

A compose-based deployment path is included in `compose.yaml`.

### Required runtime values
The compose stack expects these values:
- `SITE_URL`
- `API_URL`
- `WHATSAPP_NUMBER`
- `ADMIN_API_KEY`
- `MONGO_DB_NAME`

### Typical flow
```bash
docker compose build --pull
docker compose up -d
```

The compose file:
- runs MongoDB
- builds the backend from `apps/backend`
- builds the frontend from `apps/frontend`
- binds backend to `127.0.0.1:8000`
- binds frontend to `127.0.0.1:3000`

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
- Treat `ADMIN_API_KEY` as a production secret and rotate it if exposed
- Keep MongoDB private, authenticated, and TLS-enabled in production
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
