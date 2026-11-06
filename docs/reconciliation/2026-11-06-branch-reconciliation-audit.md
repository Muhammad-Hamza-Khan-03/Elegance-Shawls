# Elegance Shawls Git Reconciliation Audit

- Generated (UTC): `2026-11-06T14:17:20.641069+00:00`
- Scope: local/remote refs, all registered worktrees, dirty state, ancestry/tree-delta comparisons, GitHub PR/issue/project/CI references, and cleanup classification.
- Safety boundary: `main`, production/VPS/deployment/credentials/`release_ready` untouched; no force-push, reset, or destructive clean.

## Baseline canonical refs

- `origin/main` = `283b27eee90533435ef3b2e28e6a3823ee1c5d23`
- `origin/staging` = `b4c5f58046cda2c848518a70425644ee80eee55e`
- `origin/staging-integration` = `fed9db4eb1ab82e9bf02c387c39c162b38111b7a`

## Integration decision

- Exact `integration` ref was **not created**: Git ref namespace `integration/local-complete` already exists and is linked to an active worktree. Creating `integration` would require renaming/deleting a live namespace/ref, so it is unsafe.
- Existing `staging-integration` remains the canonical integration ref for this reconciliation. `integration/local-complete` is preserved as a divergent local/remote-gone worktree and is not renamed or deleted.

## Worktrees

