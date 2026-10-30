# Launch runbook

## Current decision

The repository-controlled storefront and API are launch-complete only after the external configuration and Quill integration gates below are satisfied. Do not direct customers to production while any required gate is unchecked.

## 1. Infrastructure

- Set final HTTPS `SITE_URL` and `API_URL`, the international-digit `WHATSAPP_NUMBER`, the production PostgreSQL passwords (`POSTGRES_*`) and, only while integrations still need it, a randomly generated legacy `ADMIN_API_KEY` with a near `ADMIN_LEGACY_KEY_EXPIRES_AT`. After the schema (including migration 0007) is applied, create the first owner: `python scripts/admin_accounts.py bootstrap-owner --email <owner>` from `apps/backend` (password via `ADMIN_ACCOUNT_PASSWORD` or prompt), then sign in at `/admin/login` and create `editor`/`viewer` accounts for other people.
- Keep PostgreSQL on the internal network (no published port) with the least-privilege application role, and apply the schema with the approved `migrate` step before the first start.
- Build immutable frontend/backend images from a commit with green CI.
- Configure DNS, TLS, reverse proxy request limits and the four documented health/readiness probes.
- Complete an encrypted backup to an owner-approved off-server S3-compatible destination and an isolated restore drill, and record the drill evidence file (`OPERATIONS.md`). **Open:** the tooling is built, but the destination, its free-tier/cost approval, credentials, scheduling and production activation are owner actions that have not happened.

## 2. Quill compatibility — blocking

The currently accessible `Muhammad-Hamza-Khan-03/quill-panel` is not compatible with this production API and must be updated before it is used:

- It currently calls old `/admin/products` routes; this API exposes `/products/admin/*`.
- It submits multipart `product_data`; this API accepts the documented JSON product schema.
- It calls `/admin/verify-key`, which this API does not expose.
- It reads the secret from `NEXT_PUBLIC_ADMIN_KEY`, which places the administrative credential in browser-delivered code. (The Elegance admin UI itself no longer uses a shared key: it signs in individual accounts.)
- Its category, scraper and media routes are not part of the Elegance API.

Use a server-side Quill proxy/session so the browser never receives a backend credential. Quill has no individual account integration yet, so until it does the trusted server may attach the legacy `X-Admin-Key` (`ADMIN_API_KEY`), which works only until `ADMIN_LEGACY_KEY_EXPIRES_AT` and is audited as `legacy-shared-key`; plan Quill's move to an individual account (`X-Admin-Session` from `/v1/admin/auth/login`) before that date. Map Quill product fields to the OpenAPI schema and explicitly support create, update, status changes, stock changes and archive.

## 3. Staging acceptance

1. Confirm unauthenticated, expired-session and incorrect-credential admin requests return 401 (and are recorded in `audit_log` as denied), a `viewer` write returns 403, and an expired or unset `ADMIN_LEGACY_KEY_EXPIRES_AT` rejects `X-Admin-Key`.
2. From the updated Quill deployment, create a uniquely named draft product with two variants.
3. Verify the draft is visible in the admin feed and absent from public endpoints.
4. Publish it and confirm it appears on the storefront with the correct slug, images, price, SKU, options and stock.
5. Change one variant to zero stock and verify the storefront disables it.
6. Unpublish the product and confirm public slug/list endpoints no longer expose it.
7. Publish again, then archive it and confirm it remains absent publicly.
8. Verify no session token, password or legacy admin key appears in browser source, network responses, analytics or logs, and that the staging mutations above appear in `audit_log` attributed to the signing-in account.

## 4. Customer acceptance

- Test homepage, navigation, browsing, search, category filtering, sorting and both pagination pages on desktop and a real mobile device.
- Test gallery, available/out-of-stock options, quantity limits, price and total.
- Inspect the WhatsApp message for product, colour, size, quantity, SKU, unit price, total and absolute production URL.
- Test API failure/retry, empty catalogue, missing product, ordering-disabled configuration and mobile sticky ordering action.
- Review delivery, returns, privacy, terms and contact wording with the business owner.

## 5. Go live

1. Record the deployed commit and immutable image digests.
2. Confirm CI, health, readiness, logs and alerts are green.
3. Take a pre-launch database backup with `scripts/pg_backup.py backup` and run `verify` on it (blocked until the off-server destination and credentials above exist; do not skip).
4. Run one final Quill publish-to-storefront smoke test and remove the test product.
5. Enable public traffic and watch errors, latency, resources and readiness continuously during the launch window.

## Rollback

If a repository-controlled failure appears, stop further deployment, restore the previous frontend and backend image tags together, verify readiness, and preserve logs. Do not roll back or delete database data unless a verified restore is explicitly required.
