# EmbeddingGemma 2 provider contract

This record accompanies the narrow `staging-integration` candidate. It documents a reviewed, local-only provider contract; it does not activate production, perform a backfill, or set `release_ready`.

## Immutable provenance

| Field | Pinned value |
|---|---|
| Model | `google/embeddinggemma-2` |
| Hugging Face revision | `f9972ac22e696a105c482202646979e33e4b5a1e` |
| Embedding dimension | `768` |
| Canonical artifact tree SHA-256 | `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b` |
| `model.safetensors` SHA-256 | `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79` |

The adapter verifies the revision metadata, canonical tree digest, and weight-file digest before loading. It loads with network access blocked and fails closed to lexical-only retrieval on any provider, configuration, digest, load, inference, or vector-validation failure.

## Scope and safety

- Local provider name: `local_embeddinggemma2`; semantic search remains disabled by default.
- The model path and revision are explicit settings; no weights are downloaded by application code.
- Provider selection is explicit in hybrid query and backfill paths; unknown providers do not silently fall back.
- No production activation, deployment, shared-database backfill, credentials, customer data, or `release_ready` change is included.

## Verification evidence

## Local verification snapshot

Run from `apps/backend` on the candidate worktree:

- `pytest -q tests/test_local_gemma_search.py`: **12 passed, 1 skipped**. The skipped case is the real inference test because `sentence_transformers` is not installed in this environment; digest, revision, fail-closed, injected-provider, and route fallback cases ran.
- `pytest -q tests/test_local_gemma_search.py tests/test_local_semantic_search.py tests/test_postgres_layer.py tests/test_repositories_static.py`: **46 passed, 1 skipped**.
- `pytest -q -m integration tests/integration/test_embedding_jobs.py tests/integration/test_embeddings_schema.py`: **27 passed, 3 warnings** (testcontainers deprecation warnings only).
- `python -m compileall -q .`: **passed**.
- `git diff --check`: **passed**.

The exact immutable commit and independent QA rerun are recorded in the PR body. Any database-backed acceptance is reported separately from container-free provider tests; no production or release-readiness claim is made here.
