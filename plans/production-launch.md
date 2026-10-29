# Elegance Shawls Production Launch Plan

## Current architecture

- `Elegance-Shawls` is the customer storefront.
- `quill-panel` is the admin/product upload panel.
- Products are uploaded from Quill Panel and consumed by the storefront through `NEXT_PUBLIC_API_URL`.
- Customer orders are intentionally handled through WhatsApp, not an orders database or payment gateway.

## Production-ready launch definition

The site is launch-ready when a customer can:

1. Open the storefront homepage.
2. Browse active products.
3. Open a product detail page.
4. See correct images, price, description, material, size and color options.
5. Click `Order on WhatsApp`.
6. Send a pre-filled WhatsApp order message to the business number.

The admin can:

1. Log in to Quill Panel.
2. Add products with images, price, category and variations.
3. Publish/unpublish products.
4. Preview the product on the storefront.

## Done in the storefront

- Replaced default Next.js homepage.
- Added storefront metadata.
- Added `/products` listing page.
- Added `/product/[slug]` product detail page.
- Added WhatsApp order helper.
- Added `NEXT_PUBLIC_WHATSAPP_NUMBER` env example.
- Normalized product mapping to support Quill payload shape:
  - `price.amount`
  - `price.currency`
  - `category.name`
  - `variations`
  - `description`
  - `material`
  - `sizing`
  - `weight`
  - `item_number`
- Added backend CORS support.
- Added env examples.
- Pinned backend dependencies.

## Remaining P0 checks before launch

### 1. Configure production env vars

Frontend:

```env
NEXT_PUBLIC_API_URL=https://your-api-domain.com
NEXT_PUBLIC_WHATSAPP_NUMBER=923xxxxxxxxx
```

Backend/API:

```env
MONGODB_URI=...
MONGO_DB_NAME=...
ALLOWED_ORIGINS=https://your-storefront-domain.com,https://your-quill-panel-domain.com
```

Quill Panel:

```env
NEXT_PUBLIC_API_URL=https://your-api-domain.com
NEXT_PUBLIC_STOREFRONT_URL=https://your-storefront-domain.com
```

### 2. Validate API compatibility

The storefront expects public products to be readable from:

```text
GET /products/
GET /products/slug/:slug
```

The response can be either:

```json
[
  { "name": "...", "price": { "amount": 1000, "currency": "PKR" }, "variations": [] }
]
```

or:

```json
{ "items": [ ... ] }
```

### 3. Validate WhatsApp order link

Open a product and click `Order on WhatsApp`. Confirm:

- Correct business number opens.
- Product name appears.
- Item/SKU appears.
- Price and total are correct.
- Product link is included.

### 4. Validate Quill to storefront flow

- Add a product in Quill Panel.
- Publish as `active`.
- Confirm it appears on `/products`.
- Confirm image loads.
- Confirm `/product/[slug]` opens.
- Confirm draft/archived products do not appear.

## Remaining P1 hardening

- Replace client-exposed admin key with server-issued session/auth if the backend supports it.
- Add CI build checks for storefront and Quill Panel.
- Add domain-level CORS restrictions only; no wildcard CORS in production.
- Add product image optimization or trusted image domains when switching from plain `img` to Next Image.
- Add analytics after launch.
- Add basic privacy/returns/shipping pages.

## Manual QA checklist

### Desktop

- Homepage loads.
- Products page loads.
- Product cards show image, title, category and price.
- Product detail page loads.
- WhatsApp CTA works.
- Empty product state is readable.

### Mobile

- Homepage is readable.
- Product grid becomes one column.
- Product image is not cropped badly.
- WhatsApp CTA is easy to tap.
- Text is not overflowing.

### Admin

- Quill Panel login works.
- Product upload works.
- Image upload works.
- Product status toggle works.
- Storefront preview link opens correct product.

## Launch decision

This project can launch as a WhatsApp-order storefront after the P0 checks pass. It should not be treated as a payment/order-management ecommerce platform until orders, inventory reservation and payment workflows are added.
