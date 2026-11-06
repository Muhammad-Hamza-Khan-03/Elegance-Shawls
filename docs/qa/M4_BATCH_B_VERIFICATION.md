# M4 Batch B Verification Evidence

Candidate scope: synthetic-only, staging-only explainable recommendation assignment and append-only impression provenance. No production activation, customer data, live credentials, deployment, VPS, `main`, issue closure, or `release_ready` changes were performed.

Base: `dff5248e96911640c1b039481b0fd0a7464dc0d1`
Worktree: `/home/hamza/qa-m1-s4-clean`
Branch: `m4-batch-a`

## Canonical checks

- Backend, from `apps/backend`: `pytest -q` -> **1600 passed, 597 deselected**.
- Backend compile: `python -m compileall -q .` -> **pass**.
- Frontend, from `apps/frontend`: `npm test` -> **32 files passed, 394 tests passed**.
- Frontend lint: `npm run lint` -> **pass**.
- Frontend typecheck: `npm run typecheck` -> **pass**.
- Frontend build: `npm run build` -> **pass**. Next emitted only the existing `metadataBase` warning.
- Diff hygiene: `git diff --check` -> **pass**.

The frontend command was run exactly as the repository defines it (`npm test`); no unsupported `--runInBand` flag was used.

## Disposable PostgreSQL integration

Docker/Testcontainers PostgreSQL image: `pgvector/pgvector:0.8.1-pg17`.

- `pytest -q -m integration tests/integration/test_api_suggestions.py` -> **3 passed, 2 deprecation warnings**.
- `pytest -q -m integration tests/integration/test_postgres_schema.py` -> **23 passed, 2 deprecation warnings**.

The two integration files were run as separate disposable-container invocations so the migration reversibility guard was not contaminated by fixture data from another file.

## Scope and safety

The candidate changed only Batch B backend configuration/model/repository/route/schema/engine code, the recommendation migration and experiment module, the focused and relevant integration tests, and this evidence record. Batch A/M3 and unrelated files remain untouched. Flags default off; synthetic-only and staging-only guards remain enforced. No production memory path or release-readiness state was modified.

Independent QA initially identified three bounded issues: category/style suggestions did not require a purchasable variant; impression input was not checked against a server-issued recommendation; and the synthetic subject was not bound to the authenticated synthetic customer. Manager rework added the purchasable-variant gate, server-side recommendation/evidence/provenance/version validation before insert, and the exact `synthetic:<principal.customer_id>` staging subject binding. The canonical and disposable PostgreSQL checks were rerun after rework; re-QA must verify the revised commit.
