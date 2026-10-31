# Elegance Shawls storefront

Next.js storefront for browsing active shawls and stoles and preparing variant-aware WhatsApp order enquiries.

## Development

Copy `.env.example` to `.env.local`, then run:

```bash
npm ci
npm run dev
```

Required public configuration:

- `NEXT_PUBLIC_API_URL` — Elegance FastAPI origin.
- `NEXT_PUBLIC_SITE_URL` — canonical storefront origin.
- `NEXT_PUBLIC_WHATSAPP_NUMBER` — international digits only.

Customer sign-in uses the public API origin through the server-side `/api/customer/session` route. The browser stores only the opaque `cs_customer_session` handle in an HttpOnly cookie; identity-provider credentials, JWKS configuration, session tokens and database URLs are backend/deployment configuration, never `NEXT_PUBLIC_*` values. See [`docs/m4-customer-auth-closeout.md`](../../docs/m4-customer-auth-closeout.md) for the provider-neutral contract and future isolated-staging prerequisites.

## Verification

```bash
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Deployment, security and operational guidance lives in the repository-level `DEPLOYMENT.md`, `OPERATIONS.md` and `LAUNCH_RUNBOOK.md` files.
