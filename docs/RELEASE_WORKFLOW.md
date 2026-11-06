# Elegance Shawls Release and Branch Workflow

## Permanent hierarchy

```text
feature/* | fix/* | ai/* | docs/* | refactor/* | test/* | infra/*
                         |
                         v
integration tier: integration
                         |
                         v
release candidate: staging
                         |
                         v
production: main
```

`integration` is the canonical integration branch. It was named `staging-integration` until 2026-11-06; it was renamed after the historical `integration/local-complete` namespace collision was resolved (that branch was fully merged into the integration tier and retired). The old name was retired only after CI, branch protection, open PR bases, documentation and agent instructions had moved to `integration`.

## Pull-request gates

1. New work starts from the latest `origin/integration` in an isolated worktree. Do not use a dirty canonical checkout.
2. Feature/fix/AI/docs branches open PRs into `integration`; no direct pushes to permanent branches.
3. A PR must identify scope, migration/config impact, rollback plan, test commands, QA evidence, and any linked issue/project item.
4. CI must be green for the changed surface. Backend/database changes require backend tests, compile checks, and integration tests when available; frontend changes require lint, typecheck, unit tests, build, and relevant Playwright coverage. Evaluation suites must distinguish `PASS`, `FAIL`, and `NOT EVALUATED`; `NOT EVALUATED` blocks release readiness.
5. Independent QA must test the exact immutable candidate SHA. Implementation tests are not independent QA. A failed or blocked QA run is not a pass.
6. Only completed, QA-approved changes are eligible for integration. Do not blind-cherry-pick a branch whose migration/API contract differs from the target; reconcile the target contract first and port only the required behavior.
7. Promote from `integration` to `staging` only through a PR containing the exact candidate SHA and fresh regression evidence. Fixes found on staging return to the integration tier first.
8. Promote from `staging` to `main` only through an explicitly approved production promotion. This document does not authorize deployment, VPS changes, production mutations, credential changes, or `release_ready` changes.

## Protection baseline

The permanent branches are protected with required CI contexts (`frontend`, `backend`, `containers`, `e2e`) and strict checks on `main`; `staging` and `integration` currently require the same contexts with non-strict status-check ordering. Review-count and administrator-enforcement settings remain subject to the repository's GitHub ruleset and owner governance. Do not bypass required checks or force-push protected branches.

## Reconciliation and cleanup policy

The repeatable audit and cleanup procedure, with the worktree and archive rules, is in `docs/REPO_HYGIENE.md` (read-only audit: `scripts/repo_audit.sh`).

Before cleanup, produce a durable audit covering every local/remote branch and worktree, SHA, dirty state, ancestry/tree/patch equivalence against `main`, `staging`, and `integration`, open PR/issue/project/CI references, active workers, and QA evidence. Classify from evidence, not branch names.

- Always retain permanent branches.
- Retain active, linked, dirty, detached-QA, ambiguous, blocked, or unique work. Preserve uncommitted changes and untracked evidence.
- For a branch proven merged/superseded/obsolete and confirmed clean/inactive, first create `archive/reconciliation/<UTC-date>-<source>` and push it where possible. Verify archive SHA equals the source SHA and record the verification.
- Only after archive verification may the source branch and its clean inactive worktree be removed with ordinary non-force operations.
- Never use `reset --hard`, broad `git clean`, force-push, blind branch deletion, or history rewriting. `git worktree prune` is limited to demonstrably stale metadata for missing paths.
- Every archive/removal decision, retained blocker, and final SHA belongs in a durable reconciliation checkpoint.

## Current reconciliation checkpoint

See `docs/reconciliation/2026-11-06-branch-reconciliation-audit.md` and its machine-readable `.json` companion for the complete inventory and evidence snapshot. The audit records why the exact `integration` ref was not created and why active/dirty/ambiguous work was retained.
