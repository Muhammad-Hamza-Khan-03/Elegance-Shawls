# M4 Batch C formal acceptance evidence

**Artifact:** M4 Batch C privacy-readiness worktree `ai/m4-batch-c-readiness`
**Base candidate:** `394e74828ec5a60b7fe1cb68c5db1d4c3b64056c` (origin/staging before this evidence-only closeout)
**Scope:** readiness evidence only; no production activation, provider selection, spend, credentials, customer data, deployment, VPS, main, issue closure, or `release_ready`.

## Scope reconciliation

The candidate's existing Batch C implementation scope was limited to the following tracked paths:

- memory privacy epoch / queue guard implementation and tests
- consent/correction epoch invalidation rework and its PostgreSQL integration assertions
- Alembic migration `0018_memory_privacy_epoch.py`
- synthetic memory evaluation fixture and deterministic offline runner
- provider privacy decision, promotion packet, roadmap/contract records
- this formal acceptance evidence record

No CHANGELOG change was expected or added: the Batch C readiness contract is represented by the listed implementation, evaluation, and decision artifacts. No unrelated untracked files were present; frontend `node_modules` and build output are ignored dependencies/artifacts.

## Canonical verification

All commands were run from the repository worktree unless noted.

| Check | Result |
|---|---|
| Backend canonical suite: `cd apps/backend && pytest -q` | PASS — 1604 passed, 601 deselected |
| Backend compile: `cd apps/backend && python -m compileall -q .` | PASS |
| PostgreSQL integration: `pytest -q -m integration tests/integration/test_api_memory.py tests/integration/test_anonymous_merge.py` | PASS — 51 passed, 2 deprecation warnings |
| Queue-guard focused tests plus config: `pytest -q tests/test_memory_queue_guard.py tests/test_customer_auth_config.py` | PASS — 28 passed |
| Migration head: `cd apps/backend && alembic heads` | PASS — `0018 (head)` |
| Frontend dependency setup: `cd apps/frontend && npm ci` | PASS — 428 packages audited; npm reported 8 moderate audit findings |
| Frontend lint/typecheck/tests/build | PASS — lint, typecheck, 32 files / 394 tests, and Next production build |
| Commit/worktree diff validation: `git diff --check` | PASS after removal of pre-existing trailing whitespace in three Batch C docs |

`check_migration_stamp.py` was not run against a database URL because no `DATABASE_URL` was configured in the shell. Disposable PostgreSQL integration tests did apply and exercise the migration chain; no shared or production database was touched.

## Reproducible synthetic memory evaluation

Commands:

```bash
python evals/run_memory_extraction_eval.py --report /tmp/m4c-memory-eval.json
python evals/run_memory_extraction_eval.py --report /tmp/m4c-memory-eval-2.json
cmp /tmp/m4c-memory-eval.json /tmp/m4c-memory-eval-2.json
```

Observed result on both runs:

```json
{"suite":"memory_extraction_synthetic","mode":"offline_synthetic","records":12,"passed":12,"failed":0,"release_ready":false,"provider_calls":0,"database_writes":0}
```

Locale counts were `en=5`, `roman_ur=4`, `ur=3`. The report bytes were identical across the two runs. This is deterministic synthetic contract evidence, not model-quality or production approval.

## Safety gates confirmed

- `memory_extraction_enabled` defaults to `false`.
- The provider decision remains `BLOCKED_PROVIDER_PRIVACY_DECISION`; no provider is selected.
- The promotion packet remains `BLOCKED` with `release_ready=false`.
- Queue guards reject disabled extraction, stale `memory_version`, replay/retry/worker-restart work, and work at or before a tombstone; newer post-tombstone work is accepted only when the feature is explicitly enabled.
- PostgreSQL remains the sole application database.

## Independent QA

**Reviewer:** exactly one independent `qa-engineer` owner; the same owner performed the required re-QA after bounded manager rework.

**Initial verdict:** `FAIL`. The reviewer found that consent correction/revocation did not bump `customers.memory_version`, allowing stale queued work through after revoke/regrant.

**Bounded rework:** `memory/service.py` now bumps the epoch on every real consent-state change and every real memory correction; idempotent repeats remain no-ops. PostgreSQL integration assertions cover both behaviors.

**Re-QA verdict:** `PASS`.

Re-QA independently verified the exact revised worktree: focused queue/config tests `28 passed`; disposable PostgreSQL memory/merge integration `51 passed`; backend compilation and `git diff --check` passed; migration `0018` is the Alembic head; and the synthetic evaluation produced byte-identical two-run reports with `12/12`, `provider_calls=0`, `database_writes=0`, and `release_ready=false`. Memory extraction remained disabled and the provider/promotion gates remained blocked. QA left the worktree unchanged.

## Closeout conditions

Commit and push are permitted now that QA has recorded a terminal `PASS`. The final closeout must verify the commit changed-file manifest, `git diff --check`, clean worktree, `git ls-remote origin refs/heads/staging` equal to the pushed SHA, and preserve the provider/privacy and Hamza approval blockers.
