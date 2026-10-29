# Elegance Shawls product API

Public storefront reads use `GET /products/` and `GET /products/slug/{slug}`.
List responses use `{ "items": [...], "next_cursor": "..." }`; pass the cursor
back with `?cursor=...&limit=20`. Only active products are publicly visible.

Administrative operations live under `/products/admin` and require the
`X-Admin-Key` header:

- `POST /products/admin/` — create
- `GET /products/admin/` and `GET /products/admin/{id}` — inspect all lifecycle states
- `PUT /products/admin/{id}` — replace editable product data
- `PATCH /products/admin/{id}/status` — publish, draft, mark out of stock, or archive
- `PATCH /products/admin/{id}/stock` — set a variant's stock count
- `DELETE /products/admin/{id}` — soft-delete by archiving

Configure the same long random `ADMIN_API_KEY` in the API and trusted Quill
server. Never put this secret in a `NEXT_PUBLIC_` variable or browser bundle.
Production deployments should also enforce rate limits at the edge; the API's
in-process limiter protects a single application instance.

`GET /health/` is a liveness probe (no dependencies). `GET /ready/` returns 503 when PostgreSQL is unreachable.
The catalogue, staged products and ingestion jobs live in PostgreSQL (`DATABASE_URL`, required; startup fails fast without it).
Schema comes from Alembic: run `alembic upgrade head` before starting the API or the ingestion worker. Product, variant and
staged-product identifiers are opaque UUID strings under the same `_id` key; list cursors are opaque `(created_at, id)` tokens
(a malformed or tampered cursor is a 400).

Run contract and security tests with `pip install -r requirements-dev.txt`
followed by `pytest`.

## AI platform foundation and PostgreSQL runtime

- **PostgreSQL** (`DATABASE_URL`, required): async SQLAlchemy in `database/pg.py`, models in `models/relational_model.py`, reversible Alembic migrations in `migrations/`. From `apps/backend` with `DATABASE_URL` set: `alembic upgrade head`, `alembic downgrade base`, `alembic current`. Locally use `docker compose ... run --rm migrate` (see the root README). Startup fails fast if `DATABASE_URL` is unset; if the server is merely unreachable the API still starts, `/ready/` answers 503 and database-backed routes answer 5xx until it returns. The schema is migrated only by an operator (`DEPLOYMENT.md`, "Database migrations"), never at startup.
- **Redis/arq** (`REDIS_URL`, empty = disabled): new AI workloads only (`workers/`). Run `arq workers.settings.WorkerSettings`; health: `arq --check workers.settings.WorkerSettings`. The PostgreSQL-backed ingestion worker (`python -m ingestion.worker`) is separate. When Redis is set, rate limits are shared across replicas and fall back to per-instance limits if Redis is down. Admin-only sample job: `POST /v1/admin/jobs/sample`, `GET /v1/admin/jobs/{id}`.
- **Events**: `POST /v1/events` (batched, size-capped, rate-limited, needs `SESSION_SIGNING_KEY`). `GET /products/` records an `impression` with result positions (skipped for DNT/GPC); it has no server-side query or filters, so server-side search logging belongs to the Phase 1 search endpoint. Retention runs daily on the arq worker cron (`purge_events_job`); `python -m events.retention` runs it by hand.
- **LLM gateway** (`llm/`): logical chains from `LLM_CHAIN_DEFAULT` / `LLM_PRODUCTION_CHAIN`, bounded fallback, daily and environment budgets with an 80% warning, and `personal=True` calls never reach free-tier providers. Smoke test without keys: `python scripts/llm_smoke.py --fake`. Budgets are shared through Redis when configured. Groq, Gemini, OpenRouter and Ollama use the built-in client (keys from `GROQ_API_KEY` etc.); other providers and optional Langfuse need `pip install -r requirements-llm.txt`, outside the audited `requirements.txt` while LiteLLM pins `filelock<4`. The first real call is `python scripts/llm_smoke.py`, run by the operator with their own key.
- **Tests**: `pytest -q` is fast and container-free. `pytest -q -m integration` starts PostgreSQL (pgvector) and Redis through Testcontainers and skips cleanly when Docker is unavailable.
