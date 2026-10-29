# Local acceptance record — 2026-10-28

> **Historical record (pre-PostgreSQL).** Written when the catalogue ran on MongoDB; those parts no longer apply. Current setup: `DEPLOYMENT.md`.

**Candidate:** branch `p0/integration-local-qa` (PR #89), commit `0b4d6d8`. It merges #66 and #67 and adds #74, #75, #81, the #72 message fix, #69/#70/#76/#77 tooling and the SSR rate-limit fix.
**Environment:** local Docker stack equivalent to `compose.yaml` + `compose.local.yaml`; HTTPS through Caddy's local CA at `https://store.localhost:8443` and `https://api.localhost:8443`; authenticated MongoDB 8.0 on an internal network; fresh volumes; images built from `git archive 0b4d6d8`.
**Scope of this evidence:** local only. It is not staging or production evidence, no WhatsApp message was sent (`wa.me` was intercepted), and no production credentials or data were used. Secrets were generated per run and are not recorded.

| Image | ID |
|---|---|
| `elegance-backend:0b4d6d8` | `sha256:c32af62a44c2ce37583e1d036b8d964bb5ff13e60bd998b12904117508a6e6d9` |
| `elegance-frontend:0b4d6d8` | `sha256:bd603061cdb3aecd74037a8a645a37c7e174283853d917a81786447410a58c20` |
| `caddy:2.10.2-alpine` | `sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d` |
| `mongo:8.0` | `sha256:8e7d23aa641b0ec6c86418866d5d18d74d5abf89061bc5db7bc4b80929021ef6` |

## Repository checks (same commit)

- Frontend: `npm run lint`, `npm run typecheck` PASS; `npm test` 95/95 PASS; `npm audit --audit-level=high` 0 vulnerabilities; `npm run build` PASS; mocked `npm run test:e2e` 12/12 PASS.
- Backend (python:3.12-slim): `pytest -q` 31/31 PASS; `python -m compileall -q .` PASS; `pip-audit -r requirements.txt` no known vulnerabilities.

## Live-stack Playwright (`npm run test:e2e:live`), 06:14 UTC

Real Next.js, FastAPI and MongoDB with default public rate limits, no mocks; desktop Chrome and Pixel 7. 17/17 passed plus the throttle test (admin lifecycle runs on desktop only).

- **#71 admin lifecycle (built-in admin UI):**
  - Anonymous admin page redirects to login. The admin proxy returns 401 without a session; the backend returns 401 without a key or with a wrong key.
  - A wrong admin key is refused.
  - Created a draft with two variants: its stock status is derived from stock, it is not public, and the product page returns 404.
  - A cross-origin PATCH through the proxy returned 403 and the product stayed a draft.
  - Publish: product visible publicly with correct name, price, enabled and disabled options, and image.
  - Edit description and stock: variant IDs unchanged, and the storefront shows "1 available".
  - Unpublish → 404. Republish → 200. Archive → 404 and absent from the list.
  - Sign out → 401.
- **#72 customer ordering:**
  - Search finds the product. The out-of-stock option is disabled, and quantity is capped at stock.
  - The single-product WhatsApp message contains product, SKU, colour, size, quantity, unit price, total and the absolute product URL.
  - Multi-item cart message lists every line with SKU, options, unit and line totals, link, and the grand total.
  - The popup opens `https://wa.me/<number>`.
  - The empty cart shows guidance. On mobile, the sticky order button is visible.
- **#75 revalidation:**
  - Price raised and stock reduced on the backend after add-to-cart: the cart reports both, uses the backend price and quantity, and blocks handoff until acknowledged.
  - An unpublished line is removed. A sold-out line is removed, and the product page shows "Order unavailable".
  - A catalogue outage blocks handoff until "Check again" succeeds.
  - A verification older than 60 s re-checks instead of opening WhatsApp, on both the cart and the product page.
- **#67 sign-in throttle:** five wrong keys → 401, then the correct key → 429 with `Retry-After` and no cookie. A forged `X-Forwarded-For` is overwritten by the proxy and does not reset the throttle.

## Operations checks

- **#76 HTTPS and readiness:**
  - All four probes returned 200 over verified TLS.
  - With MongoDB stopped, backend `/ready/` and frontend `/api/ready` returned 503 in 2.01 s, and both recovered after restart.
  - Security headers (HSTS, CSP, X-Frame-Options) were present, and `X-Request-ID` propagated from Caddy to the backend log.
  - Found and fixed in this run: in container builds, `/api/ready` always returned 503 because it read `NEXT_PUBLIC_*` dynamically.
- **#69 MongoDB:**
  - No host port; unreachable from the frontend container; no internet egress; unauthenticated reads denied.
  - The app user can read its own database, and is denied access to `admin.system.users`, writes to other databases, and dropping the admin database.
- **#70 backup and restore drill:**
  - The encrypted backup (`Salted__` OpenSSL header) recorded 34 products and 51 variants.
  - The isolated restore into a container with no network reconciled 34/51, taking 1 s. Result: pass.
  - A wrong passphrase fails. Failures produce exactly one webhook alert, and retention removes only `elegance-*` files older than the limit.
- **#77 monitoring and rollback:**
  - Induced MongoDB outage: the watchdog alerted for the unhealthy container, both readiness probes (after 3 consecutive failures) and the 5xx spike, then sent recovery messages after restart.
  - A backend crash/restart raised a restart alert.
  - Rollback `0b4d6d8 → 8ce2858 → 0b4d6d8` took 13 s each way, with all probes 200 and product count unchanged (34).
  - Container logs contained 0 occurrences of the admin key, internal API token, MongoDB passwords, session cookie or WhatsApp message text. An earlier run found the new internal token in Caddy logs; it is now redacted (`0b4d6d8`).

## Findings and limits

- **SSR rate limiting (found and fixed here):** every server-rendered request reached the backend from the storefront server's address, so all page views shared one public bucket. With the default 120/min limit, 150 parallel product page views on `5dffea1` returned 30 × 404 for a real product: the backend answered 429 and the storefront treated it as not found. The storefront server now sends a server-only `X-Internal-API-Token`. On `0b4d6d8` the same load returned 150 × 200 with no 429s. On Render, browser requests are still keyed by whatever address uvicorn sees; see `DEPLOYMENT.md` before changing `FORWARDED_ALLOW_IPS`.
- **Compose:** only Compose v1 was available locally, and it is incompatible with Docker 29. `docker-compose config` validated the files, and a scripted `docker run` equivalent of the same services, networks, aliases, volumes and environment ran the stack. `deploy/rollback.sh` uses `docker compose` and was exercised through that equivalent rather than directly.
- **Not covered here:** Vercel/Render/Atlas production configuration, public DNS and certificates, delivery of a real WhatsApp message, off-host backup upload, and owner approval of policy content (#78).
