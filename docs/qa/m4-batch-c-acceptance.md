# M4 Batch C formal acceptance evidence

**Artifact:** M4 Batch C privacy-readiness worktree `ai/m4-batch-c-readiness`
**Observed candidate before this evidence refresh:** `f254e975a0b6ec3b3d1b7c3eeff25d3dcccb689a` (`origin/staging`)
**Scope:** readiness evidence only; no production activation, provider selection, spend, credentials, customer data, deployment, VPS, main, issue closure, or `release_ready`.

## Scope reconciliation

The worktree was clean before this acceptance run. The existing candidate contains the Batch C implementation and readiness artifacts, including memory privacy epoch / queue guards, consent and correction epoch invalidation, Alembic migration `0018_memory_privacy_epoch.py`, the deterministic synthetic evaluation, and provider-privacy/promotion decision records. This acceptance refresh changes only this evidence file; it does not alter production code or activation gates.

Commands were run from the exact worktree `/home/hamza/worktrees/m4-batch-c-readiness` or the stated application directory. The disposable PostgreSQL integration fixture uses Testcontainers with `pgvector/pgvector:0.8.1-pg17`; no shared or production database was used.

## Canonical verification executed in this run

| Check | Result |
|---|---|
| Backend canonical suite: `cd apps/backend && python -m pytest -q` | PASS — 1604 passed, 601 deselected, 75.24s |
| Memory queue/tombstone/version/privacy unit and contract coverage: `python -m pytest -q tests/test_memory_queue_guard.py tests/test_memory_policy.py tests/test_memory_principal.py tests/test_memory_provider.py tests/integration/test_api_assistant_memory.py` | PASS — 109 passed, 11 deselected, 1.42s |
| Disposable PostgreSQL migration + memory/merge integration: `python -m pytest -q -m integration tests/integration/test_api_memory.py tests/integration/test_anonymous_merge.py` | PASS — 51 passed, 2 deprecation warnings, 32.19s |
| Migration head: `cd apps/backend && alembic heads` | PASS — `0018 (head)` |
| Backend compile and repository diff checks: `python -m compileall -q . && git diff --check` | PASS |

The integration run applied the Alembic chain to a disposable PostgreSQL instance and exercised the memory API, consent/version invalidation, tombstone/queue protections, and anonymous merge behavior. The two warnings are Testcontainers deprecations only; they did not affect the result.

## Reproducible synthetic memory evaluation

Commands executed from the repository root:

```bash
python evals/run_memory_extraction_eval.py --report /tmp/m4c-memory-eval.json
python evals/run_memory_extraction_eval.py --report /tmp/m4c-memory-eval-2.json
cmp /tmp/m4c-memory-eval.json /tmp/m4c-memory-eval-2.json
```

Observed on both runs:

```json
{"suite":"memory_extraction_synthetic","mode":"offline_synthetic","records":12,"passed":12,"failed":0,"release_ready":false,"provider_calls":0,"database_writes":0}
```

Both reports were byte-identical at 1761 bytes. Locale counts were `en=5`, `roman_ur=4`, `ur=3`. This is deterministic synthetic contract evidence, not model-quality or production approval.

## Safety gates confirmed from repository artifacts

- `memory_extraction_enabled` defaults to `false`.
- The provider decision remains `BLOCKED_PROVIDER_PRIVACY_DECISION`; no provider is selected.
- The promotion packet remains `BLOCKED` with `release_ready=false`.
- Queue guards reject disabled extraction, stale `memory_version`, replay/retry/worker-restart work, and work at or before a tombstone; newer post-tombstone work is accepted only when explicitly enabled.
- PostgreSQL remains the sole application database.

## Independent QA gate

**Reviewer:** exactly one independent `qa-engineer` review was dispatched against this worktree and evidence artifact. The review was read-only and made no file, commit, push, production, provider, or `release_ready` changes.

**QA VERDICT: PASS**

QA independently verified the exact artifact identity (`HEAD` and `origin/staging` both `f254e975a0b6ec3b3d1b7c3eeff25d3dcccb689a`), current changed-file scope (only this evidence refresh), focused memory coverage (`109 passed, 11 deselected`), disposable PostgreSQL memory/merge integration (`51 passed`, none skipped), full backend suite (`1604 passed, 601 deselected`), compile, `git diff --check`, Alembic head `0018`, and byte-identical synthetic reports (`12/12`, `provider_calls=0`, `database_writes=0`, `release_ready=false`). QA found no readiness-scope blocker. Provider selection, model-backed evaluation, owner approval, and production activation remain blocked.

## Closeout conditions

QA PASS permits committing this readiness-only evidence refresh. Before push, verify the commit manifest, `git diff --check`, and clean status. Push only to `origin/staging`, then verify `git ls-remote origin refs/heads/staging` equals the pushed SHA. Preserve the provider/privacy and Hamza approval blockers; do not claim M4 completion or alter `release_ready`.
