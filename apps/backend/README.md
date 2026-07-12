# Elegance Shawls product API

Public storefront reads use `GET /products/` and `GET /products/slug/{slug}`.
List responses use `{ "items": [...], "next_cursor": "..." }`; pass the cursor
back with `?cursor=...&limit=20`. Only active products are publicly visible.

Administrative operations live under `/products/admin` and require the
`X-Admin-Key` header:

- `POST /products/admin/` — create
- `GET /products/admin/` and `GET /products/admin/{id}` — inspect all lifecycle states
- `PUT /products/admin/{id}` — replace editable product data
- `PATCH /products/admin/{id}/status` — publish, draft, mark out of stock, or archive
- `PATCH /products/admin/{id}/stock` — set a variant's stock count
- `DELETE /products/admin/{id}` — soft-delete by archiving

Configure the same long random `ADMIN_API_KEY` in the API and trusted Quill
server. Never put this secret in a `NEXT_PUBLIC_` variable or browser bundle.
Production deployments should also enforce rate limits at the edge; the API's
in-process limiter protects a single application instance.

`GET /health/` is a liveness probe. `GET /ready/` verifies MongoDB connectivity.
Startup verifies MongoDB and creates the unique slug and feed indexes.

Run contract and security tests with `pip install -r requirements-dev.txt`
followed by `pytest`.
