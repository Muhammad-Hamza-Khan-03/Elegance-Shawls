# Real-stack E2E suite

`npm run test:e2e:real` (apps/frontend) runs Playwright against a genuine stack: Next.js dev server, FastAPI and a disposable PostgreSQL/pgvector database. Nothing is mocked. CI job: `e2e-real-stack` (Postgres service container `pgvector/pgvector:0.8.1-pg17`). Open gaps are listed separately in [real-stack-e2e-coverage-gaps.md](real-stack-e2e-coverage-gaps.md).

## Running it locally
Set, then run `npm run test:e2e:real`:

| Variable | Meaning |
|---|---|
| `E2E_DATABASE_URL` | `postgresql+asyncpg://...` to a **loopback** host (127.0.0.1, localhost, ::1) or a local unix socket (`?host=/abs/dir`) |
| `E2E_DISPOSABLE_DATABASE` | must equal the database name, which must contain an `e2e` token (for example `elegance_e2e`) |
| `E2E_PYTHON` | the backend virtualenv's python (default `python`) |

## Isolation (enforced in `e2e-real/isolation.cjs`, tested by `npm run test:e2e:real:guard`)
- Both conditions are required: a loopback/socket host **and** a database explicitly designated as disposable (name token plus the acknowledgement variable). Anything else is refused by `prepare.mjs`, `launch.mjs` and `playwright.real.config.ts`; `hostaddr` is rejected.
- The servers and the migration/seed commands start with an **allowlisted environment** (PATH, HOME, locale/temp basics plus explicit test values). Provider keys, `DATABASE_URL`, `ADMIN_API_KEY`, Redis settings and every other inherited variable are not forwarded.
- Fixtures are synthetic (`apps/backend/scripts/seed_e2e.py`, development only); `wa.me` is intercepted; no model, provider, Redis or customer data is used.

## Suites
| Suite | Style | Backend | In CI |
|---|---|---|---|
| `e2e/` | UI behaviour | `mock-api.mjs` (fake) | yes (`e2e`) |
| `e2e-real/` | genuine journeys | real FastAPI + PostgreSQL | yes (`e2e-real-stack`) |
| `e2e-live/` | acceptance on a running stack | operator-run (HTTPS compose) | no |

## Covered
Exact-result constraint search in English, Roman Urdu and Urdu, including a lower and an upper price bound and the "in stock" constraint; drafts hidden; hybrid search reporting `semantic:false`; assistant cards verified one by one (count and name) with confirm-once cart actions; cart -> enquiry reference -> intercepted `wa.me`; exact server refusals (`price_changed`, `out_of_stock`, `insufficient_stock`, `unavailable`, admin price change); admin sign-in, wrong-password message, product lifecycle, audit attribution, viewer RBAC with the denial rows audited against the viewer; CSRF (valid session, foreign or missing origin), forged cookies, retired legacy key, malformed input, readiness.

## Mutation evidence
Breaking a rule in the application must fail the suite. Price and stock-in-search rules are enforced twice (SQL narrowing in `repositories/products.py` and the matcher in `catalog/search.py`); a mutation of one layer alone is intentionally absorbed by the other, so both layers are mutated together.
