# MONOREPO FOLDER STRUCTURE

**Repository Root: `ecommerce-monorepo/`**

```
ecommerce-monorepo/
│
├── apps/
│   ├── frontend/                # Next.js 14 App Router
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── public/
│   │   ├── styles/
│   │   ├── utils/
│   │   ├── types/
│   │   ├── service/             # API client layer for FastAPI
│   │   ├── store/               # Zustand store (cart etc)
│   │   ├── config/
│   │   └── package.json
│   │
│   ├── backend/                 # FastAPI service
│   │   ├── src/
│   │   │   ├── api/             # Routers
│   │   │   │   ├── auth.py
│   │   │   │   ├── products.py
│   │   │   │   ├── variants.py
│   │   │   │   ├── orders.py
│   │   │   │   └── admin.py
│   │   │   ├── core/            # Core app configs
│   │   │   │   ├── config.py
│   │   │   │   ├── security.py
│   │   │   │   ├── email.py
│   │   │   │   └── database.py
│   │   │   ├── models/          # SQLAlchemy ORM Models
│   │   │   ├── schemas/         # Pydantic Schemas
│   │   │   ├── services/        # Business logic (CRUD etc.)
│   │   │   ├── utils/
│   │   │   └── main.py          # FastAPI entrypoint
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── admin-panel/ (optional if separate UI)
│       └── ... (Can reuse frontend if integrated)
│
│
├── packages/
│   ├── shared-types/            # Shared TS interfaces for frontend ↔ backend
│   │   ├── product.ts
│   │   ├── variant.ts
│   │   ├── order.ts
│   │   ├── user.ts
│   │   └── package.json
│   │
│   ├── shared-utils/            # Cross-app utilities
│   │   ├── formatting/
│   │   ├── validations/
│   │   ├── constants/
│   │   └── package.json
│   │
│   └── shared-config/           # Common config for monorepo
│       ├── eslint/
│       ├── prettier/
│       ├── tailwind/
│       └── package.json
│
├── infra/
│   ├── docker/                  # Docker configs for local dev
│   │   ├── fastapi.Dockerfile   
│   │   ├── docker-compose.yml
│   │   └── nginx/
│   │       └── default.conf
│   ├── supabase/                # SQL schema migrations
│   │   ├── migrations/
│   │   │   ├── 001_init.sql
│   │   │   ├── 002_variants.sql
│   │   │   └── ...
│   │   └── seed.sql
│   ├── cloudinary/              # Upload presets
│   └── resend/                  # Email templates
│
├── .github/
│   ├── workflows/
│   │   ├── deploy-frontend.yml
│   │   ├── deploy-backend.yml
│   │   └── test.yml
│
├── scripts/                     # Automation scripts
│   ├── deploy.sh
│   ├── backup-db.sh
│   ├── seed-products.py
│   └── generate-sitemap.js
│
├── docs/                        # Documentation for devs
│   ├── API-CONTRACT.md
│   ├── ARCHITECTURE.md
│   ├── DB-DESIGN.md
│   └── SETUP-GUIDE.md
│
├── .env                         # Root environment (not committed)
├── turbo.json or nx.json (optional for monorepo tooling)
├── package.json                 # Root-level workspace definitions
└── README.md
```

---

# DETAILED BREAKDOWN

## 1. `apps/frontend`

Next.js 14 App Router with:

* `/app` → Routes (Home, products, cart, checkout, success, admin)
* `/store` → Zustand (cart, UI, admin state)
* `/service` → API calls to FastAPI
* `/types` → TS types (imported from `packages/shared-types`)
* `/components` → UI components with ShadCN
* `/config` → SEO, Cloudinary, API base URL

---

## 2. `apps/backend`

A clean FastAPI architecture:

```
backend/src/
├── api/        # Routers
├── core/       # Config, DB, email, auth
├── models/     # SQLAlchemy models
├── schemas/    # Pydantic
├── services/   # CRUD logic per entity
├── utils/
└── main.py
```

Matches your API spec:

* `/products`
* `/variants`
* `/orders`
* `/auth`
* Admin routes

---

## 3. `packages/` (shared libraries)

### `shared-types`

Both frontend & backend share the same data interfaces so no mismatch occurs.

Useful for:

* Product DTOs
* Order DTOs
* Variant DTOs
* Auth DTOs

### `shared-utils`

Reusable functions:

* price formatting
* slug generation
* validation
* regex utilities

### `shared-config`

Common config for:

* ESLint
* Prettier
* Tailwind base config
* TypeScript base config

---

## 4. `infra/`

Includes everything related to deployment, ops, and infra:

### `docker/`

* `docker-compose.yml` to run FastAPI + PostgreSQL locally
* Nginx reverse proxy if needed
* Dockerfiles for FastAPI

### `supabase/migrations`

Schema versioning:

```
001_init.sql
002_variants.sql
003_orders.sql
```

### `resend/`

Email templates:

* order-confirmation.html
* admin-notify.html

---

## 5. `.github/workflows/`

3 workflows:

* Deploy frontend → Vercel
* Deploy backend → Render/Railway
* Test → pytest + Next.js type check

---

## Services

```
services/
  ├── notification-service/     # For WhatsApp Cloud API
  ├── payment-service/          # JazzCash/EasyPaisa
```

---
