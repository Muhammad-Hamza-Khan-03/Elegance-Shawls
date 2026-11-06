# M4 Batch A independent QA record

**Scope:** synthetic customer identity/session handling and conservative anonymous event merge only. No production, VPS, deploy, `main`, live credentials, or customer data were used.

## Artifact

- Worktree: `/home/hamza/qa-m1-s4-clean`
- Candidate implementation HEAD at QA: `f5d8d0787f21da8b1c7645244325dc6b946b9922`
- Base: `origin/staging` (`7e319d5348dc3ef97aa2f6e278cf85528a3d9469`), confirmed ancestor
- Implementation commits: `34acec3` and `f5d8d07`
- QA owner: independent `qa-engineer` task

## Evidence

- Focused PostgreSQL integration tests (disposable local Docker/Testcontainers PostgreSQL): **41 passed, 2 deprecation warnings**
  - `tests/integration/test_anonymous_merge.py`
  - `tests/integration/test_api_customer_auth.py`
  - `tests/integration/test_customer_sessions_migration.py`
  - `tests/integration/test_upgrade_from_0009.py`
- Independent QA rerun of container-free identity/config/policy/customer/session tests: **110 passed**.
- Backend canonical suite: **1598 passed, 597 deselected**.
- Backend `python -m compileall -q .`: **PASS**.
- Frontend canonical suite: **394 passed** across 32 files.
- Frontend `npm run lint`: **PASS**.
- Frontend `npm run typecheck`: **PASS** after clean `npm ci --ignore-scripts`.
- `git diff --check`: **PASS**.

## Acceptance findings

Independent QA verdict: **QA_PASS**.

- Explicit consent, DNT/GPC refusal, signed anonymous-session ownership proof, freshness and event-count limits, and existing-owner refusal: PASS.
- Customer isolation and replay behavior: PASS; the ledger is unique and advisory locking serializes merges.
- Audit/event/ledger transaction rollback: PASS.
- Merge changes only `events.customer_id`; authenticated memory is not imported or overwritten: PASS.
- Verified issuer binding and hashed identity subjects: PASS.
- Session expiry, logout, logout-all, session cap, customer isolation, and exchange idempotency: PASS.
- Migration 0016 additive upgrade/downgrade behavior and upgrade-from-0009 path: PASS.
- Diff scope contains only Batch A identity/auth, migration, tests, customer session route, and documentation changes; no deployment or production changes: PASS.

## Non-blocking limitations

- Existing local fixture rows with bare identity subjects are intentionally not auto-linked after issuer-bound hashing; disposable fixtures should be recreated rather than inferred.
- The QA did not stress the narrow concurrent exchange/idempotency-key race or exact 24-hour/100-event boundaries.
- QA used the Hermes Python 3.11 environment rather than CI Python 3.12. No shared/staging/production database was touched.

This record is evidence for the exact QA-passed local artifact and does not set `release_ready` or authorize deployment.
