# Accessibility baseline

Automated checks run in CI against the local mock API only (`apps/frontend/e2e/a11y.spec.ts` and `keyboard.spec.ts` via `npm run test:e2e`). The live Playwright configuration is untouched.

## Enforced checks

- axe-core WCAG 2.0/2.1 A and AA scans cover home, collection, product, cart, delivery, admin login, admin dashboard, and admin products.
- Serious or critical violations fail the build, except the two explicitly recorded current baseline exceptions: `color-contrast` and `label-content-name-mismatch`. All violations are attached to the test result as `axe-<page>.json` for review.
- The desktop keyboard path covers the skip link, product quantity, Add to cart, and cart quantity. Mobile runs the axe scans.

## Limitations

- Automated axe does not replace screen-reader, zoom/reflow, focus-order, cognitive, or manual keyboard review.
- Admin orders, product edit forms, staged-ingestion review, dialogs/toasts, error and empty states, and WhatsApp hand-off are not covered.
- Mock data and placeholder images are used; real catalogue alt text and contrast over real photos are unchecked.
- Baseline violation counts are recorded by CI artifacts rather than claimed here; accepted exceptions must be listed after a measured run.

## Coverage floors

- Frontend (`vitest.config.ts`): cart, WhatsApp, API mapping, and admin auth modules; `npm run test:coverage` enforces 75% lines/statements, 70% functions, and 60% branches.
- Backend (`.github/workflows/ci.yml`): pagination and admin-auth modules at 85% and overall coverage at 55%.
