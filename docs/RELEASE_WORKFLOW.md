# Staging-first release workflow

Elegance Shawls uses one protected `main` branch and short-lived feature, fix, and documentation branches. GitHub Issues and pull requests are the system of record; every pull request runs CI before merge. Vercel Preview is used for branch review, and staging must be isolated from production.

## Release sequence

1. Open or update a GitHub Issue with acceptance criteria and rollback notes.
2. Create a short-lived branch from the current `main` SHA.
3. Open a pull request into `main`. CI must pass: frontend, backend, containers, and E2E.
4. Deploy the exact branch SHA to Vercel Preview and the reusable isolated Render staging service, backed by the isolated Atlas staging database.
5. Run independent QA against the staging tuple: exact frontend deployment/SHA, Render service/deployment/SHA, staging database, staging-only credentials, and approved CORS origin. Record pass/fail evidence; production data and credentials are never used.
6. Squash merge only after review, CI, and QA gates pass.
7. Wait for CI on the resulting `main` commit. The merge result—not the feature-branch SHA—is the production candidate.
8. Explicitly deploy that exact `main` SHA to production. Record immutable Vercel and Render deployment IDs.
9. Run production smoke tests (storefront, `/api/health`, backend `/health/` and `/ready/`, and relevant non-mutating routes). Stop and roll back if a check fails.
10. Write a release record containing the issue/PR, resulting SHA, deployment IDs, timestamps, checks, and rollback decision.

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
