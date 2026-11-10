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

## 6. WhatsApp automation (optional; skip entirely to stay in link mode)

Decision recorded: reply automation stays on the unofficial bridge (owner approval, 2026-11-06); the Cloud API remains the official fallback if the number is ever restricted. Do not enable until every box is checked.

- [ ] Stage 2 VPS runs the production `compose.yaml` with `--profile whatsapp` (Redis with `noeviction`, bridge, consumer); the bridge is on `data` and `whatsapp_egress` only, never `web`, no published port.
- [ ] Migrations 0019 and 0020 applied after a verified backup; `ALEMBIC_ALLOW_WHATSAPP_DATA_LOSS` unset.
- [ ] `WHATSAPP_BRIDGE_TOKEN`, `REDIS_PASSWORD` set; if `WHATSAPP_AUTH_STORE=postgres`: role script run, `WHATSAPP_AUTH_ENCRYPTION_KEY` stored in the secret manager (not in backups).
- [ ] Privacy policy published with the order-chat wording (owner/legal review of `apps/frontend/src/app/privacy/page.tsx`, including current Pakistani data-protection requirements) before the first customer chat is stored.
- [ ] Urdu templates (`apps/backend/whatsapp/templates/replies.yaml`) reviewed by a native speaker.
- [ ] Monitoring wired (`scripts/whatsapp_monitor.py --check` on a schedule, alert on non-zero) and retention purge scheduled monthly.
- [ ] Rollout on a throwaway number first; then the shop number with `WHATSAPP_REPLY_ALLOWLIST` = staff numbers for at least a week; only then clear the allowlist.
- [ ] Shop phone is used daily (WhatsApp unlinks companion devices after 14 days of primary-phone inactivity) and staff know typing in a chat silences the bot there for 12 hours.
- [ ] Emergency off rehearsed: `WHATSAPP_BRIDGE_ENABLED=false` then `docker compose --profile whatsapp up -d`, and removing the device under Linked Devices.
- [ ] Read "WhatsApp: known limits and deliberate shortcuts" in `OPERATIONS.md` and accept each item.
- [ ] `WHATSAPP_ASSISTANT_ENABLED` and `WHATSAPP_VOICE_ENABLED` stay off until the ASR endpoint is self-hosted and declared and the owner has approved each.
