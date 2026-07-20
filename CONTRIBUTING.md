# Contributing to Elegance Shawls

Thanks for contributing to Elegance Shawls.

This repository contains a production-oriented commerce stack with:
- a Next.js storefront in `apps/frontend`
- a FastAPI + MongoDB product API in `apps/backend`

Please treat contributions as production changes, not casual demo edits.

## Principles

- preserve customer-facing reliability
- prefer clarity over cleverness
- keep operational safety in mind
- avoid breaking product API contracts without documenting the change
- never commit secrets, real credentials, or production `.env` files

## Before you start

1. Sync with the latest `main`
2. Read `README.md`
3. Read `DEPLOYMENT.md` and `OPERATIONS.md` if your change affects runtime behavior
4. Read `LAUNCH_RUNBOOK.md` if your change affects production launch or admin flows

## Local setup

### Frontend
```bash
cd apps/frontend
cp .env.example .env
npm ci
npm run dev
```

### Backend
```bash
cd apps/backend
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8000
```

## Validation checklist

### Frontend
```bash
cd apps/frontend
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

### Backend
```bash
cd apps/backend
. .venv/bin/activate
pytest -q
python -m compileall -q .
```

## Contribution workflow

1. Create a focused branch
2. Keep changes small and reviewable
3. Update documentation when behavior changes
4. Run relevant validation locally
5. Write clear commit messages
6. Open a PR with a concise summary and test notes

## Commit style

Use conventional commit prefixes where possible:
- `feat:` new functionality
- `fix:` bug fixes
- `docs:` documentation changes
- `refactor:` structure changes without intended behavior change
- `test:` test additions or fixes
- `ci:` CI/CD changes
- `chore:` maintenance work

Examples:
- `feat: add stock-aware storefront product selection`
- `fix: correct admin product status update handling`
- `docs: improve deployment and setup guidance`

## Pull request expectations

A good PR should include:
- what changed
- why it changed
- impacted areas
- how it was tested
- screenshots if the storefront/admin UX changed
- migration or rollout notes if env/config/contracts changed

## Documentation expectations

Update docs when you change:
- environment variables
- setup steps
- deployment flow
- health checks
- API behavior
- operational procedures

At minimum, review whether these files need updates:
- `README.md`
- `DEPLOYMENT.md`
- `OPERATIONS.md`
- `LAUNCH_RUNBOOK.md`

## Security rules

- never commit secrets
- never expose `ADMIN_API_KEY` in public docs with real values
- never log sensitive production credentials in examples
- keep CORS and production origins explicit
- preserve least-privilege assumptions around database and admin access

## If your change affects production behavior

Call it out explicitly in the PR description and include:
- risk level
- rollback plan
- required env/config updates
- whether customer-facing behavior changes

## Questions to ask before merging

- Is this change production-safe?
- Is the README/setup still accurate?
- Are deployment/operations docs still accurate?
- Are tests and verification steps sufficient for this change?
