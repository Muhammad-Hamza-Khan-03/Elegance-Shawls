# M4 customer-auth closeout packet (local-only)

**Status:** documentation/configuration contract only. This packet does not provision an identity provider, change deployment settings, migrate a hosted database, or enable customer sign-in.

## Reviewed implementation boundaries

- Backend worktree: `/home/hamza/worktrees/m4-customer-auth-foundation`
  - reviewed `0626507dc8eef74cc3d55abf6bcc57eed31d340f`
  - customer identity verification: `apps/backend/security/customer_identity.py`
  - readiness/session wiring: `apps/backend/security/customer_session.py`
  - exchange/logout routes: `apps/backend/routes/customer_auth_routes.py`
  - principal contract: `apps/backend/memory/principal.py`
  - session persistence: `apps/backend/repositories/customer_auth.py`, migration `0012_customer_sessions`
  - configuration source: `apps/backend/configuration/config.py`
- Frontend worktree: `/home/hamza/worktrees/m4-customer-auth-frontend`
  - reviewed `edbf4a30d660e4a5c429de19a1d1b7a629157f71`
  - browser session boundary: `apps/frontend/src/app/api/customer/session/route.ts`, `apps/frontend/src/lib/customer-session.ts`
  - frontend route tests: `apps/frontend/src/app/api/customer/session/route.test.ts`

The frontend and backend SHAs are separate implementation evidence. This closeout commit is based on the backend SHA and records the frontend SHA; it does not merge or alter either implementation worktree.

## Contract

### Provider-neutral customer identity

The backend accepts an external OIDC-style RS256 identity token only after strict verification of the configured issuer, audience, expiry/not-before/issued-at, subject, algorithm, signing key and bounded JWKS cache. The verified `(issuer, subject)` pair is mapped server-side to the local customer record. Request bodies and headers never select a customer identity.

The provider setting is an application identity-provider label, not a database or session-store selector. The current implementation accepts only the provider values declared by `IDENTITY_PROVIDERS` other than `anon` (currently `google` and `phone` in the reviewed tree). Do not add a new provider label or claim a provider is supported without a separately reviewed implementation and contract update.

### Exact backend configuration keys

Customer auth is disabled by default. The following keys are the exact environment names corresponding to the backend settings:

| Key | Required contract |
|---|---|
| `CUSTOMER_AUTH_ENABLED` | Must be explicitly true to enable the verifier. Default false. |
| `CUSTOMER_AUTH_PROVIDER` | Must be a supported non-anonymous identity-provider label. |
| `CUSTOMER_AUTH_ISSUER` | Must exactly match the verified token issuer. |
| `CUSTOMER_AUTH_AUDIENCE` | Must match the token audience. |
| `CUSTOMER_AUTH_JWKS_URL` | Must be an HTTPS URL; redirects are not followed. |
| `CUSTOMER_AUTH_JWKS_TTL_SECONDS` | Must be greater than zero. |
| `CUSTOMER_AUTH_JWKS_MIN_REFRESH_SECONDS` | Must be greater than zero. |
| `CUSTOMER_SESSION_TTL_SECONDS` | Must be greater than zero; current default is seven days. |
| `CUSTOMER_SESSION_MAX_ACTIVE` | Must be greater than zero; current default is five sessions per customer. |
| `CUSTOMER_AUTH_RATE_LIMIT_PER_MINUTE` | Separate customer-auth rate-limit bucket; current default is 10. |
| `DATABASE_URL` | Required PostgreSQL URL. The backend and customer-session repository use this sole application database. |

No example value in this packet is a provider credential, issuer, audience, JWKS URL, or deployment secret.

### Fail-closed defaults

- With `CUSTOMER_AUTH_ENABLED` false, incomplete, unsafe, or unsupported configuration, identity/session verifiers are absent.
- In that state, exchange returns 404 and customer-authenticated routes return 401 without touching PostgreSQL for the disabled exchange path.
- Invalid, expired, revoked, inactive, unknown, mismatched, malformed, or verifier-error sessions resolve to the same 401 class.
- JWKS outage is a temporary 503, not a successful identity decision.
- The frontend refuses cross-origin exchange/sign-out, requires JSON for exchange, never relays upstream error detail, and does not set a cookie for malformed or refused responses.

### Opaque session and revocation semantics

`POST /v1/customer/auth/exchange` exchanges a verified external identity for a locally generated opaque session token. The token is a lookup handle, not a customer identity assertion. PostgreSQL stores only its SHA-256 digest in `customer_sessions`; it does not store the bearer token or an identity-provider credential.

The server resolves `X-Customer-Session` to a live session and derives the customer from that row. Every use checks expiry, revocation and customer status. `POST /v1/customer/auth/logout` revokes only the presented session; `POST /v1/customer/auth/logout-all` revokes all sessions for that customer. The frontend keeps the opaque token only in the HttpOnly `cs_customer_session` cookie and clears that cookie on sign-out, including when the backend is unavailable. The browser response never returns either the external identity token or local session token.

### Supabase identity-only boundary

If Supabase is selected as the future external identity provider, its role is identity verification/JWKS only. Supabase is not the Elegance application database, customer-session store, authorization source, or catalogue source. The application continues to resolve customer identity and revocation through its own PostgreSQL-backed tables and server-side verifier. No Supabase project, key, URL, database, or deployment value is asserted or configured by this packet.

### Database boundary

Render PostgreSQL is the sole application database for customer records, identities, catalogue data and customer sessions. Supabase must not be introduced as a second application database or persistence path. Redis remains optional infrastructure for shared rate limiting/AI workloads; it is not the source of customer identity or session revocation.

### Future isolated staging prerequisites

Future staging work is a separate, approval-gated task and remains blocked until all of these are available and verified without reusing production values:

1. An isolated Render backend service and an isolated Render PostgreSQL database, with a reviewed branch/SHA and explicit service-to-database association.
2. The staging database schema applied by an operator-approved Alembic migration; no production database reuse and no customer-data copy.
3. A staging-only identity-provider configuration with verified issuer, audience and HTTPS JWKS endpoint, plus provider-side authorization to use it. If Supabase is chosen, it must be a staging identity project/configuration, not the production project or application database.
4. The exact backend key set above, stored in the staging secret store. Never place secrets in Git, frontend `NEXT_PUBLIC_*` variables, logs, screenshots or chat.
5. A separately reviewed frontend origin and backend `ALLOWED_ORIGINS` value, plus the existing same-origin proxy/cookie boundary. The frontend needs only its public `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_WHATSAPP_NUMBER`; customer provider secrets do not belong in the browser.
6. Non-production test identities and disposable fixtures, with an explicit cleanup plan. No live customer data, production sessions, production tokens or production database connection strings.
7. Non-destructive verification of liveness/readiness, exchange refusal when configuration is incomplete, successful local session exchange only with approved staging identity material, per-session logout, logout-all, expiry/revocation and customer isolation.

Until these prerequisites are met, the local implementation is code/test evidence only; it is not staging, deployment, provider-compatibility, or customer-data acceptance evidence.

## Explicit non-claims

This packet does not claim that customer authentication is enabled anywhere, that a Supabase project exists, that Render services or databases exist, that any provider keys are valid, or that staging/production has been deployed or migrated. No provider, deployment, merge, push, canonical checkout, or customer data was changed.
