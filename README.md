# Elegance Shawls

Production-oriented WhatsApp storefront for shawls and stoles. The repository contains a Next.js customer storefront and a FastAPI/MongoDB product service designed to receive authenticated product changes from Quill Panel.

## Applications

- `apps/frontend` — Next.js storefront, product discovery and WhatsApp ordering.
- `apps/backend` — FastAPI public product feed and authenticated product-management API.

## Local verification

```bash
cd apps/frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e

cd ../backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Copy each `.env.example` to `.env` for local development. Never commit `.env` files or real keys. Production setup and operations are documented in [DEPLOYMENT.md](DEPLOYMENT.md) and [OPERATIONS.md](OPERATIONS.md).
