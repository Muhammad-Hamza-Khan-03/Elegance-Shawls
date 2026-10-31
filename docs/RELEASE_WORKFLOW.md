# Staging-first release workflow

Elegance Shawls has exactly three permanent branches. Everything else is a short-lived branch that is deleted after it is integrated. GitHub Issues and pull requests are the system of record.

```text
feature/* fix/* ai/* docs/* refactor/* test/* infra/*
        |  PR + CI
        v
staging-integration   development source of truth (shared, may hold several features)
        |  PR + CI, a chosen release-candidate SHA
        v
staging               release-candidate source of truth (QA / UAT)
        |  PR + QA evidence + explicit approval
        v
main                  production source of truth
```

| Branch | Role | Environment | Who/what may change it |
|---|---|---|---|
| `staging-integration` | Active development and integration | Vercel Preview / local | PRs from short-lived branches |
| `staging` | Release candidates, QA, UAT | Isolated staging (not yet provisioned, see below) | PRs from `staging-integration` only |
| `main` | Production | Production | PRs from `staging` only, with explicit approval (hotfixes excepted, see below) |

`staging` was initialised at the production SHA (`283b27e`) so the first promotion is a reviewed diff. Nothing is promoted automatically.

## Day-to-day development

1. Open or update a GitHub Issue with acceptance criteria and rollback notes.
2. Fetch, then create a short-lived branch from the latest `origin/staging-integration` (never from `main`). Allowed prefixes: `feature/`, `fix/`, `ai/`, `docs/`, `refactor/`, `test/`, `infra/`, `hotfix/` (hotfix branches start from `main`).
3. Implement, run the relevant tests, commit (conventional commits), push.
4. Open a PR targeting `staging-integration`. CI must pass. Squash merge (the only merge method the repo allows). The head branch is deleted on merge.

## Promoting to staging

1. Compare `staging-integration` with `staging` (`git log origin/staging..origin/staging-integration`) and choose the release candidate. It must be a green `staging-integration` SHA; unfinished features should be reverted or left out before choosing it.
2. Open a PR from `staging-integration` (or a branch cut from the chosen SHA) into `staging`. Record the candidate SHA in the PR description.
3. CI must pass: frontend, backend, backend-integration (includes migration validation and the upgrade-from-0009 test), containers, e2e, evals. Fixture-only AI evals are not release evidence; "not evaluated" blocks release.
4. Deploy that exact SHA to isolated staging and run QA. Record pass/fail evidence against the SHA.
5. Fixes found in staging are made on `staging-integration` first and re-promoted. They are not committed directly to `staging`.

## Promoting to production

1. Use only a `staging` SHA that has CI success and recorded QA evidence.
2. Review migrations (`apps/backend/migrations`), write release notes and the rollback procedure.
3. Get explicit approval. Open a PR from `staging` into `main` and squash merge after review.
4. Wait for CI on the resulting `main` commit; that merge result is the production candidate.
5. Explicitly deploy that exact `main` SHA. Record immutable Vercel and Render deployment IDs.
6. Run production smoke tests (storefront, `/api/health`, backend `/health/` and `/ready/`, non-mutating routes). Stop and roll back if a check fails.
7. Write a release record: issue/PR, resulting SHA, deployment IDs, timestamps, checks, rollback decision.

After a squash merge into `main`, fast-forward is not possible; merge `main` back into `staging` and then `staging-integration` through PRs so the branches share ancestry again.

## Production hotfixes

1. Create `hotfix/<description>` from the latest `main`.
2. Fix, test, and get explicit approval before merging to `main`; release through the normal explicit deploy.
3. Propagate the fix: open PRs carrying the same fix into `staging-integration` and into `staging` (cherry-pick the hotfix commit; do not merge unrelated unfinished work into `staging`).

## Retiring branches

Delete a short-lived branch only when its commits are reachable from `staging-integration` (or its replacement is documented), it has no open PR, no active worktree and no deployment reference. Use non-forced deletes. Never delete `main`, `staging` or `staging-integration`; never delete tags. Audit periodically with `git branch -r --merged origin/staging-integration`.

## CI triggers

`.github/workflows/ci.yml` runs on every pull request (any base) and on pushes to `main`, `staging` and `staging-integration`. Required status checks are configured in GitHub branch protection; they must match job names that actually run on that branch.

## Hosting controls and boundaries

- Render production automatic deploys should be disabled so production requires an explicit deploy of an exact `main` SHA. This is a provider setting and must be verified in Render after any change; source files alone are not evidence.
- Vercel production deployment controls should prevent an unreviewed branch from becoming production. Preview deployments remain enabled for feature branches. The Vercel project setting and the live production deployment must be verified in the provider UI/API.
- If a provider control is unavailable or a change could risk downtime, do not guess or change it. Record the exact provider limitation as a follow-up and preserve the live production deployment.
- No GitFlow, Kubernetes, new hosting platform, or production catalog migration is part of this workflow.

## Staging conventions

The reusable staging target is an isolated Render service and an isolated Atlas database (for example, a `staging`-named database), each with separate credentials and a staging-only admin key. Never copy production secrets into staging or Vercel Preview. Use disposable, clearly marked QA fixtures only; remove them after QA. Products are added manually through the built-in admin after the workflow is accepted. The legacy catalog is not imported.

As of the baseline record, the isolated Render/Atlas staging tuple is **not provisioned/verified**. Until it exists and its exact credentials, CORS, deployment SHA, and cleanup procedure are recorded, staging QA is blocked; Vercel Preview alone is not an independent staging gate.

## Rollback

For an application failure, stop promotion, identify the last known-good immutable Vercel/Render deployment IDs, redeploy those artifacts, and rerun health/smoke checks. Do not delete or rewrite production catalog data as part of an application rollback. Database restore is a separate, tested procedure.

## Release record minimum

Record: issue and PR URLs; merged `main` SHA; Vercel Preview and production deployment IDs/URLs; Render staging and production deployment IDs/URLs; QA evidence and reviewer; production smoke results; exact timestamps; and rollback status. Never record secret values.

## Current verified boundaries

- Production baseline is infrastructure readiness, not a commercial launch; the catalog is intentionally empty and no legacy records are to be imported.
- Atlas network access must retain only `74.220.52.0/24` and `74.220.60.0/24`; `0.0.0.0/0` must remain removed.
- The baseline's provider-control verification and isolated staging provisioning remain explicit follow-ups where evidence is absent.
