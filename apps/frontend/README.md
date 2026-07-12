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
