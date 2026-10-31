# Staging-integration consolidation

One branch, `staging-integration`, that carries all newly developed and fixed work in the repository, built **on top of `main`** (`283b27e`, unchanged).
`main` was not modified or merged into. Nothing was deployed, no branch was deleted, no history was rewritten or force-pushed.

## Why this branch exists, and why it is not called `staging`

- The repository's own workflow (`docs/RELEASE_WORKFLOW.md`) has **no integration branch before `main`**: one protected `main` plus short-lived branches.
  There was no `staging`, `develop`, `dev` or `release` branch, so this branch was created from `main`.
- A branch called plain `staging` cannot exist while `staging/e5-semantic-activation` exists (Git cannot hold a ref that is both a branch and a folder).
  Removing or renaming that branch was out of scope, so the closest safe name was used. Renaming later is one command once `staging/e5-semantic-activation` is retired.

## What was merged (in order)

| # | Branch | How | Notes |
|---|---|---|---|
| 1 | `integration/local-complete` | real merge | 72 commits: the whole M1-M5 chain plus the assistant, memory, voice, semantic search and UI work. Merged against the PostgreSQL foundation (`ecf690b`) as base, see "Why the merge base matters". |
| 2 | `ai/local-ai-search-integration` | history merge (`-s ours`) | The phase-1 line (attributes, staff enrichment + admin review, hybrid retrieval, local E5 evidence). Already in `main` as the squashed PR #125 (+ #126-#128); only older versions of three files differed, `main`'s newer content kept. Also covers 11 more phase-1 / embedding branches it contains. |
| 3 | `docs/staging-first-release-workflow` | real merge | `RELEASE_WORKFLOW.md`, infrastructure baseline record, `AGENTS.md`; the architecture doc's unique 92-line section carried over as Appendix A. |
| 4 | `staging/e5-semantic-activation` | real merge | Staging Dockerfile (pinned offline E5 model, migrations/seed/backfill on start), staging catalogue seed script, staging allowed for local E5. |
| 5 | `ai/synonym-error-analysis` | real merge | Synonym gap analysis, aliases, eval template notes. |
| 6 | `ai/openai-embedding-eval` | real merge | Bounded OpenAI embedding provider and its eval tests; conflicts resolved by keeping both sides. |
| 7 | `ai/m2-s3-hybrid-retrieval-claude-retry` | history merge + selective keep | A competing implementation of hybrid `/v1/search`. Kept: `semantic/fusion.py` (pure weighted reciprocal-rank fusion) and its tests. Not adopted: `repositories/search.py`, offset-cursor helpers, route wiring. See "Not adopted". |
| 8 | `fix/render-asyncpg-url` (#126) | history merge | Already in `main`; tree unchanged. |
| 9 | `chore/pin-e5-evaluated-snapshot` (#128) | history merge | Already in `main`; tree unchanged. |
| 10 | `fix/staging-migrations` (#127) | real merge | Dockerfile conflict resolved by keeping the staging version, which already contains this change. |

After these merges **every local and remote branch is reachable from `staging-integration`** (checked with `git rev-list HEAD..<branch>` for all refs except `main`).

## Features now on this branch

- **Backend:** PostgreSQL + pgvector foundation, repositories, Alembic (0001-0015, one linear head); individual admin accounts, server-side sessions, roles, audit log;
  `GET /v1/search` (keyword + semantic ranking, variant-level filters, cursor paging) **and** `POST /v1/search` + `/v1/search/hybrid` (constraint-parsing search);
  enquiry references; encrypted backup foundation; catalogue attributes; staff enrichment suggestions with admin review; ingestion (one source) with category filter;
  action kernel + durable execution; assistant (grounded in the live catalogue, conversation memory, optional LLM wording, voice bridge); customer sign-in (Google), customer memory and its privacy gate, reasoned suggestions; LLM gateway; Redis/arq workers.
- **Embeddings (two systems, both kept):** `main`'s `product_embeddings` / `variant_embeddings` with HNSW indexes, job worker and E5 provider (`embeddings/`, `search/`), and the assistant's
  `semantic/` pipeline over `semantic_embeddings` / `semantic_embedding_jobs`. They use separate tables, modules, classes and backfill scripts and do not interfere.
- **Frontend:** storefront, admin (accounts login, staging review, enquiries, enrichment review), the new Shopping-concierge panel with per-card server-checked add-to-cart, memory page, account page, Google sign-in.
- **AI / evals:** parser v7 (English, Roman Urdu, Urdu script, typo-tolerant product words), 362-query Roman Urdu retrieval eval, OpenAI/Gemini/Groq/local E5 embedding evaluation harness, synonym analysis, Urdu voice eval contract.
- **Docs:** release workflow, infrastructure baseline, architecture (+ Appendix A), runbooks, this record.

## Conflicts and how they were resolved (nothing dropped)

### Why the merge base matters
`main` holds the phase-1 line as **one squashed commit** built on a base that predates the PostgreSQL foundation, so Git's own merge base made both sides look like they independently
added the same foundation code (58 conflicts). The true common ancestor in content terms is the foundation commit `ecf690b`; merging against that base left 11 real conflicts.

### The real conflicts (11 files)
- `models/relational_model.py`: both sides added different tables, and one table name (`product_embeddings`) was used by both with different schemas. The file was rebuilt: ours as the base,
  `main`'s unique classes inserted verbatim (`CatalogAttribute`, `EnrichmentSuggestion`, embedding tables, `Variant` unique constraint), and **our** embedding classes renamed `SemanticEmbedding` / `SemanticEmbeddingJob`
  (`semantic_embeddings`, `semantic_embedding_jobs`).
- `repositories/embeddings.py` and `scripts/embedding_backfill.py` (both sides added a different file at the same path): `main`'s kept at the path, ours moved to
  `repositories/semantic_embeddings.py` and `scripts/semantic_backfill.py`; all of our imports and tests updated.
- **Migrations:** both lines used revisions 0007-0009. `main`'s 0007-0009 are untouched (they may already be applied to a staging database); ours became **0010-0015**
  (admin accounts 0010, enquiries 0011, semantic embeddings 0012, action executions 0013, customer memory 0014, customer sessions 0015). One linear head.
- `main.py`: two different routers both named `search_router` (`GET` vs `POST /v1/search`); both mounted under distinct names.
- `security/rate_limit.py`: our named buckets kept and `main`'s anonymous-search limit kept (now also covers `/v1/search/hybrid`).
- `workers/settings.py`: both job sets registered. `repositories/products.py`, `AdminShell.tsx`, `requirements-local-e5.txt`, `test_repositories_static.py`: union of both sides.
- `tests/integration/test_api_search.py`: both tests kept (`main`'s POST contract file keeps its name; ours is `test_api_catalogue_search.py`).

### Fixed after the merge (found by the integration checks)
- `routes/enrichment_routes.py` still imported the removed `require_admin_api_key`; it now uses `require_admin` like the other admin routes (individual accounts, roles, audit).
- A change `main` made *inside* the existing `Variant` model (`UniqueConstraint("id", "product_id")`) was missed in the rebuilt model; restored (caught by the models-match-schema test).
- Tests that hard-coded the old migration numbers or the single head `0009`, the staging-environment test that contradicted `staging/e5-semantic-activation`, and `main`'s enrichment proxy/e2e tests that used the removed shared-key login: updated to the merged reality.

## Checks run on this branch (informational; none blocked the consolidation)

- Backend unit: 1565 passed. Backend integration (real PostgreSQL, full migration chain, models vs schema): 577 passed.
- Frontend: lint clean, typecheck clean, 385 unit tests passed, 68 Playwright specs passed.
- Not run: a production build, container image builds, any deployment, any migration against a shared database.

## Not adopted / still unmerged (documented, not discarded)

1. **Hybrid retrieval retry** (`ai/m2-s3-hybrid-retrieval-claude-retry`): a second design of hybrid `/v1/search` (offset cursors, query embedding inside the route).
   It competes with the ranked-cursor hybrid search already here (`repositories/hybrid.py`). Left on its branch: `repositories/search.py`, offset-cursor helpers in `utils/pagination.py`,
   the route wiring and `test_api_hybrid_search.py`. Its RRF fusion (`semantic/fusion.py`) is on this branch but **not yet wired**; the plan asks for RRF, so wiring it is a candidate follow-up.
2. **Two embedding systems.** Kept side by side to avoid dropping either; converging on one (and one backfill) is a follow-up. Until then the staging image drives `main`'s system (`EMBEDDING_*` / `LOCAL_E5_*`),
   and the assistant's pipeline stays off unless `SEMANTIC_*` is set.
3. **Uncommitted work in other checkouts**, which a branch merge cannot include (left untouched, not copied):
   - `Elegance-Shawls-chat-assistant-ui-clean`: the assistant UI preview (AI SDK based). Its design was ported onto the real stream on this branch; its `package.json` additions (`ai`, `@ai-sdk/react`) were not taken.
   - `.claude/worktrees/local-multilingual-e5`, `.claude/worktrees/local-ingestion-category-filter`: their uncommitted changes are older versions of files already present here.
   - `.claude/worktrees/docs-status-correction` (a modified architecture doc), `/home/hamza/qa-m2-integrated-*/qa-artifacts/`, `/home/hamza/qa-m1-s6-*/docs/qa/m1-s6-promotion-packet-*.md`: QA/doc artifacts that exist only in those folders.

## Operating notes

- **Existing databases need attention.** A database already migrated by `main`'s chain is at 0009 and will receive 0010-0015 on `alembic upgrade head` (additive; see `DEPLOYMENT.md` for the approval boundary).
  A **local development database created from the pre-consolidation integration branch is stamped with the old numbers** (our 0012 is now 0015): recreate it, or restore data and run `alembic stamp` for the revisions it really has.
- The staging Dockerfile enables `main`'s E5 system and runs migrations/seed/backfill at start-up; review the environment before pointing it at any shared database.
- Pushing this branch may trigger preview builds if the repository is linked to a hosting provider (the release workflow says Vercel Preview is used for branch review).
