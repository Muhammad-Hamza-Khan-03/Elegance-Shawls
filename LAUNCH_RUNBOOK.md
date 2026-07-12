# Launch runbook

## Current decision

The repository-controlled storefront and API are launch-complete only after the external configuration and Quill integration gates below are satisfied. Do not direct customers to production while any required gate is unchecked.

## 1. Infrastructure

- Set final HTTPS `SITE_URL` and `API_URL`, the international-digit `WHATSAPP_NUMBER`, a randomly generated `ADMIN_API_KEY`, and production MongoDB settings.
- Restrict MongoDB to private authenticated TLS access and use a least-privilege database user.
- Build immutable frontend/backend images from a commit with green CI.
- Configure DNS, TLS, reverse proxy request limits and the four documented health/readiness probes.
- Complete an encrypted backup and an isolated restore drill.

## 2. Quill compatibility — blocking

The currently accessible `Muhammad-Hamza-Khan-03/quill-panel` is not compatible with this production API and must be updated before it is used:

- It currently calls old `/admin/products` routes; this API exposes `/products/admin/*`.
- It submits multipart `product_data`; this API accepts the documented JSON product schema.
- It calls `/admin/verify-key`, which this API does not expose.
- It reads the secret from `NEXT_PUBLIC_ADMIN_KEY`, which places the administrative credential in browser-delivered code.
- Its category, scraper and media routes are not part of the Elegance API.

Use a server-side Quill proxy/session so the browser never receives `ADMIN_API_KEY`. The trusted server must attach `X-Admin-Key` to the Elegance admin API. Map Quill product fields to the OpenAPI schema and explicitly support create, update, status changes, stock changes and archive.

## 3. Staging acceptance

1. Confirm unauthenticated and incorrect-key admin requests return 401, and an unconfigured admin API returns 503.
2. From the updated Quill deployment, create a uniquely named draft product with two variants.
3. Verify the draft is visible in the admin feed and absent from public endpoints.
4. Publish it and confirm it appears on the storefront with the correct slug, images, price, SKU, options and stock.
5. Change one variant to zero stock and verify the storefront disables it.
6. Unpublish the product and confirm public slug/list endpoints no longer expose it.
7. Publish again, then archive it and confirm it remains absent publicly.
8. Verify no admin key appears in browser source, network responses, analytics or logs.

## 4. Customer acceptance

- Test homepage, navigation, browsing, search, category filtering, sorting and both pagination pages on desktop and a real mobile device.
- Test gallery, available/out-of-stock options, quantity limits, price and total.
- Inspect the WhatsApp message for product, colour, size, quantity, SKU, unit price, total and absolute production URL.
- Test API failure/retry, empty catalogue, missing product, ordering-disabled configuration and mobile sticky ordering action.
- Review delivery, returns, privacy, terms and contact wording with the business owner.

## 5. Go live

1. Record the deployed commit and immutable image digests.
2. Confirm CI, health, readiness, logs and alerts are green.
3. Take a pre-launch database backup.
4. Run one final Quill publish-to-storefront smoke test and remove the test product.
5. Enable public traffic and watch errors, latency, resources and readiness continuously during the launch window.

## Rollback

If a repository-controlled failure appears, stop further deployment, restore the previous frontend and backend image tags together, verify readiness, and preserve logs. Do not roll back or delete database data unless a verified restore is explicitly required.