### `/home/hamza/GitHub-Repositories/Elegance-Shawls`
- HEAD: `3003eba6835e424fd4a9f37b23ad510d0491b161`; branch: `refs/heads/ai/phase-0-foundations`; dirty paths: `5`
- Dirty paths: `.gitignore`, `apps/frontend/.env.example`, `apps/frontend/AGENTS.md`, `.claude/`, `.worktrees/`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls-chat-assistant-ui`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/feat/elegance-assistant-ui-ai-sdk`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls-m1-s4`
- HEAD: `7674dd255645cf0061bfff67470a98dba82d15cb`; branch: `refs/heads/ai/m1-s4-enquiry-reference`; dirty paths: `1`
- Dirty paths: `apps/frontend/AGENTS.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls-m4-s1`
- HEAD: `55057d90cd2bd2424b1d8a61c5b8cff8365c3d1b`; branch: `refs/heads/ai/m4-s1-privacy-memory`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/docs-status-correction`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/worktree-docs-status-correction`; dirty paths: `1`
- Dirty paths: `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/embedding-provider-contract`
- HEAD: `0cf5613ce1e40c7b6ec3ca36cbeedd8137ecfc4f`; branch: `refs/heads/ai/embedding-provider-contract`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/embedding-synthetic-eval`
- HEAD: `c71ef03062f2bcba535e53071e61429ebcf020e4`; branch: `refs/heads/ai/embedding-synthetic-eval`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-ai-search-integration`
- HEAD: `0cd3224528c9996524197287194345b64a3352cf`; branch: `refs/heads/staging-e5-semantic-activation-local`; dirty paths: `13`
- Dirty paths: `apps/backend/configuration/config.py`, `apps/backend/scripts/embedding_backfill.py`, `apps/backend/search/hybrid.py`, `apps/backend/tests/conftest.py`, `apps/backend/tests/test_local_semantic_search.py`, `apps/backend/tests/test_postgres_layer.py`, `apps/backend/tests/test_repositories_static.py`, `apps/backend/requirements-local-embeddinggemma2.txt`, `apps/backend/search/local_gemma.py`, `apps/backend/tests/test_local_gemma_search.py`, `apps/frontend/AGENTS.md`, `docs/qa/embeddinggemma-independent-reqa.md`, `docs/qa/embeddinggemma-manager-rework-contract.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-e5-v2-evidence`
- HEAD: `61a45a1e7061e016ea7583e893486c77701f2278`; branch: `refs/heads/ai/local-e5-v2-evidence`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-ingestion-category-filter`
- HEAD: `61a45a1e7061e016ea7583e893486c77701f2278`; branch: `refs/heads/ai/local-ingestion-category-filter`; dirty paths: `5`
- Dirty paths: `apps/backend/.env.example`, `apps/backend/configuration/config.py`, `apps/backend/ingestion/pipeline.py`, `apps/backend/ingestion/refresh.py`, `apps/backend/tests/test_ingestion_category_filter.py`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-multilingual-e5`
- HEAD: `c71ef03062f2bcba535e53071e61429ebcf020e4`; branch: `refs/heads/worktree-local-multilingual-e5`; dirty paths: `8`
- Dirty paths: `apps/backend/embeddings/providers/__init__.py`, `docs/qa/embedding-provider-evaluation-template.md`, `evals/run_embedding_eval.py`, `evals/tests/test_embedding_eval.py`, `apps/backend/embeddings/providers/local_e5.py`, `apps/backend/requirements-local-e5.txt`, `apps/backend/tests/test_local_e5_provider.py`, `docs/qa/local-e5-evaluation-manifest.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m1-s1-server-search`
- HEAD: `69b7b37edb019bb393a2533bfd44d8e2d36d2b17`; branch: `refs/heads/ai/m1-s1-server-search`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m1-s2-variant-filters`
- HEAD: `9df1a5be5a6849eb1cc2098e04e18c3f8bc685a6`; branch: `refs/heads/ai/m1-s2-variant-filters`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m3-s5-action-registry`
- HEAD: `f466ebcf49e6ab4348aeec68dcf838c7a1c83f77`; branch: `refs/heads/ai/m3-s5-action-registry`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m3-staging-promotion`
- HEAD: `f466ebcf49e6ab4348aeec68dcf838c7a1c83f77`; branch: `refs/heads/chore/m3-staging-promotion`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/openai-embedding-eval`
- HEAD: `82c034de3e4838e1feac2d2b7ccd1f3d701b8292`; branch: `refs/heads/ai/openai-embedding-eval`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s1-retrieval`
- HEAD: `f1e786bb5883e007ad08ab184712503059d3071c`; branch: `refs/heads/ai/phase-1-retrieval`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s2-attributes`
- HEAD: `64fc22c7aa932950295f2adecda51597a24be479`; branch: `refs/heads/ai/phase-1-attributes`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s3-admin-review`
- HEAD: `40653fe5ef84c8eb6b58785cd526986f1866f8d4`; branch: `refs/heads/ai/phase-1-enrichment-admin-review`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s3-enrichment`
- HEAD: `976eb0ae5ab42af7bf059752430f3775d2795d9c`; branch: `refs/heads/ai/phase-1-enrichment`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4a-representations`
- HEAD: `843a22857999470ab96a64497f2b0fb64d37321a`; branch: `refs/heads/ai/phase-1-s4a-representations`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4b-embeddings`
- HEAD: `0719769bdc6cabf5537d6578f7ad162764457ee4`; branch: `refs/heads/ai/phase-1-s4b-embeddings`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4c-hybrid`
- HEAD: `2220811411c55ea367abb4b44deab460f99dfb54`; branch: `refs/heads/ai/phase-1-s4c-hybrid`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/reviewed-synthetic-benchmark-v2`
- HEAD: `24346e8c4f0af2f1cae98c5d9abdcaccad3d8f13`; branch: `refs/heads/ai/reviewed-synthetic-benchmark-v2`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/semantic-error-analysis`
- HEAD: `b693d7733fe31879ea46d091a69b764b78cff580`; branch: `refs/heads/ai/synonym-error-analysis`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_1b57d00f`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_1b57d00f`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_209ec7cb`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_209ec7cb`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_2749cbd6`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_2749cbd6`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_2b45c806`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_2b45c806`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_31294d42`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_31294d42`; dirty paths: `8`
- Dirty paths: `.github/workflows/ci.yml`, `apps/backend/tests/test_evals_runner.py`, `evals/datasets/filter_parsing.jsonl`, `evals/recorded/filter_parsing.jsonl`, `evals/run_evals.py`, `evals/thresholds.yaml`, `evals/README.md`, `evals/baseline_report.json`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_345e5309`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_345e5309`; dirty paths: `13`
- Dirty paths: `.github/workflows/ci.yml`, `apps/backend/requirements-dev.txt`, `apps/frontend/e2e/mock-api.mjs`, `apps/frontend/package-lock.json`, `apps/frontend/package.json`, `apps/frontend/playwright.config.ts`, `apps/frontend/vitest.config.ts`, `apps/backend/.coverage`, `apps/backend/.coveragerc`, `apps/backend/coverage.xml`, `apps/frontend/e2e/a11y.spec.ts`, `apps/frontend/e2e/keyboard.spec.ts`, `docs/qa/accessibility-baseline.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_34b3f1b3`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_34b3f1b3`; dirty paths: `10`
- Dirty paths: `apps/backend/.env.example`, `apps/backend/configuration/config.py`, `apps/backend/observability/request_log.py`, `apps/backend/observability/tracing.py`, `apps/backend/observability/error_reporting.py`, `apps/backend/tests/test_error_reporting.py`, `apps/frontend/src/app/error.tsx`, `apps/frontend/src/app/global-error.tsx`, `apps/frontend/src/lib/error-reporter.test.ts`, `apps/frontend/src/lib/error-reporter.ts`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_6b56fbc5`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_6b56fbc5`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_7b0e9ae9`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_7b0e9ae9`; dirty paths: `261`
- Dirty paths: `.env.example`, `.env.local.example`, `.github/workflows/ci.yml`, `CLAUDE.md`, `CONTRIBUTING.md`, `DEPLOYMENT.md`, `DEPLOYMENT_VALIDATION.md`, `LAUNCH_RUNBOOK.md`, `OPERATIONS.md`, `README.md`, `apps/backend/.env.example`, `apps/backend/Dockerfile`, `apps/backend/README.md`, `apps/backend/configuration/config.py`, `apps/backend/database/pg.py`, `apps/backend/ingestion/pipeline.py`, `apps/backend/ingestion/refresh.py`, `apps/backend/main.py`, `apps/backend/models/relational_model.py`, `apps/backend/repositories/products.py`, `apps/backend/routes/ingestion_routes.py`, `apps/backend/routes/job_routes.py`, `apps/backend/routes/llm_routes.py`, `apps/backend/routes/product_routes.py`, `apps/backend/scripts/verify_local_api_flow.py`, `apps/backend/security/admin_auth.py`, `apps/backend/security/rate_limit.py`, `apps/backend/tests/integration/api_support.py`, `apps/backend/tests/integration/conftest.py`, `apps/backend/tests/integration/test_api_review.py`, `apps/backend/tests/integration/test_catalogue_schema.py`, `apps/backend/tests/integration/test_postgres_schema.py`, `apps/backend/tests/test_events_server_side.py`, `apps/backend/tests/test_model_discovery.py`, `apps/backend/tests/test_postgres_layer.py`, `apps/backend/tests/test_product_contract.py`, `apps/backend/tests/test_redis_queue_and_rate_limit.py`, `apps/backend/tests/test_repositories_static.py`, `apps/backend/tests/test_trace_propagation.py`, `apps/backend/utils/pagination.py` …
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_89e0dc03`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_89e0dc03`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_92e4697d`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_92e4697d`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_aa03e4de`
- HEAD: `77f4fb50a4aea18e99ef347d895efb1a07b2a281`; branch: `refs/heads/wt/t_aa03e4de`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_b3172993`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_b3172993`; dirty paths: `4`
- Dirty paths: `apps/frontend/e2e/mock-api.mjs`, `apps/frontend/src/lib/api.test.ts`, `apps/frontend/src/lib/api.ts`, `docs/qa/2026-11-01-selective-catalogue-caching-evaluation.md`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_b6ca01ab`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_b6ca01ab`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_bbfdf061`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_bbfdf061`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c09f05ba`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_c09f05ba`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c4b434d4`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_c4b434d4`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c6458d03`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_c6458d03`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_d6e82c9c`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_d6e82c9c`; dirty paths: `0`
### `/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_e14699d9`
- HEAD: `ecf690bb7778e15aa7fa588b3a0a62ce98bc55cc`; branch: `refs/heads/wt/t_e14699d9`; dirty paths: `0`
### `/home/hamza/qa-batch-134-135-142`
- HEAD: `5981e8ab45ccc311986082dbbbde060f9bffd08c`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/qa-batch-79-133-45cea1d`
- HEAD: `45cea1d6d86e0d7cc2ab04add322f8146bb4c878`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/qa-batch-79-133-47241ec`
- HEAD: `47241ec537cf4a2d31a45a2d1d78cb4fe74471f8`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/qa-batch-79-133-final`
- HEAD: `47241ec537cf4a2d31a45a2d1d78cb4fe74471f8`; branch: `(detached)`; dirty paths: `1`
- Dirty paths: `--help/`
### `/home/hamza/qa-elegance-a0e651b`
- HEAD: `a0e651ba94eba1c1d4ede102317c3fc3a8ed603b`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/qa-m1-s4-clean`
- HEAD: `6d4dcff6d2818f9b49c1d443248c0660fee14d98`; branch: `refs/heads/m4-batch-a`; dirty paths: `0`
### `/home/hamza/qa-m1-s6-63d33ca`
- HEAD: `63d33cacbec8b7d237f81be4cd62a403e5ce1789`; branch: `(detached)`; dirty paths: `1`
- Dirty paths: `docs/qa/m1-s6-promotion-packet-63d33ca.md`
### `/home/hamza/qa-m2-integrated-44c0d1374e6d478658b10121bb4c8d40c24a3850`
- HEAD: `44c0d1374e6d478658b10121bb4c8d40c24a3850`; branch: `(detached)`; dirty paths: `1`
- Dirty paths: `qa-artifacts/`
### `/home/hamza/worktrees/cos-batch-79-133`
- HEAD: `7a6629a563803f2cd56f0bdecdaf94aabae1a428`; branch: `refs/heads/ai/cos-batch-79-133`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-143`
- HEAD: `13264b2cbd766c6e363fe9ce066875b54eedf656`; branch: `refs/heads/docs/issue-143-recovery`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-batch-134-135-142`
- HEAD: `5981e8ab45ccc311986082dbbbde060f9bffd08c`; branch: `refs/heads/ai/batch-134-135-142`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-batch-137-136`
- HEAD: `a0e651ba94eba1c1d4ede102317c3fc3a8ed603b`; branch: `refs/heads/ai/batch-137-136`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-batch-137-136-rework`
- HEAD: `e6814b6cc0467b2c435308df4f7186cf199b36e3`; branch: `refs/heads/ai/batch-137-136-rework`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m1-s3-admin-accounts`
- HEAD: `8c3fc4bef32300c7fd5015a6393dd7d613229310`; branch: `refs/heads/ai/m1-s3-admin-accounts`; dirty paths: `1`
- Dirty paths: `apps/frontend/AGENTS.md`
### `/home/hamza/worktrees/elegance-m1-s5-backup-restore`
- HEAD: `63d33cacbec8b7d237f81be4cd62a403e5ce1789`; branch: `refs/heads/ai/m1-s5-backup-restore`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s0-s1-foundation`
- HEAD: `f68d98b2fdfd621855b49e33aff4d02ea5b60660`; branch: `refs/heads/ai/m2-s0-s1-foundation`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s2-claude`
- HEAD: `3be8b3fcaddf0825e5dab51e04b6522fedb5c51d`; branch: `refs/heads/ai/m2-s2-pgvector-persistence`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s3-claude`
- HEAD: `75a28b357da6f3d10c476d8eb185e3c62d96e9a3`; branch: `refs/heads/ai/m2-s3-hybrid-retrieval`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s3-claude-retry`
- HEAD: `117c3c7b548781a27d0ad389376bd7bd5a112999`; branch: `refs/heads/ai/m2-s3-hybrid-retrieval-claude-retry`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s4-claude`
- HEAD: `d7ebaefa67901132a05aaf32c1ac374227ff3dcd`; branch: `refs/heads/ai/m2-s4-query-parser`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m2-s5-claude`
- HEAD: `44c0d1374e6d478658b10121bb4c8d40c24a3850`; branch: `refs/heads/ai/m2-s5-claude`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m3-s1-claude`
- HEAD: `f8ce311a084532113663b025daed3b1654790cb9`; branch: `refs/heads/ai/m3-s1-validated-action-kernel`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m3-s2-claude`
- HEAD: `d4e7e34988ad4c2aad2266eb2d0c5aa7a5b49905`; branch: `refs/heads/ai/m3-s2-streaming-assistant`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m3-s3-claude`
- HEAD: `bfa6fa43503d334b0b39f93808e8250f917f989a`; branch: `refs/heads/ai/m3-s3-golden-journey`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m3-s4`
- HEAD: `a33518275956ab6658ec51648d22951e09fa1e7c`; branch: `refs/heads/ai/m3-s4-durable-execution`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m4-s2-claude`
- HEAD: `1091153f1ad98c381df2e08345c7e70d9a442188`; branch: `refs/heads/ai/m4-s2-principal-session`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m4-s3`
- HEAD: `ca45e6579856cda64281ab22d767acb9acba1889`; branch: `refs/heads/feat/m4-s3-customer-memory-ui`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m4-s4-claude`
- HEAD: `83c1656980e40a1ffafb4fa3e72a06903302cce9`; branch: `refs/heads/ai/m4-s4-reasoned-suggestions`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m5-s1-voice`
- HEAD: `a614fa423b2a36ace93c294183f52b3207bed255`; branch: `refs/heads/ai/m5-s1-voice-eval`; dirty paths: `0`
### `/home/hamza/worktrees/elegance-m5-s2-voice-bridge`
- HEAD: `52d990eb759ff8ab74cf0ed43d366759e9954818`; branch: `refs/heads/ai/m5-s2-voice-bridge`; dirty paths: `0`
### `/home/hamza/worktrees/integration`
- HEAD: `1becedc1065296b412d76d4489bfa3c6eeb7d2da`; branch: `refs/heads/integration/local-complete`; dirty paths: `0`
### `/home/hamza/worktrees/m2-embeddinggemma2-promotion`
- HEAD: `15442712fa4799cfc9e3bfb889f77b1769beaffa`; branch: `refs/heads/m2-embeddinggemma2-promotion`; dirty paths: `0`
### `/home/hamza/worktrees/m2-semantic-review-packet-44c0d13`
- HEAD: `ab8f35558a8c6193758df593a263f69063937c13`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/worktrees/m3-canonical-actions`
- HEAD: `e061483083b3ecee380d16b0dde88e8759e40261`; branch: `refs/heads/ai/m3-canonical-action-compat`; dirty paths: `0`
### `/home/hamza/worktrees/m4-batch-a-backend`
- HEAD: `03c634cfc62c315fc0da30530ab4b765d99ef7d4`; branch: `refs/heads/ai/m4-batch-a-backend`; dirty paths: `0`
### `/home/hamza/worktrees/m4-batch-a-frontend`
- HEAD: `26a323d4edb73530369bf6b96bcf8e8b4150cbd8`; branch: `refs/heads/ai/m4-batch-a-frontend`; dirty paths: `0`
### `/home/hamza/worktrees/m4-batch-c-readiness`
- HEAD: `1641b683e15ee77f300a4f73f5af8a47600c82b7`; branch: `refs/heads/ai/m4-batch-c-readiness`; dirty paths: `0`
### `/home/hamza/worktrees/m4-c-qa`
- HEAD: `394e74828ec5a60b7fe1cb68c5db1d4c3b64056c`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/worktrees/m4-customer-auth-closeout-docs`
- HEAD: `77e9083766d7190ea9e5ade83f69d250cfb9bcd7`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/worktrees/m4-customer-auth-foundation`
- HEAD: `0626507dc8eef74cc3d55abf6bcc57eed31d340f`; branch: `refs/heads/ai/m4-customer-auth-foundation`; dirty paths: `0`
### `/home/hamza/worktrees/m4-customer-auth-frontend`
- HEAD: `edbf4a30d660e4a5c429de19a1d1b7a629157f71`; branch: `refs/heads/ai/m4-customer-auth-frontend`; dirty paths: `0`
### `/home/hamza/worktrees/m4-provider-gate`
- HEAD: `b4c5f58046cda2c848518a70425644ee80eee55e`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/worktrees/qa-recovery-5981e8a`
- HEAD: `5981e8ab45ccc311986082dbbbde060f9bffd08c`; branch: `(detached)`; dirty paths: `0`
### `/home/hamza/worktrees/reconciliation-20261106`
- HEAD: `fed9db4eb1ab82e9bf02c387c39c162b38111b7a`; branch: `refs/heads/chore/reconciliation-20261106`; dirty paths: `0`
### `/home/hamza/worktrees/staging`
- HEAD: `9eae7248e44976290689c845b143c86dac0173ca`; branch: `refs/heads/feat/redesign-on-staging`; dirty paths: `0`
### `/tmp/m4-batch-b-qa`
- HEAD: `d20f61dc481c27836318886e46e655c513c613a0`; branch: `(detached)`; dirty paths: `0`
- Metadata: `gitdir file points to non-existent location`

## Local branches: evidence-based classification

| Branch | SHA | Upstream | Worktree(s) | Classification | main | staging | staging-integration |
|---|---|---|---|---|---|---|---|
| `ai/batch-134-135-142` | `5981e8ab45cc` | `-<br>/home/hamza/worktrees/elegance-batch-134-135-142<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	114` | `A:N B:N T:N AB:19	110` | `A:N B:Y T:N AB:0	1` |
| `ai/batch-137-136` | `a0e651ba94eb` | `-<br>/home/hamza/worktrees/elegance-batch-137-136<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	114` | `A:N B:N T:N AB:19	110` | `A:N B:Y T:N AB:0	1` |
| `ai/batch-137-136-rework` | `e6814b6cc046` | `-<br>/home/hamza/worktrees/elegance-batch-137-136-rework<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	116` | `A:N B:N T:N AB:19	112` | `A:N B:Y T:N AB:0	3` |
| `ai/cos-batch-79-133` | `7a6629a56380` | `-<br>/home/hamza/worktrees/cos-batch-79-133<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	115` | `A:N B:N T:N AB:19	111` | `A:N B:Y T:N AB:0	2` |
| `ai/embedding-provider-contract` | `0cf5613ce1e4` | `origin/ai/embedding-provider-contract<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/embedding-provider-contract<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	35` | `A:N B:N T:N AB:23	35` | `A:Y B:N T:N AB:78	0` |
| `ai/embedding-synthetic-eval` | `c71ef03062f2` | `origin/ai/embedding-synthetic-eval<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/embedding-synthetic-eval<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	36` | `A:N B:N T:N AB:23	36` | `A:Y B:N T:N AB:77	0` |
| `ai/local-e5-v2-evidence` | `61a45a1e7061` | `origin/ai/local-e5-v2-evidence<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-e5-v2-evidence<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	38` | `A:N B:N T:N AB:23	38` | `A:Y B:N T:N AB:75	0` |
| `ai/local-ingestion-category-filter` | `61a45a1e7061` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-ingestion-category-filter<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	38` | `A:N B:N T:N AB:23	38` | `A:Y B:N T:N AB:75	0` |
| `ai/m1-s1-server-search` | `69b7b37edb01` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m1-s1-server-search<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	28` | `A:N B:N T:N AB:23	28` | `A:Y B:N T:N AB:85	0` |
| `ai/m1-s2-variant-filters` | `9df1a5be5a68` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m1-s2-variant-filters<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	30` | `A:N B:N T:N AB:23	30` | `A:Y B:N T:N AB:83	0` |
| `ai/m1-s3-admin-accounts` | `8c3fc4bef323` | `-<br>/home/hamza/worktrees/elegance-m1-s3-admin-accounts<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	32` | `A:N B:N T:N AB:23	32` | `A:Y B:N T:N AB:81	0` |
| `ai/m1-s4-enquiry-reference` | `7674dd255645` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls-m1-s4<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	34` | `A:N B:N T:N AB:23	34` | `A:Y B:N T:N AB:79	0` |
| `ai/m1-s5-backup-restore` | `63d33cacbec8` | `-<br>/home/hamza/worktrees/elegance-m1-s5-backup-restore<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	37` | `A:N B:N T:N AB:23	37` | `A:Y B:N T:N AB:76	0` |
| `ai/m2-s0-s1-foundation` | `f68d98b2fdfd` | `-<br>/home/hamza/worktrees/elegance-m2-s0-s1-foundation<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	38` | `A:N B:N T:N AB:23	38` | `A:Y B:N T:N AB:75	0` |
| `ai/m2-s2-pgvector-persistence` | `3be8b3fcaddf` | `-<br>/home/hamza/worktrees/elegance-m2-s2-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	40` | `A:N B:N T:N AB:23	40` | `A:Y B:N T:N AB:73	0` |
| `ai/m2-s3-hybrid-retrieval` | `75a28b357da6` | `-<br>/home/hamza/worktrees/elegance-m2-s3-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	42` | `A:N B:N T:N AB:23	42` | `A:Y B:N T:N AB:71	0` |
| `ai/m2-s3-hybrid-retrieval-claude-retry` | `117c3c7b5487` | `-<br>/home/hamza/worktrees/elegance-m2-s3-claude-retry<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	41` | `A:N B:N T:N AB:23	41` | `A:Y B:N T:N AB:72	0` |
| `ai/m2-s4-query-parser` | `d7ebaefa6790` | `-<br>/home/hamza/worktrees/elegance-m2-s4-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	43` | `A:N B:N T:N AB:23	43` | `A:Y B:N T:N AB:70	0` |
| `ai/m2-s5-claude` | `44c0d1374e6d` | `-<br>/home/hamza/worktrees/elegance-m2-s5-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	44` | `A:N B:N T:N AB:23	44` | `A:Y B:N T:N AB:69	0` |
| `ai/m3-canonical-action-compat` | `e061483083b3` | `-<br>/home/hamza/worktrees/m3-canonical-actions<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	12` | `A:Y B:N T:N AB:11	0` | `A:N B:N T:N AB:109	8` |
| `ai/m3-s1-validated-action-kernel` | `f8ce311a0845` | `-<br>/home/hamza/worktrees/elegance-m3-s1-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	46` | `A:N B:N T:N AB:23	46` | `A:Y B:N T:N AB:67	0` |
| `ai/m3-s2-streaming-assistant` | `d4e7e34988ad` | `-<br>/home/hamza/worktrees/elegance-m3-s2-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	49` | `A:N B:N T:N AB:23	49` | `A:Y B:N T:N AB:64	0` |
| `ai/m3-s3-golden-journey` | `bfa6fa43503d` | `-<br>/home/hamza/worktrees/elegance-m3-s3-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	50` | `A:N B:N T:N AB:23	50` | `A:Y B:N T:N AB:63	0` |
| `ai/m3-s4-durable-execution` | `a33518275956` | `-<br>/home/hamza/worktrees/elegance-m3-s4<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	51` | `A:N B:N T:N AB:23	51` | `A:Y B:N T:N AB:62	0` |
| `ai/m3-s5-action-registry` | `f466ebcf49e6` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m3-s5-action-registry<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	9` | `A:Y B:N T:N AB:14	0` | `A:N B:N T:N AB:109	5` |
| `ai/m4-batch-a-backend` | `03c634cfc62c` | `origin/staging<br>/home/hamza/worktrees/m4-batch-a-backend<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	24` | `A:N B:Y T:N AB:0	1` | `A:N B:N T:N AB:109	20` |
| `ai/m4-batch-a-frontend` | `26a323d4edb7` | `origin/staging<br>/home/hamza/worktrees/m4-batch-a-frontend<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	24` | `A:N B:Y T:N AB:0	1` | `A:N B:N T:N AB:109	20` |
| `ai/m4-batch-c-readiness` | `1641b683e15e` | `origin/staging<br>/home/hamza/worktrees/m4-batch-c-readiness<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	31` | `A:N B:Y T:N AB:0	8` | `A:N B:N T:N AB:109	27` |
| `ai/m4-customer-auth-foundation` | `0626507dc8ee` | `-<br>/home/hamza/worktrees/m4-customer-auth-foundation<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	57` | `A:N B:N T:N AB:23	57` | `A:Y B:N T:N AB:56	0` |
| `ai/m4-customer-auth-frontend` | `edbf4a30d660` | `-<br>/home/hamza/worktrees/m4-customer-auth-frontend<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	59` | `A:N B:N T:N AB:23	59` | `A:Y B:N T:N AB:54	0` |
| `ai/m4-s1-privacy-memory` | `55057d90cd2b` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls-m4-s1<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	52` | `A:N B:N T:N AB:23	52` | `A:Y B:N T:N AB:61	0` |
| `ai/m4-s2-principal-session` | `1091153f1ad9` | `-<br>/home/hamza/worktrees/elegance-m4-s2-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	53` | `A:N B:N T:N AB:23	53` | `A:Y B:N T:N AB:60	0` |
| `ai/m4-s4-reasoned-suggestions` | `83c1656980e4` | `-<br>/home/hamza/worktrees/elegance-m4-s4-claude<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	56` | `A:N B:N T:N AB:23	56` | `A:Y B:N T:N AB:57	0` |
| `ai/m5-s1-voice-eval` | `a614fa423b2a` | `-<br>/home/hamza/worktrees/elegance-m5-s1-voice<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	57` | `A:N B:N T:N AB:23	57` | `A:Y B:N T:N AB:56	0` |
| `ai/m5-s2-voice-bridge` | `52d990eb759f` | `-<br>/home/hamza/worktrees/elegance-m5-s2-voice-bridge<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	59` | `A:N B:N T:N AB:23	59` | `A:Y B:N T:N AB:54	0` |
| `ai/openai-embedding-eval` | `82c034de3e48` | `origin/ai/openai-embedding-eval<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/openai-embedding-eval<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	37` | `A:N B:N T:N AB:23	37` | `A:Y B:N T:N AB:76	0` |
| `ai/phase-0-foundations` | `3003eba6835e` | `origin/ai/phase-0-foundations<br>/home/hamza/GitHub-Repositories/Elegance-Shawls<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	28` | `A:N B:N T:N AB:23	28` | `A:N B:N T:N AB:86	1` |
| `ai/phase-1-attributes` | `64fc22c7aa93` | `origin/ai/phase-1-attributes<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s2-attributes<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	29` | `A:N B:N T:N AB:23	29` | `A:Y B:N T:N AB:84	0` |
| `ai/phase-1-enrichment` | `976eb0ae5ab4` | `origin/ai/phase-1-enrichment<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s3-enrichment<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	30` | `A:N B:N T:N AB:23	30` | `A:Y B:N T:N AB:83	0` |
| `ai/phase-1-enrichment-admin-review` | `40653fe5ef84` | `origin/ai/phase-1-enrichment-admin-review<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s3-admin-review<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	31` | `A:N B:N T:N AB:23	31` | `A:Y B:N T:N AB:82	0` |
| `ai/phase-1-retrieval` | `f1e786bb5883` | `origin/ai/phase-1-retrieval<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s1-retrieval<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	28` | `A:N B:N T:N AB:23	28` | `A:Y B:N T:N AB:85	0` |
| `ai/phase-1-s4a-representations` | `843a22857999` | `origin/ai/phase-1-s4a-representations<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4a-representations<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	32` | `A:N B:N T:N AB:23	32` | `A:Y B:N T:N AB:81	0` |
| `ai/phase-1-s4b-embeddings` | `0719769bdc6c` | `origin/ai/phase-1-s4b-embeddings<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4b-embeddings<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	33` | `A:N B:N T:N AB:23	33` | `A:Y B:N T:N AB:80	0` |
| `ai/phase-1-s4c-hybrid` | `2220811411c5` | `origin/ai/phase-1-s4c-hybrid<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/p1-s4c-hybrid<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	34` | `A:N B:N T:N AB:23	34` | `A:Y B:N T:N AB:79	0` |
| `ai/reviewed-synthetic-benchmark-v2` | `24346e8c4f0a` | `origin/ai/reviewed-synthetic-benchmark-v2<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/reviewed-synthetic-benchmark-v2<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	37` | `A:N B:N T:N AB:23	37` | `A:Y B:N T:N AB:76	0` |
| `ai/synonym-error-analysis` | `b693d7733fe3` | `origin/ai/synonym-error-analysis<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/semantic-error-analysis<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	37` | `A:N B:N T:N AB:23	37` | `A:Y B:N T:N AB:76	0` |
| `backup/ai-phase-0-foundations-pre-merge` | `1b7aa8765acd` | `-<br>-<br>recovery/archive ref; retain` | `A:Y B:Y T:Y AB:0	0` | `A:Y B:N T:N AB:23	0` | `A:Y B:N T:N AB:113	0` |
| `chore/m3-staging-promotion` | `f466ebcf49e6` | `origin/staging<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/m3-staging-promotion<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	9` | `A:Y B:N T:N AB:14	0` | `A:N B:N T:N AB:109	5` |
| `chore/reconciliation-20261106` | `fed9db4eb1ab` | `origin/staging-integration<br>/home/hamza/worktrees/reconciliation-20261106<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	115` | `A:N B:N T:N AB:19	111` | `A:N B:Y T:N AB:0	2` |
| `docs/issue-143-recovery` | `13264b2cbd76` | `origin/staging-integration<br>/home/hamza/worktrees/elegance-143<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	116` | `A:N B:N T:N AB:19	112` | `A:N B:Y T:N AB:0	3` |
| `docs/three-branch-workflow` | `fc298820ad95` | `origin/docs/three-branch-workflow<br>-<br>review candidate; no deletion without PR/ancestry proof` | `A:N B:Y T:N AB:0	115` | `A:N B:N T:N AB:19	111` | `A:N B:Y T:N AB:0	2` |
| `feat/elegance-assistant-ui-ai-sdk` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls-chat-assistant-ui<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `feat/m4-s3-customer-memory-ui` | `ca45e6579856` | `-<br>/home/hamza/worktrees/elegance-m4-s3<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	54` | `A:N B:N T:N AB:23	54` | `A:Y B:N T:N AB:59	0` |
| `feat/redesign-on-staging` | `9eae7248e449` | `-<br>/home/hamza/worktrees/staging<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	25` | `A:N B:Y T:N AB:0	2` | `A:N B:N T:N AB:109	21` |
| `fix/embedding-consolidation` | `63c3fc60777b` | `origin/fix/embedding-consolidation<br>-<br>review candidate; no deletion without PR/ancestry proof` | `A:N B:Y T:N AB:0	116` | `A:N B:N T:N AB:19	112` | `A:N B:Y T:N AB:0	3` |
| `fix/render-asyncpg-url` | `ac96a2bd033b` | `origin/main<br>-<br>review candidate; no deletion without PR/ancestry proof` | `A:N B:Y T:N AB:0	2` | `A:N B:N T:N AB:22	1` | `A:Y B:N T:N AB:111	0` |
| `integration/local-complete` | `1becedc10652` | `origin/integration/local-complete<br>/home/hamza/worktrees/integration<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	72` | `A:N B:N T:N AB:23	72` | `A:Y B:N T:N AB:41	0` |
| `m2-embeddinggemma2-promotion` | `15442712fa47` | `origin/staging<br>/home/hamza/worktrees/m2-embeddinggemma2-promotion<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	32` | `A:N B:Y T:N AB:0	9` | `A:N B:N T:N AB:109	28` |
| `m4-batch-a` | `6d4dcff6d281` | `origin/staging<br>/home/hamza/qa-m1-s4-clean<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	28` | `A:N B:Y T:N AB:0	5` | `A:N B:N T:N AB:109	24` |
| `main` | `1b7aa8765acd` | `origin/main<br>-<br>protected canonical ref; retain` | `A:Y B:Y T:Y AB:0	0` | `A:Y B:N T:N AB:23	0` | `A:Y B:N T:N AB:113	0` |
| `promo/m2-m3-staging-20261105` | `82b9a39a4dd9` | `origin/staging<br>-<br>review candidate; no deletion without PR/ancestry proof` | `A:N B:Y T:N AB:0	14` | `A:N B:N T:N AB:15	6` | `A:N B:N T:N AB:109	10` |
| `staging` | `7e319d5348dc` | `origin/staging<br>-<br>protected canonical ref; retain` | `A:N B:Y T:N AB:0	23` | `A:Y B:Y T:Y AB:0	0` | `A:N B:N T:N AB:109	19` |
| `staging-e5-semantic-activation-local` | `0cd3224528c9` | `origin/staging/e5-semantic-activation<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-ai-search-integration<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	13` | `A:N B:N T:N AB:19	9` | `A:N B:N T:N AB:106	6` |
| `staging-integration` | `af040762c7bf` | `origin/staging-integration<br>-<br>protected canonical ref; retain` | `A:N B:Y T:N AB:0	113` | `A:N B:N T:N AB:19	109` | `A:Y B:Y T:Y AB:0	0` |
| `worktree-docs-status-correction` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/docs-status-correction<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `worktree-local-multilingual-e5` | `c71ef03062f2` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.claude/worktrees/local-multilingual-e5<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	36` | `A:N B:N T:N AB:23	36` | `A:Y B:N T:N AB:77	0` |
| `wt/t_1b57d00f` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_1b57d00f<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_209ec7cb` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_209ec7cb<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_2749cbd6` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_2749cbd6<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_2b45c806` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_2b45c806<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_31294d42` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_31294d42<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_345e5309` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_345e5309<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_34b3f1b3` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_34b3f1b3<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_6b56fbc5` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_6b56fbc5<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_7b0e9ae9` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_7b0e9ae9<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_89e0dc03` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_89e0dc03<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_92e4697d` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_92e4697d<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_aa03e4de` | `77f4fb50a4ae` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_aa03e4de<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	28` | `A:N B:N T:N AB:23	28` | `A:N B:N T:N AB:86	1` |
| `wt/t_b3172993` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_b3172993<br>dirty worktree; retain and do not rewrite` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_b6ca01ab` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_b6ca01ab<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_bbfdf061` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_bbfdf061<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_c09f05ba` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c09f05ba<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_c4b434d4` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c4b434d4<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_c6458d03` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_c6458d03<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_d6e82c9c` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_d6e82c9c<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |
| `wt/t_e14699d9` | `ecf690bb7778` | `-<br>/home/hamza/GitHub-Repositories/Elegance-Shawls/.worktrees/t_e14699d9<br>active/linked worktree; retain pending owner confirmation` | `A:N B:Y T:N AB:0	27` | `A:N B:N T:N AB:23	27` | `A:Y B:N T:N AB:86	0` |

## Remote refs

| Ref | SHA |
|---|---|
| `origin/HEAD` | `283b27eee90533435ef3b2e28e6a3823ee1c5d23` |
| `origin/ai/phase-0-foundations` | `3003eba6835e424fd4a9f37b23ad510d0491b161` |
| `origin/dependabot/npm_and_yarn/apps/frontend/eslint-10.13.0` | `8dbbe0813008f7cc60acd8984a6a39607b42f4e7` |
| `origin/dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-fc91edfa29` | `9135c80327d2e1f40c3c76b1aa0602430759a75b` |
| `origin/dependabot/npm_and_yarn/apps/frontend/lucide-react-1.63.0` | `89956be346896309e592a024295828a088b3e33a` |
| `origin/dependabot/npm_and_yarn/apps/frontend/types/node-26.6.6` | `cb44b5d8b5923b2af79038a7fce03fed1d08a04d` |
| `origin/dependabot/npm_and_yarn/apps/frontend/vitest-5.0.5` | `4fd0eb6d0d19adcd5af23e92e0f602735c957158` |
| `origin/dependabot/pip/apps/backend/pydantic-2.14.1` | `a71895fe399eb69a7664a914b5b2995859ab0c5a` |
| `origin/dependabot/pip/apps/backend/pydantic-settings-2.16.2` | `3ea2b4d3cb380759341b5691e89858d2c0ebfc42` |
| `origin/dependabot/pip/apps/backend/redis-8.1.0` | `306916a6b555a0e8e7f0f2a27bc5fa623cdced69` |
| `origin/main` | `283b27eee90533435ef3b2e28e6a3823ee1c5d23` |
| `origin/staging` | `b4c5f58046cda2c848518a70425644ee80eee55e` |
| `origin/staging-integration` | `fed9db4eb1ab82e9bf02c387c39c162b38111b7a` |

## GitHub references

### Pull requests (all states)
```json
[
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/eslint-10.13.0",
    "headRefOid": "8dbbe0813008f7cc60acd8984a6a39607b42f4e7",
    "isDraft": false,
    "mergeCommit": null,
    "number": 155,
    "state": "OPEN",
    "title": "chore(deps-dev): bump eslint from 9.39.5 to 10.13.0 in /apps/frontend",
    "updatedAt": "2026-11-01T01:37:21Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/155"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/vitest-5.0.5",
    "headRefOid": "4fd0eb6d0d19adcd5af23e92e0f602735c957158",
    "isDraft": false,
    "mergeCommit": null,
    "number": 154,
    "state": "OPEN",
    "title": "chore(deps-dev): bump vitest from 4.1.12 to 5.0.5 in /apps/frontend",
    "updatedAt": "2026-11-01T01:36:17Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/154"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/lucide-react-1.63.0",
    "headRefOid": "89956be346896309e592a024295828a088b3e33a",
    "isDraft": false,
    "mergeCommit": null,
    "number": 153,
    "state": "OPEN",
    "title": "chore(deps): bump lucide-react from 0.562.0 to 1.63.0 in /apps/frontend",
    "updatedAt": "2026-11-01T01:36:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/153"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/types/node-26.6.6",
    "headRefOid": "cb44b5d8b5923b2af79038a7fce03fed1d08a04d",
    "isDraft": false,
    "mergeCommit": null,
    "number": 152,
    "state": "OPEN",
    "title": "chore(deps-dev): bump @types/node from 20.19.27 to 26.6.6 in /apps/frontend",
    "updatedAt": "2026-11-01T01:35:04Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/152"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-fc91edfa29",
    "headRefOid": "9135c80327d2e1f40c3c76b1aa0602430759a75b",
    "isDraft": false,
    "mergeCommit": null,
    "number": 151,
    "state": "OPEN",
    "title": "chore(deps): bump the frontend-minor-patch group in /apps/frontend with 8 updates",
    "updatedAt": "2026-11-01T01:33:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/151"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pydantic-settings-2.16.2",
    "headRefOid": "3ea2b4d3cb380759341b5691e89858d2c0ebfc42",
    "isDraft": false,
    "mergeCommit": null,
    "number": 150,
    "state": "OPEN",
    "title": "chore(deps): bump pydantic-settings from 2.14.2 to 2.16.2 in /apps/backend",
    "updatedAt": "2026-11-01T01:32:07Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/150"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pydantic-2.14.1",
    "headRefOid": "a71895fe399eb69a7664a914b5b2995859ab0c5a",
    "isDraft": false,
    "mergeCommit": null,
    "number": 149,
    "state": "OPEN",
    "title": "chore(deps): bump pydantic from 2.13.4 to 2.14.1 in /apps/backend",
    "updatedAt": "2026-11-01T01:30:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/149"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/redis-8.1.0",
    "headRefOid": "306916a6b555a0e8e7f0f2a27bc5fa623cdced69",
    "isDraft": false,
    "mergeCommit": null,
    "number": 148,
    "state": "OPEN",
    "title": "chore(deps): bump redis from 5.3.1 to 8.1.0 in /apps/backend",
    "updatedAt": "2026-11-01T01:27:36Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/148"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "staging",
    "headRefName": "staging-integration",
    "headRefOid": "fed9db4eb1ab82e9bf02c387c39c162b38111b7a",
    "isDraft": false,
    "mergeCommit": {
      "oid": "581fad46fa7317a7f0ee0bd8b0161ec7cac5f3a0"
    },
    "number": 132,
    "state": "MERGED",
    "title": "release: promote staging-integration fed9db4 to staging",
    "updatedAt": "2026-10-31T17:21:14Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/132"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "staging-integration",
    "headRefName": "docs/three-branch-workflow",
    "headRefOid": "fc298820ad95f746c0412a9ba2eb700721f97df5",
    "isDraft": false,
    "mergeCommit": {
      "oid": "fed9db4eb1ab82e9bf02c387c39c162b38111b7a"
    },
    "number": 131,
    "state": "MERGED",
    "title": "docs: adopt three-branch workflow (staging-integration, staging, main)",
    "updatedAt": "2026-10-31T17:12:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/131"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "staging-integration",
    "headRefName": "fix/embedding-consolidation",
    "headRefOid": "63c3fc60777b682e95725f9db16c1bf5f42c5200",
    "isDraft": false,
    "mergeCommit": {
      "oid": "c1d78d296d54904d6bdf6f0343babc88e1ac1fc9"
    },
    "number": 130,
    "state": "MERGED",
    "title": "Consolidate embeddings on one pipeline and verify the 0009 to 0015 migration chain (#129)",
    "updatedAt": "2026-10-31T16:11:03Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/130"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "chore/pin-e5-evaluated-snapshot",
    "headRefOid": "4e6860dc1d345af0a2ed90a0d792e3908b7b619a",
    "isDraft": false,
    "mergeCommit": {
      "oid": "283b27eee90533435ef3b2e28e6a3823ee1c5d23"
    },
    "number": 128,
    "state": "MERGED",
    "title": "docs(ai): pin reproducible E5 evaluation snapshot",
    "updatedAt": "2026-10-30T09:48:01Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/128"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "fix/staging-migrations",
    "headRefOid": "252340a8dcf383cb8bdc97d14c4f7bbe230053b4",
    "isDraft": false,
    "mergeCommit": {
      "oid": "95431c5a86b96bce5c5d9b7b8ea8266e50b7ddd3"
    },
    "number": 127,
    "state": "MERGED",
    "title": "ops: run optional migrations before staging startup",
    "updatedAt": "2026-10-30T09:19:19Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/127"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "fix/render-asyncpg-url",
    "headRefOid": "ac96a2bd033b9669a21dcde00d96c3c8b9a1204e",
    "isDraft": false,
    "mergeCommit": {
      "oid": "931d58932dbba8a921c030f98d593bbc5701b05b"
    },
    "number": 126,
    "state": "MERGED",
    "title": "fix: normalize Render PostgreSQL URL for asyncpg",
    "updatedAt": "2026-10-30T09:08:24Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/126"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "ai/local-ai-search-integration",
    "headRefOid": "6cdf9f2df42248b9991f4ba1a2bfcf230eefb0f8",
    "isDraft": false,
    "mergeCommit": {
      "oid": "7777ccc2c22e969318fca99c3c5694d9187a5ed3"
    },
    "number": 125,
    "state": "MERGED",
    "title": "feat(ai): prepare local search and catalogue controls for staging",
    "updatedAt": "2026-10-30T08:38:52Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/125"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/reviewed-synthetic-benchmark-v2",
    "headRefName": "ai/local-e5-v2-evidence",
    "headRefOid": "61a45a1e7061e016ea7583e893486c77701f2278",
    "isDraft": false,
    "mergeCommit": null,
    "number": 124,
    "state": "CLOSED",
    "title": "feat(ai): package reproducible local E5 evaluation",
    "updatedAt": "2026-10-31T17:08:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/124"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/embedding-synthetic-eval",
    "headRefName": "ai/reviewed-synthetic-benchmark-v2",
    "headRefOid": "24346e8c4f0af2f1cae98c5d9abdcaccad3d8f13",
    "isDraft": false,
    "mergeCommit": null,
    "number": 123,
    "state": "CLOSED",
    "title": "test(ai): add reviewed synthetic embedding benchmark v2",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/123"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/embedding-synthetic-eval",
    "headRefName": "ai/synonym-error-analysis",
    "headRefOid": "b693d7733fe31879ea46d091a69b764b78cff580",
    "isDraft": false,
    "mergeCommit": null,
    "number": 122,
    "state": "CLOSED",
    "title": "test(ai): diagnose synthetic synonym representation gaps",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/122"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/embedding-synthetic-eval",
    "headRefName": "ai/openai-embedding-eval",
    "headRefOid": "82c034de3e4838e1feac2d2b7ccd1f3d701b8292",
    "isDraft": false,
    "mergeCommit": null,
    "number": 121,
    "state": "CLOSED",
    "title": "feat(ai): add bounded OpenAI embedding evaluation",
    "updatedAt": "2026-10-31T17:08:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/121"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/embedding-provider-contract",
    "headRefName": "ai/embedding-synthetic-eval",
    "headRefOid": "c71ef03062f2bcba535e53071e61429ebcf020e4",
    "isDraft": false,
    "mergeCommit": null,
    "number": 120,
    "state": "CLOSED",
    "title": "test(ai): add synthetic embedding evaluation gate",
    "updatedAt": "2026-10-31T17:08:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/120"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-s4c-hybrid",
    "headRefName": "ai/embedding-provider-contract",
    "headRefOid": "0cf5613ce1e40c7b6ec3ca36cbeedd8137ecfc4f",
    "isDraft": false,
    "mergeCommit": null,
    "number": 119,
    "state": "CLOSED",
    "title": "feat(ai): add explicit embedding provider contracts",
    "updatedAt": "2026-10-31T17:08:11Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/119"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-s4b-embeddings",
    "headRefName": "ai/phase-1-s4c-hybrid",
    "headRefOid": "2220811411c55ea367abb4b44deab460f99dfb54",
    "isDraft": false,
    "mergeCommit": null,
    "number": 118,
    "state": "CLOSED",
    "title": "feat(search): add hybrid RRF retrieval",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/118"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-s4a-representations",
    "headRefName": "ai/phase-1-s4b-embeddings",
    "headRefOid": "0719769bdc6cabf5537d6578f7ad162764457ee4",
    "isDraft": false,
    "mergeCommit": null,
    "number": 117,
    "state": "CLOSED",
    "title": "feat(ai): add pgvector embedding persistence",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/117"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-enrichment-admin-review",
    "headRefName": "ai/phase-1-s4a-representations",
    "headRefOid": "843a22857999470ab96a64497f2b0fb64d37321a",
    "isDraft": false,
    "mergeCommit": null,
    "number": 116,
    "state": "CLOSED",
    "title": "feat(ai): add embedding representation contracts",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/116"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-enrichment",
    "headRefName": "ai/phase-1-enrichment-admin-review",
    "headRefOid": "40653fe5ef84c8eb6b58785cd526986f1866f8d4",
    "isDraft": false,
    "mergeCommit": null,
    "number": 115,
    "state": "CLOSED",
    "title": "feat(admin): review staged enrichment suggestions",
    "updatedAt": "2026-10-31T17:08:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/115"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "ai/phase-1-attributes",
    "headRefName": "ai/phase-1-enrichment",
    "headRefOid": "976eb0ae5ab42af7bf059752430f3775d2795d9c",
    "isDraft": false,
    "mergeCommit": null,
    "number": 114,
    "state": "CLOSED",
    "title": "feat(ai): add staged enrichment suggestions",
    "updatedAt": "2026-10-31T17:08:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/114"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "docs/plans-folder",
    "headRefOid": "bd8471045f8109925817f9ecc21308f616908afe",
    "isDraft": false,
    "mergeCommit": {
      "oid": "1b7aa8765acd8b2405f2e37aa77ceecf630c636c"
    },
    "number": 91,
    "state": "MERGED",
    "title": "docs: add plans folder for system and store planning",
    "updatedAt": "2026-10-29T09:03:00Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/91"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "chore/remove-claude-coauthor",
    "headRefOid": "23e33e2b77f04365e48bb2a369dafe074b202b78",
    "isDraft": false,
    "mergeCommit": {
      "oid": "23e33e2b77f04365e48bb2a369dafe074b202b78"
    },
    "number": 90,
    "state": "MERGED",
    "title": "chore: remove AI co-author attribution from P0 merge commit",
    "updatedAt": "2026-10-28T07:33:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/90"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "p0/integration-local-qa",
    "headRefOid": "7cbb67cba5fe8a95c02552e49b29e23a50231b81",
    "isDraft": false,
    "mergeCommit": {
      "oid": "bbfe335bfd6e90ab873e034932403c8c1f1967c1"
    },
    "number": 89,
    "state": "MERGED",
    "title": "P0 integration: admin auth, checkout correctness, hardened stack and live acceptance",
    "updatedAt": "2026-10-28T06:25:17Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/89"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "p0/68-pymongo-cve-106435",
    "headRefOid": "689bd23a7c6288acf2a07e3cb0826e60a59a3306",
    "isDraft": false,
    "mergeCommit": {
      "oid": "e8946f370933c9751d5d4044e47bcff7b07b1475"
    },
    "number": 88,
    "state": "MERGED",
    "title": "fix(p0-68): patch PyMongo CVE-2026-106435",
    "updatedAt": "2026-10-28T04:37:00Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/88"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "p0/66-admin-proxy-auth",
    "headRefOid": "06ecdaf69aac3837876bdcbc41526e6689fa5b6f",
    "isDraft": true,
    "mergeCommit": null,
    "number": 87,
    "state": "CLOSED",
    "title": "fix(p0-66): enforce admin proxy origin checks",
    "updatedAt": "2026-10-29T08:13:47Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/87"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "docs/staging-first-release-workflow",
    "headRefOid": "6d4ae63dfe7dc196de7b7a6553a96833832b5ac0",
    "isDraft": false,
    "mergeCommit": null,
    "number": 85,
    "state": "CLOSED",
    "title": "docs: document staging-first release workflow and baseline",
    "updatedAt": "2026-10-31T17:08:14Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/85"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "fix/production-deployment-readiness",
    "headRefOid": "31be4bcf773e88a051a14f800899cf843fc00477",
    "isDraft": false,
    "mergeCommit": {
      "oid": "eb43cec4ef9e560b4a7c57bf6324739c0a696e18"
    },
    "number": 84,
    "state": "MERGED",
    "title": "Secure admin API proxy and prepare production deployment",
    "updatedAt": "2026-10-29T08:13:47Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/84"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-450da7a7c9",
    "headRefOid": "b17eb61542620dd40cf3908aa472785dbc225b67",
    "isDraft": false,
    "mergeCommit": null,
    "number": 65,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 10 updates",
    "updatedAt": "2026-10-29T08:13:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/65"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-38bd30896b",
    "headRefOid": "3d41429f005242bbe2e1792b749222ab05109509",
    "isDraft": false,
    "mergeCommit": null,
    "number": 64,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 9 updates",
    "updatedAt": "2026-09-20T01:23:22Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/64"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-7d4f76aa6b",
    "headRefOid": "169b6938623bb9587aa351fb44612bdac404ad61",
    "isDraft": false,
    "mergeCommit": null,
    "number": 63,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 10 updates",
    "updatedAt": "2026-09-13T01:24:15Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/63"
  },
  {
    "author": {
      "id": "U_kgDOCcDq9Q",
      "is_bot": false,
      "login": "Muhammad-Hamza-Khan-03",
      "name": "Muhammad Hamza Khan"
    },
    "baseRefName": "main",
    "headRefName": "fix/admin-product-management-screens",
    "headRefOid": "c32ddaafd9ec051d3b70279f6fd1dc63583d6873",
    "isDraft": false,
    "mergeCommit": {
      "oid": "b40b1716a4ecca310b22fe556ab4ef617e9f8716"
    },
    "number": 62,
    "state": "MERGED",
    "title": "feat: add admin product management screens",
    "updatedAt": "2026-08-23T17:49:16Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/62"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-df068399dc",
    "headRefOid": "5516fce0b0318ee225f63a8c89555e229ef02b85",
    "isDraft": false,
    "mergeCommit": null,
    "number": 61,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 11 updates",
    "updatedAt": "2026-08-23T17:52:06Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/61"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/python-dotenv-1.2.3",
    "headRefOid": "bc598d5c2f8ddb43fc7f4b78cf4fabcb34f5a37a",
    "isDraft": false,
    "mergeCommit": null,
    "number": 60,
    "state": "CLOSED",
    "title": "chore(deps): bump python-dotenv from 1.2.2 to 1.2.3 in /apps/backend",
    "updatedAt": "2026-10-28T07:39:23Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/60"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/uvicorn-0.52.4",
    "headRefOid": "97d7e68540af1d1b467a647330ef388089a1f0e7",
    "isDraft": false,
    "mergeCommit": null,
    "number": 59,
    "state": "CLOSED",
    "title": "chore(deps): bump uvicorn from 0.51.0 to 0.52.4 in /apps/backend",
    "updatedAt": "2026-10-28T07:39:25Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/59"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-11b15e0c6b",
    "headRefOid": "7e08d92a6f7bb889311d88912dbf352a63b756aa",
    "isDraft": false,
    "mergeCommit": null,
    "number": 31,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 10 updates",
    "updatedAt": "2026-08-23T01:23:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/31"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pydantic-settings-2.15.0",
    "headRefOid": "34ccd0f66bb4aa2bb301272169a70df6949f07e9",
    "isDraft": false,
    "mergeCommit": null,
    "number": 30,
    "state": "CLOSED",
    "title": "chore(deps): bump pydantic-settings from 2.14.2 to 2.15.0 in /apps/backend",
    "updatedAt": "2026-10-28T07:39:28Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/30"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-be2ea01717",
    "headRefOid": "d0bc33a1c3d2eca5193aeaa515395a15e91c2e47",
    "isDraft": false,
    "mergeCommit": null,
    "number": 29,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 9 updates",
    "updatedAt": "2026-08-16T01:23:22Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/29"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/uvicorn-0.52.1",
    "headRefOid": "09835ee9e3f9f5de0774647a588cc5d3a68d12d9",
    "isDraft": false,
    "mergeCommit": null,
    "number": 28,
    "state": "CLOSED",
    "title": "chore(deps): bump uvicorn from 0.51.0 to 0.52.1 in /apps/backend",
    "updatedAt": "2026-08-23T01:22:51Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/28"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/uvicorn-0.52.0",
    "headRefOid": "935b3516304e20c91513e5b3edf93c2251e7a563",
    "isDraft": false,
    "mergeCommit": null,
    "number": 27,
    "state": "CLOSED",
    "title": "chore(deps): bump uvicorn from 0.51.0 to 0.52.0 in /apps/backend",
    "updatedAt": "2026-08-09T01:22:53Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/27"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/fastapi-0.141.1",
    "headRefOid": "6663db6a90711fa27d3f3ee222f6def74bc15145",
    "isDraft": false,
    "mergeCommit": null,
    "number": 26,
    "state": "CLOSED",
    "title": "chore(deps): bump fastapi from 0.139.2 to 0.141.1 in /apps/backend",
    "updatedAt": "2026-10-30T08:39:55Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/26"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/actions/upload-artifact-7",
    "headRefOid": "465a13e7c093c89d1c1a04540fd978e4a3ca40bf",
    "isDraft": false,
    "mergeCommit": null,
    "number": 25,
    "state": "CLOSED",
    "title": "chore(deps): bump actions/upload-artifact from 4 to 7",
    "updatedAt": "2026-10-28T07:39:33Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/25"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/eslint-10.8.0",
    "headRefOid": "707427813ebf0dfdba8ec11d640198920688ab69",
    "isDraft": false,
    "mergeCommit": null,
    "number": 22,
    "state": "CLOSED",
    "title": "chore(deps-dev): bump eslint from 9.39.5 to 10.8.1 in /apps/frontend",
    "updatedAt": "2026-10-28T07:39:36Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/22"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-48a405c8e8",
    "headRefOid": "9ca2035d39dbbdbcd23cb9af8ac1b9c4c7656223",
    "isDraft": false,
    "mergeCommit": null,
    "number": 21,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group in /apps/frontend with 7 updates",
    "updatedAt": "2026-08-09T01:23:26Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/21"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/fastapi-0.140.0",
    "headRefOid": "2644201172701fa55b125266a8cc5a7b0a498429",
    "isDraft": false,
    "mergeCommit": null,
    "number": 20,
    "state": "CLOSED",
    "title": "chore(deps): bump fastapi from 0.139.2 to 0.140.0 in /apps/backend",
    "updatedAt": "2026-08-02T01:22:48Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/20"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pymongo-4.17.0",
    "headRefOid": "496716e5cba33ebadb4c5c40974dd0ee25c8b8b0",
    "isDraft": false,
    "mergeCommit": null,
    "number": 19,
    "state": "CLOSED",
    "title": "chore(deps): bump pymongo from 4.15.5 to 4.17.0 in /apps/backend",
    "updatedAt": "2026-10-30T08:39:54Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/19"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/fastapi-0.139.2",
    "headRefOid": "da0b29a2173b5deaba87d482d84a698267944941",
    "isDraft": false,
    "mergeCommit": {
      "oid": "3dfcf7e51db0c87292bc87e19220753bd1d8adcf"
    },
    "number": 18,
    "state": "MERGED",
    "title": "chore(deps): bump fastapi from 0.139.0 to 0.139.2 in /apps/backend",
    "updatedAt": "2026-07-21T05:25:09Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/18"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/uvicorn-0.51.0",
    "headRefOid": "bf9cce1b652bb6fd172b98961234ae9a69a10c24",
    "isDraft": false,
    "mergeCommit": {
      "oid": "656d62242f15b2d4cf549d0e980aac077b3c6624"
    },
    "number": 17,
    "state": "MERGED",
    "title": "chore(deps): bump uvicorn from 0.38.0 to 0.51.0 in /apps/backend",
    "updatedAt": "2026-07-21T05:25:34Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/17"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-4ec8632ff0",
    "headRefOid": "204df5442ed77c8624d8365d586d368f04115c6b",
    "isDraft": false,
    "mergeCommit": {
      "oid": "0889026aafc6c5bf78789cece56ec06bef2572cb"
    },
    "number": 16,
    "state": "MERGED",
    "title": "chore(deps): bump the frontend-minor-patch group across 1 directory with 7 updates",
    "updatedAt": "2026-07-21T05:26:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/16"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/types/node-26.1.1",
    "headRefOid": "936bc154c198eef355db46643de8ea9097b9afac",
    "isDraft": false,
    "mergeCommit": null,
    "number": 15,
    "state": "CLOSED",
    "title": "chore(deps-dev): bump @types/node from 20.19.27 to 26.1.1 in /apps/frontend",
    "updatedAt": "2026-07-21T05:53:25Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/15"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/lucide-react-1.24.0",
    "headRefOid": "2cc5a0af36a4c794cf68990a1151f1ae6875a556",
    "isDraft": false,
    "mergeCommit": {
      "oid": "47809953a1cddba0cda19cbb3a5b01b81a3690f0"
    },
    "number": 14,
    "state": "MERGED",
    "title": "chore(deps): bump lucide-react from 0.562.0 to 1.25.0 in /apps/frontend",
    "updatedAt": "2026-07-21T05:37:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/14"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/typescript-7.0.2",
    "headRefOid": "3395eb157c46e035d5aa7712e78c6d86aeca4e9c",
    "isDraft": false,
    "mergeCommit": null,
    "number": 13,
    "state": "CLOSED",
    "title": "chore(deps-dev): bump typescript from 5.9.3 to 7.0.2 in /apps/frontend",
    "updatedAt": "2026-07-21T05:53:47Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/13"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/eslint-10.7.0",
    "headRefOid": "4bbe18ef1d8468ced5b5ea780daab7d07f9d22bf",
    "isDraft": false,
    "mergeCommit": null,
    "number": 12,
    "state": "CLOSED",
    "title": "chore(deps-dev): bump eslint from 9.39.5 to 10.7.0 in /apps/frontend",
    "updatedAt": "2026-07-21T05:53:52Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/12"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-f1654f54ba",
    "headRefOid": "0e5774b360821389e8ed95f5795f2e947720f1f1",
    "isDraft": false,
    "mergeCommit": null,
    "number": 11,
    "state": "CLOSED",
    "title": "chore(deps): bump the frontend-minor-patch group in /apps/frontend with 9 updates",
    "updatedAt": "2026-07-12T17:45:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/11"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pytest-asyncio-1.4.0",
    "headRefOid": "c66c9b1ec0d770432ca0d0d73e7eb5aed2fc8613",
    "isDraft": false,
    "mergeCommit": {
      "oid": "e2499e1caf98e9fa8a319b310201c9472e170c94"
    },
    "number": 10,
    "state": "MERGED",
    "title": "chore(deps-dev): bump pytest-asyncio from 1.3.0 to 1.4.0 in /apps/backend",
    "updatedAt": "2026-07-21T05:28:59Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/10"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pydantic-2.13.4",
    "headRefOid": "09e86e12639ea1918eecfc9bd75f061d43605164",
    "isDraft": false,
    "mergeCommit": {
      "oid": "0cd42506e5f2bbb7c4b7087f3448c69410975537"
    },
    "number": 9,
    "state": "MERGED",
    "title": "chore(deps): bump pydantic from 2.12.5 to 2.13.4 in /apps/backend",
    "updatedAt": "2026-07-21T05:29:08Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/9"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/fastapi-0.139.0",
    "headRefOid": "3ba881ba93fa48742543d68bedfada80223a7d91",
    "isDraft": false,
    "mergeCommit": null,
    "number": 8,
    "state": "CLOSED",
    "title": "chore(deps): bump fastapi from 0.124.0 to 0.139.0 in /apps/backend",
    "updatedAt": "2026-07-12T15:51:43Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/8"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/actions/checkout-7",
    "headRefOid": "ba982d1677721cdf1e37172df930d768ba6e8eec",
    "isDraft": false,
    "mergeCommit": {
      "oid": "a953c2ae243f8499b1238458190386300edb73e1"
    },
    "number": 7,
    "state": "MERGED",
    "title": "chore(deps): bump actions/checkout from 4 to 7",
    "updatedAt": "2026-07-21T05:29:16Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/7"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pytest-9.1.1",
    "headRefOid": "16d489be0ca351728a975a3477b822b3171f7186",
    "isDraft": false,
    "mergeCommit": {
      "oid": "c388a1d8fd0ae8f78c1611d01b934ab21896ff8c"
    },
    "number": 6,
    "state": "MERGED",
    "title": "chore(deps-dev): bump pytest from 9.0.2 to 9.1.1 in /apps/backend",
    "updatedAt": "2026-07-21T05:38:18Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/6"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/actions/setup-node-6",
    "headRefOid": "28ce3c33ae4342fc69909dea289721ede7ea9ddd",
    "isDraft": false,
    "mergeCommit": {
      "oid": "bfb996383d3d4ba774247870d9d38d703b4e39bb"
    },
    "number": 5,
    "state": "MERGED",
    "title": "chore(deps): bump actions/setup-node from 4 to 7",
    "updatedAt": "2026-07-21T05:38:36Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/5"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/pip/apps/backend/pydantic-settings-2.14.2",
    "headRefOid": "d405398704d8c84817712ad1301c7e3b3910672e",
    "isDraft": false,
    "mergeCommit": null,
    "number": 4,
    "state": "CLOSED",
    "title": "chore(deps): bump pydantic-settings from 2.12.0 to 2.14.2 in /apps/backend",
    "updatedAt": "2026-07-12T15:51:47Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/4"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/docker/setup-buildx-action-4",
    "headRefOid": "2ade83bf4630093ca84265d38c8bf3a763953a5e",
    "isDraft": false,
    "mergeCommit": {
      "oid": "eacd8f86a06f460e16a724b1b73c0e11b3bdf0c6"
    },
    "number": 3,
    "state": "MERGED",
    "title": "chore(deps): bump docker/setup-buildx-action from 3 to 4",
    "updatedAt": "2026-07-21T05:38:44Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/3"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/actions/setup-python-6",
    "headRefOid": "b31bcc73fc966cc913125033fbc744647d96493d",
    "isDraft": false,
    "mergeCommit": {
      "oid": "c7d6d5b132b0b6e58c11d9c14ebd7e15fc819511"
    },
    "number": 2,
    "state": "MERGED",
    "title": "chore(deps): bump actions/setup-python from 5 to 7",
    "updatedAt": "2026-07-21T05:38:53Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/2"
  },
  {
    "author": {
      "is_bot": true,
      "login": "app/dependabot"
    },
    "baseRefName": "main",
    "headRefName": "dependabot/github_actions/docker/build-push-action-7",
    "headRefOid": "363ff09f91b7673822c4d119805689b9b01b87d1",
    "isDraft": false,
    "mergeCommit": {
      "oid": "6de40d27783d735b342b37ab73d52651cdbafd82"
    },
    "number": 1,
    "state": "MERGED",
    "title": "chore(deps): bump docker/build-push-action from 6 to 7",
    "updatedAt": "2026-07-21T05:50:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/pull/1"
  }
]
```

### Issues (all states)
```json
[
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      }
    ],
    "number": 160,
    "state": "OPEN",
    "title": "[AI][Experiment][QA] Independent QA for fine-tuning experiment",
    "updatedAt": "2026-11-01T17:01:29Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/160"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      }
    ],
    "number": 159,
    "state": "OPEN",
    "title": "[AI][Experiment] Locked test evaluation and reproducibility evidence",
    "updatedAt": "2026-11-01T17:01:28Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/159"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      }
    ],
    "number": 158,
    "state": "OPEN",
    "title": "[AI][Experiment] Build bounded multilingual retrieval adapter",
    "updatedAt": "2026-11-01T17:01:26Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/158"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      }
    ],
    "number": 157,
    "state": "OPEN",
    "title": "[AI][Experiment] Reproduce unfine-tuned multilingual E5 baseline",
    "updatedAt": "2026-11-01T17:01:25Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/157"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      }
    ],
    "number": 156,
    "state": "OPEN",
    "title": "[AI][Experiment] Multilingual E5 fine-tuning contract",
    "updatedAt": "2026-11-01T17:01:23Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/156"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1Yg",
        "name": "documentation",
        "description": "Improvements or additions to documentation",
        "color": "0075ca"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 147,
    "state": "OPEN",
    "title": "[Audit] Engineering audit findings tracker (Phase 1 + Phase 2)",
    "updatedAt": "2026-10-31T18:35:03Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/147"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qRvg",
        "name": "frontend",
        "description": "",
        "color": "fbca04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qT4Q",
        "name": "observability",
        "description": "",
        "color": "0052cc"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 146,
    "state": "OPEN",
    "title": "[P3][Observability] F-14: Add privacy-safe application error capture",
    "updatedAt": "2026-10-31T18:34:12Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/146"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 145,
    "state": "OPEN",
    "title": "[P3][Security] F-13: Prepare individual admin accounts for promotion to main",
    "updatedAt": "2026-10-31T18:34:10Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/145"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1ZA",
        "name": "enhancement",
        "description": "New feature or request",
        "color": "a2eeef"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qRvg",
        "name": "frontend",
        "description": "",
        "color": "fbca04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 144,
    "state": "OPEN",
    "title": "[P3][Frontend] F-08: Evaluate selective caching for catalogue pages",
    "updatedAt": "2026-10-31T18:34:08Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/144"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1Yg",
        "name": "documentation",
        "description": "Improvements or additions to documentation",
        "color": "0075ca"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 143,
    "state": "CLOSED",
    "title": "[P3][Docs] F-07: Correct stale MongoDB/Atlas and auth documentation",
    "updatedAt": "2026-10-31T21:56:15Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/143"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 142,
    "state": "CLOSED",
    "title": "[P3][Backend] F-16: Evict idle keys in the in-memory rate limiter",
    "updatedAt": "2026-10-31T19:25:09Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/142"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qS-g",
        "name": "testing",
        "description": "",
        "color": "c5def5"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qU6w",
        "name": "ci",
        "description": "",
        "color": "ededed"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWo4Q",
        "name": "priority:p3",
        "description": "Low: useful improvement, not a release blocker",
        "color": "0E8A16"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 141,
    "state": "CLOSED",
    "title": "[P3][Testing] F-10: Add coverage reporting and critical-path floors to CI",
    "updatedAt": "2026-10-31T20:12:03Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/141"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qRvg",
        "name": "frontend",
        "description": "",
        "color": "fbca04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qS-g",
        "name": "testing",
        "description": "",
        "color": "c5def5"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 140,
    "state": "CLOSED",
    "title": "[P2][Testing] F-10: Add automated accessibility checks to Playwright",
    "updatedAt": "2026-10-31T20:12:00Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/140"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 139,
    "state": "OPEN",
    "title": "[P2][AI] F-11: Separate synthetic from reviewed evaluation data and report uncertainty",
    "updatedAt": "2026-10-31T18:32:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/139"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qU6w",
        "name": "ci",
        "description": "",
        "color": "ededed"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 138,
    "state": "OPEN",
    "title": "[P2][CI] F-05: Wire the AI evaluation gate to real datasets and enabled features",
    "updatedAt": "2026-10-31T18:32:44Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/138"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 137,
    "state": "CLOSED",
    "title": "[P2][AI] F-15: Use CPU-only PyTorch and measure E5 image/runtime cost",
    "updatedAt": "2026-11-01T13:13:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/137"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qU6w",
        "name": "ci",
        "description": "",
        "color": "ededed"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 136,
    "state": "CLOSED",
    "title": "[P2][Security] F-19: Lock and audit the E5 dependency set",
    "updatedAt": "2026-11-01T13:13:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/136"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qS-g",
        "name": "testing",
        "description": "",
        "color": "c5def5"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 135,
    "state": "CLOSED",
    "title": "[P2][Backend] F-04: Test trusted-proxy handling in the rate limiter",
    "updatedAt": "2026-10-31T19:25:07Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/135"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 134,
    "state": "CLOSED",
    "title": "[P2][Backend] F-01: Remove staging defaults from the backend image",
    "updatedAt": "2026-10-31T19:25:07Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/134"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1YA",
        "name": "bug",
        "description": "Something isn't working",
        "color": "d73a4a"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qRvg",
        "name": "frontend",
        "description": "",
        "color": "fbca04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWoag",
        "name": "priority:p2",
        "description": "Medium: significant correctness, hardening, testing or reliability improvement",
        "color": "FBCA04"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 133,
    "state": "CLOSED",
    "title": "[P2][Frontend] F-18: Preserve API error semantics on product pages",
    "updatedAt": "2026-10-31T19:08:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/133"
  },
  {
    "labels": [],
    "number": 129,
    "state": "OPEN",
    "title": "Stabilize consolidated embedding pipelines and verify PostgreSQL migration chain",
    "updatedAt": "2026-10-31T18:34:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/129"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      }
    ],
    "number": 113,
    "state": "CLOSED",
    "title": "[AI][P0][Postgres] Move catalogue and ingestion to PostgreSQL and remove MongoDB",
    "updatedAt": "2026-10-29T17:17:29Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/113"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qOBQ",
        "name": "phase-5",
        "description": "",
        "color": "fef2c0"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      }
    ],
    "number": 112,
    "state": "OPEN",
    "title": "[AI][P5][Epic] Phase 5: Production platform (k3s, GitOps, SLOs)",
    "updatedAt": "2026-10-29T09:23:51Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/112"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qNeg",
        "name": "phase-4",
        "description": "",
        "color": "f9d0c4"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      }
    ],
    "number": 111,
    "state": "OPEN",
    "title": "[AI][P4][Epic] Phase 4: Voice (ASR)",
    "updatedAt": "2026-10-29T09:11:09Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/111"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qMxg",
        "name": "phase-3",
        "description": "",
        "color": "d4c5f9"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      }
    ],
    "number": 110,
    "state": "OPEN",
    "title": "[AI][P3][Epic] Phase 3: Identity, memory and personalisation",
    "updatedAt": "2026-10-31T16:32:38Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/110"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qL9g",
        "name": "phase-2",
        "description": "",
        "color": "bfd4f2"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      }
    ],
    "number": 109,
    "state": "OPEN",
    "title": "[AI][P2][Epic] Phase 2: Agentic UI layer",
    "updatedAt": "2026-10-31T16:32:36Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/109"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qLcw",
        "name": "phase-1",
        "description": "",
        "color": "bfdadc"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQWg",
        "name": "epic",
        "description": "",
        "color": "3e4b9e"
      }
    ],
    "number": 108,
    "state": "OPEN",
    "title": "[AI][P1][Epic] Phase 1: Catalogue intelligence and hybrid search",
    "updatedAt": "2026-10-31T16:32:34Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/108"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1Yg",
        "name": "documentation",
        "description": "Improvements or additions to documentation",
        "color": "0075ca"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      }
    ],
    "number": 107,
    "state": "OPEN",
    "title": "[AI][P0][Docs] Update README, DEPLOYMENT, OPERATIONS, architecture doc and CLAUDE.md for the AI platform",
    "updatedAt": "2026-10-29T09:10:51Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/107"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      }
    ],
    "number": 106,
    "state": "OPEN",
    "title": "[AI][P0][Infra] Order the VPS and run the existing stack behind Cloudflare",
    "updatedAt": "2026-10-29T09:23:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/106"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qW_Q",
        "name": "operations",
        "description": "",
        "color": "006b75"
      }
    ],
    "number": 105,
    "state": "OPEN",
    "title": "[AI][P0][Postgres] Postgres backups to R2, restore drill and retention jobs",
    "updatedAt": "2026-10-31T18:34:38Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/105"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qWVA",
        "name": "staging",
        "description": "",
        "color": "ff9f1c"
      }
    ],
    "number": 104,
    "state": "OPEN",
    "title": "[AI][P0][Environments] Local to staging to production strategy for Postgres, Redis and the AI services",
    "updatedAt": "2026-10-31T18:34:39Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/104"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qU6w",
        "name": "ci",
        "description": "",
        "color": "ededed"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qVtA",
        "name": "security",
        "description": "",
        "color": "d93f0b"
      }
    ],
    "number": 103,
    "state": "OPEN",
    "title": "[AI][P0][CI] Multi-arch GHCR images, Trivy, gitleaks, CodeQL and SBOM",
    "updatedAt": "2026-10-31T18:34:40Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/103"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qUKw",
        "name": "evals",
        "description": "",
        "color": "b60205"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qU6w",
        "name": "ci",
        "description": "",
        "color": "ededed"
      }
    ],
    "number": 102,
    "state": "CLOSED",
    "title": "[AI][P0][Evals] evals/ runner skeleton wired into CI with empty gates",
    "updatedAt": "2026-10-31T16:30:50Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/102"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qRvg",
        "name": "frontend",
        "description": "",
        "color": "fbca04"
      }
    ],
    "number": 101,
    "state": "OPEN",
    "title": "[AI][P0][Events] Interaction logging: POST /v1/events and storefront tracker for searches and product views",
    "updatedAt": "2026-10-29T09:10:25Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/101"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qT4Q",
        "name": "observability",
        "description": "",
        "color": "0052cc"
      }
    ],
    "number": 100,
    "state": "OPEN",
    "title": "[AI][P0][Observability] OpenTelemetry to Grafana Cloud and Langfuse tracing",
    "updatedAt": "2026-10-31T18:34:43Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/100"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qTfQ",
        "name": "llm",
        "description": "",
        "color": "ff6f00"
      }
    ],
    "number": 99,
    "state": "OPEN",
    "title": "[AI][P0][LLM] LiteLLM gateway with dev fallback chain and budgets",
    "updatedAt": "2026-10-29T09:10:17Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/99"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      }
    ],
    "number": 98,
    "state": "OPEN",
    "title": "[AI][P0][Queue] Redis and arq worker with a sample job; Redis-backed rate limits",
    "updatedAt": "2026-10-29T09:23:41Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/98"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qXfA",
        "name": "refactor",
        "description": "",
        "color": "cccccc"
      }
    ],
    "number": 97,
    "state": "CLOSED",
    "title": "[AI][P0][Backend] Restructure backend into modules (core, catalog, events, audit, identity, agent, memory) with no behaviour change",
    "updatedAt": "2026-10-29T12:58:16Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/97"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qS-g",
        "name": "testing",
        "description": "",
        "color": "c5def5"
      }
    ],
    "number": 96,
    "state": "CLOSED",
    "title": "[AI][P0][Testing] Testcontainers integration tests for Postgres and Redis",
    "updatedAt": "2026-10-31T16:30:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/96"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      }
    ],
    "number": 95,
    "state": "OPEN",
    "title": "[AI][P0][Postgres] First Alembic migration: customers, identities, events, conversations, messages, tool_calls, audit_log",
    "updatedAt": "2026-10-29T09:23:39Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/95"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qQ8g",
        "name": "backend",
        "description": "",
        "color": "1d76db"
      }
    ],
    "number": 94,
    "state": "OPEN",
    "title": "[AI][P0][Postgres] SQLAlchemy 2 (async) and Alembic wired into the backend",
    "updatedAt": "2026-10-31T16:32:42Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/94"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qO4g",
        "name": "postgres",
        "description": "",
        "color": "336791"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qSag",
        "name": "infrastructure",
        "description": "",
        "color": "5319e7"
      }
    ],
    "number": 93,
    "state": "OPEN",
    "title": "[AI][P0][Postgres] Add PostgreSQL 17 + pgvector to local and production compose",
    "updatedAt": "2026-10-29T12:58:18Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/93"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1Yg",
        "name": "documentation",
        "description": "Improvements or additions to documentation",
        "color": "0075ca"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKDw",
        "name": "ai",
        "description": "",
        "color": "5319e7"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qKzA",
        "name": "phase-0",
        "description": "",
        "color": "c2e0c6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAAC_7qPrA",
        "name": "adr",
        "description": "",
        "color": "0e8a16"
      }
    ],
    "number": 92,
    "state": "OPEN",
    "title": "[AI][P0][Docs] Write ADRs 001-006 and C4 context/container diagrams",
    "updatedAt": "2026-10-29T09:23:34Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/92"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1ZA",
        "name": "enhancement",
        "description": "New feature or request",
        "color": "a2eeef"
      }
    ],
    "number": 86,
    "state": "OPEN",
    "title": "[P2][Scalability] Measure staging capacity by population, daily visitors and concurrency",
    "updatedAt": "2026-10-26T13:47:05Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/86"
  },
  {
    "labels": [],
    "number": 83,
    "state": "CLOSED",
    "title": "[P0][Dependencies] Resolve braces GHSA-vfj7-8cjw-p6xm from PR #65",
    "updatedAt": "2026-10-27T16:46:52Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/83"
  },
  {
    "labels": [],
    "number": 82,
    "state": "OPEN",
    "title": "[P1][Governance] Enforce minimum main branch protection after approval",
    "updatedAt": "2026-10-31T18:34:42Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/82"
  },
  {
    "labels": [],
    "number": 81,
    "state": "CLOSED",
    "title": "[P1][Admin] Preserve stable variant identifiers during product edits",
    "updatedAt": "2026-10-28T06:27:53Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/81"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAADAYWpvg",
        "name": "audit:phase-2",
        "description": "Finding verified in the Phase 2 engineering audit",
        "color": "5319E7"
      }
    ],
    "number": 80,
    "state": "OPEN",
    "title": "[P1][Security] Restrict remote product image hosts and review frontend CSP",
    "updatedAt": "2026-10-31T18:34:35Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/80"
  },
  {
    "labels": [],
    "number": 79,
    "state": "CLOSED",
    "title": "[P1][Catalog] Support browsing beyond the first 100 published products",
    "updatedAt": "2026-10-31T19:08:46Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/79"
  },
  {
    "labels": [],
    "number": 78,
    "state": "CLOSED",
    "title": "[P0][Content] Verify business contact and approve delivery, returns, terms and privacy copy",
    "updatedAt": "2026-10-28T07:18:50Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/78"
  },
  {
    "labels": [],
    "number": 77,
    "state": "CLOSED",
    "title": "[P0][Operations] Add production monitoring, error alerts and rehearse image rollback",
    "updatedAt": "2026-10-28T06:28:09Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/77"
  },
  {
    "labels": [],
    "number": 76,
    "state": "CLOSED",
    "title": "[P0][Deployment] Configure final HTTPS deployment and verify readiness end-to-end",
    "updatedAt": "2026-10-28T06:28:06Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/76"
  },
  {
    "labels": [],
    "number": 75,
    "state": "CLOSED",
    "title": "[P0][Checkout] Revalidate current product, variant, price and stock before WhatsApp handoff",
    "updatedAt": "2026-10-28T06:27:50Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/75"
  },
  {
    "labels": [],
    "number": 74,
    "state": "CLOSED",
    "title": "[P0][Catalog] Remove fabricated fallback stock from product mapping",
    "updatedAt": "2026-10-28T06:27:47Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/74"
  },
  {
    "labels": [],
    "number": 73,
    "state": "CLOSED",
    "title": "[P0][Release] Restore green main CI and certify exact launch commit",
    "updatedAt": "2026-10-28T06:28:25Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/73"
  },
  {
    "labels": [],
    "number": 72,
    "state": "CLOSED",
    "title": "[P0][Acceptance] Validate real WhatsApp customer ordering on desktop and mobile",
    "updatedAt": "2026-10-28T06:28:04Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/72"
  },
  {
    "labels": [],
    "number": 71,
    "state": "CLOSED",
    "title": "[P0][Acceptance] Execute live admin-to-storefront product lifecycle QA",
    "updatedAt": "2026-10-28T06:28:01Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/71"
  },
  {
    "labels": [],
    "number": 70,
    "state": "CLOSED",
    "title": "[P0][Operations] Automate encrypted MongoDB backups and prove isolated restore",
    "updatedAt": "2026-10-28T06:27:58Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/70"
  },
  {
    "labels": [],
    "number": 69,
    "state": "CLOSED",
    "title": "[P0][Infrastructure] Configure authenticated and private production MongoDB",
    "updatedAt": "2026-10-28T06:27:56Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/69"
  },
  {
    "labels": [],
    "number": 68,
    "state": "CLOSED",
    "title": "[P0][Dependencies] Patch PyMongo advisories and restore backend pip-audit",
    "updatedAt": "2026-10-28T04:39:22Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/68"
  },
  {
    "labels": [],
    "number": 67,
    "state": "CLOSED",
    "title": "[P0][Security] Rate-limit admin sign-in and harden session authentication",
    "updatedAt": "2026-10-28T06:27:44Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/67"
  },
  {
    "labels": [],
    "number": 66,
    "state": "CLOSED",
    "title": "[P0][Security] Enforce admin session authorization on every Next.js admin API proxy",
    "updatedAt": "2026-10-28T06:27:41Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/66"
  },
  {
    "labels": [],
    "number": 58,
    "state": "CLOSED",
    "title": "Build admin product-management screens",
    "updatedAt": "2026-08-23T18:08:21Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/58"
  },
  {
    "labels": [],
    "number": 57,
    "state": "CLOSED",
    "title": "Build authenticated admin shell and navigation",
    "updatedAt": "2026-08-22T05:25:48Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/57"
  },
  {
    "labels": [],
    "number": 56,
    "state": "CLOSED",
    "title": "Add order lookup and status progression support",
    "updatedAt": "2026-10-31T16:31:13Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/56"
  },
  {
    "labels": [],
    "number": 55,
    "state": "CLOSED",
    "title": "Create backend order model and order creation endpoint",
    "updatedAt": "2026-10-31T16:31:08Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/55"
  },
  {
    "labels": [],
    "number": 54,
    "state": "CLOSED",
    "title": "Build cart summary and checkout handoff UI",
    "updatedAt": "2026-10-31T16:30:59Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/54"
  },
  {
    "labels": [],
    "number": 53,
    "state": "CLOSED",
    "title": "Design shared cart state and item-editing model",
    "updatedAt": "2026-08-22T06:03:57Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/53"
  },
  {
    "labels": [],
    "number": 52,
    "state": "OPEN",
    "title": "Add ecommerce analytics and conversion tracking foundations",
    "updatedAt": "2026-08-20T19:39:06Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/52"
  },
  {
    "labels": [],
    "number": 51,
    "state": "OPEN",
    "title": "Add wishlist and saved-products browsing aids",
    "updatedAt": "2026-08-20T19:39:01Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/51"
  },
  {
    "labels": [],
    "number": 50,
    "state": "OPEN",
    "title": "Add size guide, shipping estimator, and FAQ trust modules",
    "updatedAt": "2026-08-20T19:38:54Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/50"
  },
  {
    "labels": [],
    "number": 49,
    "state": "OPEN",
    "title": "Build production admin dashboard for shawl/stole product management",
    "updatedAt": "2026-10-31T16:32:40Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/49"
  },
  {
    "labels": [],
    "number": 48,
    "state": "CLOSED",
    "title": "Add order persistence and order tracking backend for shawls/stoles",
    "updatedAt": "2026-10-31T16:31:04Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/48"
  },
  {
    "labels": [],
    "number": 47,
    "state": "CLOSED",
    "title": "Add cart and multi-item WhatsApp checkout for shawls/stoles",
    "updatedAt": "2026-10-31T16:30:54Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/47"
  },
  {
    "labels": [],
    "number": 46,
    "state": "OPEN",
    "title": "Audit shawl/stole discovery and product-detail UX gaps",
    "updatedAt": "2026-08-20T19:38:32Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/46"
  },
  {
    "labels": [],
    "number": 45,
    "state": "OPEN",
    "title": "Feature gap audit: shawls/stoles ecommerce completeness",
    "updatedAt": "2026-10-31T16:32:45Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/45"
  },
  {
    "labels": [],
    "number": 44,
    "state": "OPEN",
    "title": "Consolidate production launch-gate and operations docs",
    "updatedAt": "2026-08-20T19:27:41Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/44"
  },
  {
    "labels": [],
    "number": 43,
    "state": "OPEN",
    "title": "Add repository LICENSE file",
    "updatedAt": "2026-08-20T19:27:36Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/43"
  },
  {
    "labels": [],
    "number": 42,
    "state": "CLOSED",
    "title": "Map admin dashboard routes and payloads to /products/admin/*",
    "updatedAt": "2026-10-28T06:28:15Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/42"
  },
  {
    "labels": [],
    "number": 41,
    "state": "CLOSED",
    "title": "Replace browser-delivered admin secret with server-side proxy",
    "updatedAt": "2026-10-28T06:28:11Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/41"
  },
  {
    "labels": [],
    "number": 40,
    "state": "CLOSED",
    "title": "Admin dashboard / Quill integration audit",
    "updatedAt": "2026-10-28T07:18:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/40"
  },
  {
    "labels": [],
    "number": 39,
    "state": "CLOSED",
    "title": "Backend production readiness audit",
    "updatedAt": "2026-10-28T07:18:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/39"
  },
  {
    "labels": [],
    "number": 38,
    "state": "CLOSED",
    "title": "Frontend production readiness audit",
    "updatedAt": "2026-10-28T07:18:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/38"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1ZA",
        "name": "enhancement",
        "description": "New feature or request",
        "color": "a2eeef"
      }
    ],
    "number": 37,
    "state": "CLOSED",
    "title": "[P0][Audit] Coordinate production-readiness and scalability evidence",
    "updatedAt": "2026-10-28T07:18:49Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/37"
  },
  {
    "labels": [],
    "number": 36,
    "state": "CLOSED",
    "title": "Draft minimal main-branch protection baseline and rollout notes",
    "updatedAt": "2026-10-31T19:47:15Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/36"
  },
  {
    "labels": [],
    "number": 35,
    "state": "CLOSED",
    "title": "Inspect current GitHub branch protection and ruleset state",
    "updatedAt": "2026-10-31T19:47:11Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/35"
  },
  {
    "labels": [],
    "number": 34,
    "state": "CLOSED",
    "title": "Re-run frontend production validation after dependency refresh",
    "updatedAt": "2026-10-28T06:28:23Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/34"
  },
  {
    "labels": [],
    "number": 33,
    "state": "CLOSED",
    "title": "Upgrade Next.js and refresh frontend lockfile",
    "updatedAt": "2026-10-28T06:28:20Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/33"
  },
  {
    "labels": [],
    "number": 32,
    "state": "CLOSED",
    "title": "Audit frontend dependency tree and advisory scope",
    "updatedAt": "2026-10-04T19:07:15Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/32"
  },
  {
    "labels": [],
    "number": 24,
    "state": "OPEN",
    "title": "Governance plan: minimal main branch-protection baseline",
    "updatedAt": "2026-10-31T19:47:19Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/24"
  },
  {
    "labels": [
      {
        "id": "LA_kwDOQk7jDc8AAAACR7K1YA",
        "name": "bug",
        "description": "Something isn't working",
        "color": "d73a4a"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAACrYun2Q",
        "name": "dependencies",
        "description": "Pull requests that update a dependency file",
        "color": "0366d6"
      },
      {
        "id": "LA_kwDOQk7jDc8AAAACrYvF0A",
        "name": "javascript",
        "description": "Pull requests that update javascript code",
        "color": "168700"
      }
    ],
    "number": 23,
    "state": "CLOSED",
    "title": "Remediate frontend production dependency vulnerabilities",
    "updatedAt": "2026-10-28T06:28:17Z",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/issues/23"
  }
]
```

### Recent CI runs
```json
[
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T13:49:07Z",
    "databaseId": 42228563542,
    "headBranch": "staging",
    "headSha": "b4c5f58046cda2c848518a70425644ee80eee55e",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42228563542"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T11:49:51Z",
    "databaseId": 42213116706,
    "headBranch": "staging",
    "headSha": "15442712fa4799cfc9e3bfb889f77b1769beaffa",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42213116706"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T11:28:51Z",
    "databaseId": 42210550987,
    "headBranch": "staging",
    "headSha": "1641b683e15ee77f300a4f73f5af8a47600c82b7",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42210550987"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T11:20:22Z",
    "databaseId": 42209505170,
    "headBranch": "staging",
    "headSha": "f254e975a0b6ec3b3d1b7c3eeff25d3dcccb689a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42209505170"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T11:03:17Z",
    "databaseId": 42207315107,
    "headBranch": "staging",
    "headSha": "394e74828ec5a60b7fe1cb68c5db1d4c3b64056c",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42207315107"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T10:54:29Z",
    "databaseId": 42206218756,
    "headBranch": "staging",
    "headSha": "6d4dcff6d2818f9b49c1d443248c0660fee14d98",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42206218756"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-06T08:12:51Z",
    "databaseId": 42186068925,
    "headBranch": "staging",
    "headSha": "dff5248e96911640c1b039481b0fd0a7464dc0d1",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42186068925"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-05T21:28:05Z",
    "databaseId": 42112898345,
    "headBranch": "staging",
    "headSha": "7e319d5348dc3ef97aa2f6e278cf85528a3d9469",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42112898345"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-05T15:51:03Z",
    "databaseId": 42059150174,
    "headBranch": "staging",
    "headSha": "e061483083b3ecee380d16b0dde88e8759e40261",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42059150174"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-05T15:13:28Z",
    "databaseId": 42052770067,
    "headBranch": "staging",
    "headSha": "3de94149d0129db9340eb1adb28f6038d3310adc",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42052770067"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-05T10:56:32Z",
    "databaseId": 42014843118,
    "headBranch": "staging",
    "headSha": "f466ebcf49e6ab4348aeec68dcf838c7a1c83f77",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/42014843118"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:26:45Z",
    "databaseId": 41261118231,
    "headBranch": "dependabot/npm_and_yarn/apps/frontend/eslint-10.13.0",
    "headSha": "8dbbe0813008f7cc60acd8984a6a39607b42f4e7",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261118231"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-01T01:26:35Z",
    "databaseId": 41261106820,
    "headBranch": "dependabot/npm_and_yarn/apps/frontend/vitest-5.0.5",
    "headSha": "4fd0eb6d0d19adcd5af23e92e0f602735c957158",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261106820"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:26:21Z",
    "databaseId": 41261091008,
    "headBranch": "dependabot/npm_and_yarn/apps/frontend/lucide-react-1.63.0",
    "headSha": "89956be346896309e592a024295828a088b3e33a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261091008"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:26:12Z",
    "databaseId": 41261080648,
    "headBranch": "dependabot/npm_and_yarn/apps/frontend/types/node-26.6.6",
    "headSha": "cb44b5d8b5923b2af79038a7fce03fed1d08a04d",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261080648"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:26:05Z",
    "databaseId": 41261072617,
    "headBranch": "dependabot/npm_and_yarn/apps/frontend/frontend-minor-patch-fc91edfa29",
    "headSha": "9135c80327d2e1f40c3c76b1aa0602430759a75b",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261072617"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:25:29Z",
    "databaseId": 41261029687,
    "headBranch": "dependabot/pip/apps/backend/pydantic-settings-2.16.2",
    "headSha": "3ea2b4d3cb380759341b5691e89858d2c0ebfc42",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261029687"
  },
  {
    "conclusion": "cancelled",
    "createdAt": "2026-11-01T01:25:25Z",
    "databaseId": 41261024483,
    "headBranch": "dependabot/pip/apps/backend/pydantic-2.14.1",
    "headSha": "a71895fe399eb69a7664a914b5b2995859ab0c5a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261024483"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-11-01T01:25:18Z",
    "databaseId": 41261016256,
    "headBranch": "dependabot/pip/apps/backend/redis-8.1.0",
    "headSha": "306916a6b555a0e8e7f0f2a27bc5fa623cdced69",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41261016256"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:24:21Z",
    "databaseId": 41260950316,
    "headBranch": "main",
    "headSha": "283b27eee90533435ef3b2e28e6a3823ee1c5d23",
    "name": "npm_and_yarn in /apps/frontend - Update #1669001540",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41260950316"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:24:21Z",
    "databaseId": 41260950008,
    "headBranch": "main",
    "headSha": "283b27eee90533435ef3b2e28e6a3823ee1c5d23",
    "name": "github_actions in /. - Update #1669001527",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41260950008"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-11-01T01:24:21Z",
    "databaseId": 41260949937,
    "headBranch": "main",
    "headSha": "283b27eee90533435ef3b2e28e6a3823ee1c5d23",
    "name": "pip in /apps/backend - Update #1669001525",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41260949937"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T19:24:52Z",
    "databaseId": 41234103019,
    "headBranch": "staging",
    "headSha": "902a2fff7bc24ffbc23af446a828d2da56aa0059",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41234103019"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T19:08:08Z",
    "databaseId": 41232761220,
    "headBranch": "staging",
    "headSha": "d352d8be622c8f6f22eb4ee95f9de4fe30818dec",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41232761220"
  },
  {
    "conclusion": "failure",
    "createdAt": "2026-10-31T19:03:37Z",
    "databaseId": 41232387020,
    "headBranch": "staging",
    "headSha": "7d387caa70bd45ee2b8a5172db402def77010cf8",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41232387020"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T17:21:16Z",
    "databaseId": 41224119914,
    "headBranch": "staging",
    "headSha": "581fad46fa7317a7f0ee0bd8b0161ec7cac5f3a0",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41224119914"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T17:17:23Z",
    "databaseId": 41223794041,
    "headBranch": "staging-integration",
    "headSha": "fed9db4eb1ab82e9bf02c387c39c162b38111b7a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41223794041"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T17:12:47Z",
    "databaseId": 41223423667,
    "headBranch": "staging-integration",
    "headSha": "fed9db4eb1ab82e9bf02c387c39c162b38111b7a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41223423667"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T17:09:10Z",
    "databaseId": 41223118640,
    "headBranch": "docs/three-branch-workflow",
    "headSha": "fc298820ad95f746c0412a9ba2eb700721f97df5",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41223118640"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-31T16:06:35Z",
    "databaseId": 41218060344,
    "headBranch": "fix/embedding-consolidation",
    "headSha": "63c3fc60777b682e95725f9db16c1bf5f42c5200",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41218060344"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:48:01Z",
    "databaseId": 41036057281,
    "headBranch": "main",
    "headSha": "283b27eee90533435ef3b2e28e6a3823ee1c5d23",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41036057281"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:45:41Z",
    "databaseId": 41035773754,
    "headBranch": "chore/pin-e5-evaluated-snapshot",
    "headSha": "4e6860dc1d345af0a2ed90a0d792e3908b7b619a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41035773754"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:19:19Z",
    "databaseId": 41032568599,
    "headBranch": "main",
    "headSha": "95431c5a86b96bce5c5d9b7b8ea8266e50b7ddd3",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41032568599"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:12:17Z",
    "databaseId": 41031710496,
    "headBranch": "fix/staging-migrations",
    "headSha": "252340a8dcf383cb8bdc97d14c4f7bbe230053b4",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41031710496"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:08:24Z",
    "databaseId": 41031234172,
    "headBranch": "main",
    "headSha": "931d58932dbba8a921c030f98d593bbc5701b05b",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41031234172"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T09:03:39Z",
    "databaseId": 41030660857,
    "headBranch": "fix/render-asyncpg-url",
    "headSha": "ac96a2bd033b9669a21dcde00d96c3c8b9a1204e",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41030660857"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T08:38:52Z",
    "databaseId": 41027850020,
    "headBranch": "main",
    "headSha": "7777ccc2c22e969318fca99c3c5694d9187a5ed3",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41027850020"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T08:31:39Z",
    "databaseId": 41027037251,
    "headBranch": "ai/local-ai-search-integration",
    "headSha": "6cdf9f2df42248b9991f4ba1a2bfcf230eefb0f8",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41027037251"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T06:35:23Z",
    "databaseId": 41014960266,
    "headBranch": "ai/local-e5-v2-evidence",
    "headSha": "61a45a1e7061e016ea7583e893486c77701f2278",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41014960266"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T05:47:28Z",
    "databaseId": 41010375358,
    "headBranch": "ai/reviewed-synthetic-benchmark-v2",
    "headSha": "24346e8c4f0af2f1cae98c5d9abdcaccad3d8f13",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41010375358"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T05:29:37Z",
    "databaseId": 41008729224,
    "headBranch": "ai/synonym-error-analysis",
    "headSha": "b693d7733fe31879ea46d091a69b764b78cff580",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41008729224"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T05:12:52Z",
    "databaseId": 41007160028,
    "headBranch": "ai/openai-embedding-eval",
    "headSha": "82c034de3e4838e1feac2d2b7ccd1f3d701b8292",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41007160028"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-30T04:25:42Z",
    "databaseId": 41002832483,
    "headBranch": "ai/embedding-synthetic-eval",
    "headSha": "c71ef03062f2bcba535e53071e61429ebcf020e4",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/41002832483"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T19:49:21Z",
    "databaseId": 40943510925,
    "headBranch": "ai/embedding-provider-contract",
    "headSha": "0cf5613ce1e40c7b6ec3ca36cbeedd8137ecfc4f",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40943510925"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T19:39:45Z",
    "databaseId": 40942100948,
    "headBranch": "ai/phase-1-s4c-hybrid",
    "headSha": "2220811411c55ea367abb4b44deab460f99dfb54",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40942100948"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T19:29:56Z",
    "databaseId": 40940611726,
    "headBranch": "ai/phase-1-s4b-embeddings",
    "headSha": "0719769bdc6cabf5537d6578f7ad162764457ee4",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40940611726"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T19:13:17Z",
    "databaseId": 40938088626,
    "headBranch": "ai/phase-1-s4a-representations",
    "headSha": "843a22857999470ab96a64497f2b0fb64d37321a",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40938088626"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T19:03:49Z",
    "databaseId": 40936625387,
    "headBranch": "ai/phase-1-enrichment-admin-review",
    "headSha": "40653fe5ef84c8eb6b58785cd526986f1866f8d4",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40936625387"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T18:47:49Z",
    "databaseId": 40934163078,
    "headBranch": "ai/phase-1-enrichment",
    "headSha": "976eb0ae5ab42af7bf059752430f3775d2795d9c",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40934163078"
  },
  {
    "conclusion": "success",
    "createdAt": "2026-10-29T09:02:59Z",
    "databaseId": 40846590214,
    "headBranch": "main",
    "headSha": "1b7aa8765acd8b2405f2e37aa77ceecf630c636c",
    "name": "CI",
    "status": "completed",
    "url": "https://github.com/Muhammad-Hamza-Khan-03/Elegance-Shawls/actions/runs/40846590214"
  }
]
```

### Branch protection
```json
{
  "main": {
    "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection",
    "required_status_checks": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection/required_status_checks",
      "strict": true,
      "contexts": [
        "frontend",
        "backend",
        "containers",
        "e2e"
      ],
      "contexts_url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection/required_status_checks/contexts",
      "checks": [
        {
          "context": "frontend",
          "app_id": 15368
        },
        {
          "context": "backend",
          "app_id": 15368
        },
        {
          "context": "containers",
          "app_id": 15368
        },
        {
          "context": "e2e",
          "app_id": 15368
        }
      ]
    },
    "required_pull_request_reviews": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection/required_pull_request_reviews",
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "require_last_push_approval": false,
      "required_approving_review_count": 0
    },
    "required_signatures": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection/required_signatures",
      "enabled": false
    },
    "enforce_admins": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/main/protection/enforce_admins",
      "enabled": false
    },
    "required_linear_history": {
      "enabled": false
    },
    "allow_force_pushes": {
      "enabled": false
    },
    "allow_deletions": {
      "enabled": false
    },
    "block_creations": {
      "enabled": false
    },
    "required_conversation_resolution": {
      "enabled": false
    },
    "lock_branch": {
      "enabled": false
    },
    "allow_fork_syncing": {
      "enabled": false
    }
  },
  "staging": {
    "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection",
    "required_status_checks": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection/required_status_checks",
      "strict": false,
      "contexts": [
        "frontend",
        "backend",
        "containers",
        "e2e"
      ],
      "contexts_url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection/required_status_checks/contexts",
      "checks": [
        {
          "context": "frontend",
          "app_id": 15368
        },
        {
          "context": "backend",
          "app_id": 15368
        },
        {
          "context": "containers",
          "app_id": 15368
        },
        {
          "context": "e2e",
          "app_id": 15368
        }
      ]
    },
    "required_pull_request_reviews": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection/required_pull_request_reviews",
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "require_last_push_approval": false,
      "required_approving_review_count": 0
    },
    "required_signatures": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection/required_signatures",
      "enabled": false
    },
    "enforce_admins": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging/protection/enforce_admins",
      "enabled": false
    },
    "required_linear_history": {
      "enabled": false
    },
    "allow_force_pushes": {
      "enabled": false
    },
    "allow_deletions": {
      "enabled": false
    },
    "block_creations": {
      "enabled": false
    },
    "required_conversation_resolution": {
      "enabled": false
    },
    "lock_branch": {
      "enabled": false
    },
    "allow_fork_syncing": {
      "enabled": false
    }
  },
  "staging-integration": {
    "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection",
    "required_status_checks": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection/required_status_checks",
      "strict": false,
      "contexts": [
        "frontend",
        "backend",
        "containers",
        "e2e"
      ],
      "contexts_url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection/required_status_checks/contexts",
      "checks": [
        {
          "context": "frontend",
          "app_id": 15368
        },
        {
          "context": "backend",
          "app_id": 15368
        },
        {
          "context": "containers",
          "app_id": 15368
        },
        {
          "context": "e2e",
          "app_id": 15368
        }
      ]
    },
    "required_pull_request_reviews": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection/required_pull_request_reviews",
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "require_last_push_approval": false,
      "required_approving_review_count": 0
    },
    "required_signatures": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection/required_signatures",
      "enabled": false
    },
    "enforce_admins": {
      "url": "https://api.github.com/repos/Muhammad-Hamza-Khan-03/Elegance-Shawls/branches/staging-integration/protection/enforce_admins",
      "enabled": false
    },
    "required_linear_history": {
      "enabled": false
    },
    "allow_force_pushes": {
      "enabled": false
    },
    "allow_deletions": {
      "enabled": false
    },
    "block_creations": {
      "enabled": false
    },
    "required_conversation_resolution": {
      "enabled": false
    },
    "lock_branch": {
      "enabled": false
    },
    "allow_fork_syncing": {
      "enabled": false
    }
  },
  "integration": {
    "error": "gh: Branch not found (HTTP 404)",
    "rc": 1
  }
}
```

### Projects/Kanban
```json
{
  "projects": [
    {
      "closed": false,
      "fields": {
        "totalCount": 13
      },
      "id": "PVT_kwHOCcDq9c4Bg-ib",
      "items": {
        "totalCount": 86
      },
      "number": 4,
      "owner": {
        "login": "Muhammad-Hamza-Khan-03",
        "type": "User"
      },
      "public": false,
      "readme": "",
      "shortDescription": "",
      "title": "Elegance Shawls",
      "url": "https://github.com/users/Muhammad-Hamza-Khan-03/projects/4"
    },
    {
      "closed": false,
      "fields": {
        "totalCount": 13
      },
      "id": "PVT_kwHOCcDq9c4BeRBi",
      "items": {
        "totalCount": 37
      },
      "number": 3,
      "owner": {
        "login": "Muhammad-Hamza-Khan-03",
        "type": "User"
      },
      "public": false,
      "readme": "",
      "shortDescription": "Track delivery for the Hermes personal dashboard: auth, schema, ingestion, review flows, and deployment blockers.",
      "title": "personal-dashboard",
      "url": "https://github.com/users/Muhammad-Hamza-Khan-03/projects/3"
    }
  ],
  "totalCount": 4
}
```

## QA evidence observed

- Prior approved staging SHAs from task context: `dff5248e96911640c1b039481b0fd0a7464dc0d1`, `6d4dcff6d2818f9b49c1d443248c0660fee14d98`, `1641b683e15ee77f300a4f73f5af8a47600c82b7`, `b4c5f58046cda2c848518a70425644ee80eee55e`, `15442712fa4799cfc9e3bfb889f77b1769beaffa`.
- Current recent CI shows `origin/staging`/`b4c5f58` failing; therefore no new promotion is authorized by this audit.
- Dirty QA/evidence worktrees are retained and not treated as clean/merged merely from branch names.

## Cleanup policy applied

- Preserve protected refs, active/linked worktrees, dirty worktrees, detached QA worktrees with untracked artifacts, ambiguous unique work, and any branch lacking verifiable merged/superseded evidence.
- Archive-first cleanup is limited to clean, unlinked branches with merged PR evidence and no active worktree; any such action is recorded in a follow-up checkpoint.

## Checkpoint actions completed after inventory

- Canonical integration remains `origin/staging-integration` at `fed9db4eb1ab82e9bf02c387c39c162b38111b7a`; exact `integration` was not created because the existing `integration/local-complete` namespace/ref has a linked worktree.
- Created and remote-verified archive refs (source SHA preserved exactly):
  - `archive/reconciliation/2026-11-06-docs-three-branch-workflow` -> `fc298820ad95f746c0412a9ba2eb700721f97df5`
  - `archive/reconciliation/2026-11-06-fix-embedding-consolidation` -> `63c3fc60777b682e95725f9db16c1bf5f42c5200`
  - `archive/reconciliation/2026-11-06-fix-render-asyncpg-url` -> `ac96a2bd033b9669a21dcde00d96c3c8b9a1204e`
- Source remote refs were already absent. Local source branches were **retained** because ordinary `git branch -d` correctly refused deletion after squash-merge history was not a direct ancestor; no force deletion was used.
- Pruned only stale worktree metadata for missing `/tmp/m4-batch-b-qa`; no existing worktree directory or working tree content was removed.
- No active, dirty, detached-QA, or unique worktree was modified.

See `docs/reconciliation/2026-11-06-verification.md` for exact local verification output and the current staging CI migration-contract blocker.
