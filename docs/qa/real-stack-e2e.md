# Real-stack E2E suite

`npm run test:e2e:real` (apps/frontend) runs Playwright against a genuine stack: Next.js dev server, FastAPI and a disposable PostgreSQL/pgvector database. Nothing is mocked. CI job: `e2e-real-stack` (Postgres service container `pgvector/pgvector:0.8.1-pg17`).

Locally: set `E2E_DATABASE_URL=postgresql+asyncpg://...` (a throwaway database; `prepare.mjs` refuses hosted-looking URLs) and `E2E_PYTHON` (backend venv), then `npm run test:e2e:real`. Fixtures are synthetic (`apps/backend/scripts/seed_e2e.py`, development only).

| Suite | Style | Backend | Runs in CI |
|---|---|---|---|
| `e2e/` | UI behaviour | `mock-api.mjs` (fake) | yes (`e2e`) |
| `e2e-real/` | genuine journeys | real FastAPI + PostgreSQL | yes (`e2e-real-stack`) |
| `e2e-live/` | acceptance on a running stack | operator-run (HTTPS compose) | no |

## Covered
Catalogue browse/search from real rows (drafts hidden); English, Roman Urdu and Urdu constraint search; assistant grounded cards and confirm-once cart action (no LLM); cart -> enquiry reference -> intercepted `wa.me`; server refusal of stale price, out-of-stock, over-stock and admin price changes; admin sign-in, product lifecycle, audit attribution, viewer RBAC; unauthenticated, forged-cookie, foreign-origin and retired-key access; malformed input; readiness.

## Not covered
Semantic ranking quality (no embedding model in CI; hybrid only proven to degrade to lexical), LLM wording, Google sign-in and customer memory, WhatsApp bridge, Redis-shared rate limits (limits are raised for the run), real WhatsApp delivery, deployment.
