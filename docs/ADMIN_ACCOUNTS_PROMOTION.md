# Promoting individual admin accounts to `main` (issue #145)

Status: **plan only.** Nothing here promotes, deploys or migrates anything. `main` still authenticates admin with the shared `ADMIN_API_KEY`; the account system lives on `integration` (and `staging` once promoted).

## What is being promoted

- Migration `0010_admin_accounts` (tables `admin_accounts`, `admin_sessions`; audit log extensions). `0001`-`0009` are identical on `main` and `integration`, so `main` is at head `0009` and 0010 is the first step.
- `security/admin_auth.py` with roles `viewer`/`editor`/`owner`, audit-before-mutation (an audit failure refuses the request), and the legacy key honoured only until `ADMIN_LEGACY_KEY_EXPIRES_AT`.
- Frontend proxy pattern (`/api/admin/*`, HttpOnly `es_admin_session` cookie). The browser never holds a backend credential other than the opaque session token.

Note: documents previously called this migration "0007"; it is 0010.

## Preconditions (all must hold before a PR to `main`)

1. CI green on the exact `staging` SHA chosen, including `backend-integration` (admin account and migration tests) and `e2e-real-stack`.
2. Independent QA of the staging candidate recorded in `docs/qa/`. The account system has not been penetration-tested; say so in the PR.
3. A pg_dump taken immediately before the migration, stored off the server (backups are not yet activated, see #105; until then this is a manual step).
4. The owner has decided the legacy-key retirement date. Recommended: set `ADMIN_LEGACY_KEY_EXPIRES_AT` to a near future instant at promotion, so the shared key stops working without a redeploy.
5. The first owner is created right after `alembic upgrade head`: `python scripts/admin_accounts.py bootstrap-owner --email <owner>` (password from `ADMIN_ACCOUNT_PASSWORD` or a prompt). Nobody can sign in to the new admin until this is done, so do it in the same maintenance window.
6. Quill or any other server that calls `/products/admin/*` is either moved to an individual account (`X-Admin-Session`) or is covered by the legacy expiry window.

## Order of operations (production window)

1. Announce the window; confirm the pg_dump exists and restores in a disposable database.
2. Deploy the backend image built from the promoted SHA (without the frontend yet), run `alembic upgrade head`.
3. `bootstrap-owner`; sign in through the new frontend; confirm `GET /v1/admin/auth/me`.
4. Deploy the frontend. Create `editor`/`viewer` accounts as needed through `/v1/admin/accounts`.
5. Verify: one product edit appears in `GET /v1/admin/audit` attributed to the account; a request without a credential is 401; a `viewer` write is 403.
6. Let `ADMIN_LEGACY_KEY_EXPIRES_AT` pass or empty both variables.

## Rollback

- **Application only** (no migration yet or the migration is kept): `deploy/rollback.sh <previous-sha>`. The old shared-key code still works with the new tables present.
- **Database:** `alembic downgrade 0009` refuses if accounts, sessions or audit details exist, unless `ALEMBIC_ALLOW_ADMIN_DATA_LOSS=1` is set. Only use it after a pg_dump, and accept that account data and attributed audit detail are lost. Prefer rolling the application back and keeping the additive tables.
- **Locked out:** if no owner can sign in, run `bootstrap-owner` (creates one only when no active owner exists) or `reset-password`.

## Known limits

- Sessions are opaque server-side tokens, so revocation is immediate but every request costs a lookup.
- The login throttle in the frontend is per process; the backend enforces lockout per account.
- Not independently penetration-tested.
