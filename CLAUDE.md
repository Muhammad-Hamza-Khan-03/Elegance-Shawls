# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independent apps with no shared tooling at the root. Run commands from inside the app's directory.

- `apps/frontend`: Next.js 16 (App Router, React 19, React Compiler, Tailwind 4) storefront plus the admin UI
- `apps/backend`: FastAPI + SQLAlchemy/asyncpg (PostgreSQL) product API, Python 3.11 (CI uses 3.12)
- `compose.yaml`: postgres + backend + frontend + Caddy proxy for production-style runs (`docker compose up -d`; needs `SITE_URL`, `API_URL`, `WHATSAPP_NUMBER`, `ADMIN_API_KEY`, `POSTGRES_*` passwords; schema via the operator-run `migrate` profile)

## Commands

### Frontend (`apps/frontend`)
```bash
npm ci
npm run dev                 # http://localhost:3000
npm run lint                # eslint
npm run typecheck           # tsc --noEmit
npm test                    # vitest run (src/**/*.test.{ts,tsx})
npx vitest run src/lib/cart.test.ts          # single unit test file
npx vitest run -t "name of test"             # single test by name
npm run build
npx playwright install chromium && npm run test:e2e
npx playwright test e2e/cart.spec.ts --project=chromium   # single e2e spec
```
Playwright starts its own servers: `e2e/mock-api.mjs` (fake backend on :4100) and `next dev` on :3100 with `ADMIN_API_KEY=test-admin-secret`. E2E tests never hit a real backend or database.

### Backend (`apps/backend`)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000        # OpenAPI at /docs
pytest -q
pytest -q -m integration tests/integration/test_api_products.py::test_admin_routes_require_authentication   # single DB-backed test
python -m compileall -q .
```
The default suite is container-free (pure logic, fakes). Everything that needs a database runs under `pytest -q -m integration` against a real PostgreSQL started by Testcontainers (skipped without Docker); `tests/integration/conftest.py` provides the `db` / `pg_engine_factory` fixtures. `tests/conftest.py` adds the backend root to `sys.path`. Imports are top-level module style (`from database.pg import get_pg_session`), so run everything from `apps/backend`.

PostgreSQL and the AI platform foundation:
```bash
pytest -q -m integration                      # Testcontainers: PostgreSQL+pgvector and Redis; skipped without Docker
alembic upgrade head | downgrade base         # needs DATABASE_URL; migrations live in apps/backend/migrations
arq workers.settings.WorkerSettings           # Redis/arq worker for new AI workloads only
python scripts/llm_smoke.py --fake            # LLM gateway smoke test, no keys
python evals/run_evals.py [--release-ready]   # from the repo root; recorded responses, "not evaluated" blocks release
docker compose --env-file .env.ai -f compose.ai.yaml up -d --wait   # local Postgres + Redis (internal network)
```
Plans and decisions: `plans/` holds the roadmap; `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md` is the single canonical architecture document (no separate ADR files).

CI (`.github/workflows/ci.yml`) also runs `npm audit --audit-level=high` and `pip-audit -r requirements.txt`. Dependency bumps for CVEs must keep both passing.

## Architecture

### Request flow
Browser → Next.js storefront → FastAPI `/products/...` → PostgreSQL `products` / `variants` tables (via `repositories/`). Customers have no checkout: the cart (localStorage, `src/lib/cart.ts`) builds a WhatsApp message/URL (`src/lib/whatsapp.ts`) and the order happens off-platform.

### Backend
- `main.py` `create_app()` wires CORS (`ALLOWED_ORIGINS`, comma-separated), `RateLimitMiddleware` (separate public, admin and events limits; Redis-shared when `REDIS_URL` is set, otherwise in-process per instance), the product router, `/health/` (liveness, dependency-free) and `/ready/` (PostgreSQL ping, 503 when down).
- PostgreSQL is required (`DATABASE_URL`; startup fails without it, `/ready/` is 503 when it is down). Schema is Alembic (`migrations/`). SQL lives in `repositories/{products,staged,jobs}.py`, which take an `AsyncSession` and never commit; routes and the worker own transactions.
- Optional services never gate startup: `database/redis_client.py`, `llm/` (gateway) and `workers/` (arq) degrade to disabled when unconfigured or unreachable (PostgreSQL, by contrast, is required). New endpoints live under `/v1` (events, admin jobs). Flat package layout is intentional (architecture doc 3.2).
- `routes/product_routes.py` has a public router plus a nested `admin_router` (`/products/admin/...`) guarded by `security/admin_auth.require_admin_api_key`, which does a constant-time `X-Admin-Key` comparison and returns 503 if `ADMIN_API_KEY` is unset.
- Public visibility means `is_active=True` **and** `status=="active"`. Admin "delete" is a soft delete (archive).
- IDs are UUIDs, exposed as opaque strings under the unchanged `_id` key. Pagination is keyset on `(created_at, id)` descending with opaque, checksummed cursors (`utils/pagination.py`; malformed or tampered cursors are a 400). List responses are `{items, next_cursor}`.

### Frontend
- `src/lib/api.ts` is the only public-API client. `mapBackendProduct` defensively normalizes several backend/legacy ("Quill") shapes (`variants`/`variations`, numeric vs `{amount, currency}` price, and so on) into the storefront `Product` type in `src/types/types.ts`. Shape changes on the backend usually need a matching change here.
- **Admin auth (security-sensitive):** `ADMIN_API_KEY` is a server-only env var and must never be `NEXT_PUBLIC_`.
  - `POST /api/admin/session` checks the submitted key and sets an HMAC-signed `es_admin_session` cookie (`src/lib/admin-session.ts`, 8h TTL, signed with `ADMIN_API_KEY`).
  - `app/admin/(shell)/layout.tsx` redirects to `/admin/login` without a valid session.
  - Browser admin calls go to Next route handlers under `src/app/api/admin/products/...`, which call `proxyAdminRequest` (`src/lib/admin-backend.ts`). It verifies the session cookie, enforces a same-origin check for non-GET methods, then forwards to the backend with the `X-Admin-Key` header.
  - New admin endpoints should follow this proxy pattern. Never call the backend admin routes from client code.
- Next config sets `output: "standalone"`, strict security headers, and a CSP in `next.config.ts`. New external origins (scripts, connect targets) must be allowed there.
- Frontend probes: `/api/health`, `/api/ready`.

## Conventions

- Conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`, `refactor:`). Recent history also uses scoped forms like `fix(p0-66): ...`.
- Changes to env vars, setup, health checks, API behavior, or deploy flow should update `README.md`, `DEPLOYMENT.md`, `OPERATIONS.md`, and/or `LAUNCH_RUNBOOK.md` (per `CONTRIBUTING.md`).
