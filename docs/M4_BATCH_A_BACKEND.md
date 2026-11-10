# M4 Batch A backend implementation notes

This branch implements the backend portion of `docs/m4-contract.md` against `origin/staging`. It does not activate customer login, complete independent QA, push staging, or set `release_ready=true`.

## Synthetic identity and local sessions

`tests/customer_auth_synthetic.py` holds deterministic Google and phone OTP adapters. OTP values and subjects are synthetic; no network call, real provider credential, or customer data is used. The existing production verifier remains configuration gated and disabled by default. The provider namespace and verified issuer and subject determine the identity binding; the stored subject is a SHA-256 digest of the issuer and subject pair. An issuer mismatch is refused before any identity write. Existing bare-subject rows from an earlier local fixture cannot be silently linked under the new binding; recreate disposable fixtures rather than inferring an issuer.

FastAPI continues to own opaque `cs1.` sessions and stores only a token hash. The optional `idempotency_key` on `POST /v1/customer/auth/exchange` (format `idem_` plus 16–64 safe characters) is bound to the issuer and subject. Repeating that key returns 409 without another session row; clients should retain the first response token. Without a key, a new exchange intentionally issues a new session. The existing expiry, customer status, per-session logout, logout-all, and session-cap behavior remains in force.

## Explicit anonymous event attribution

`POST /v1/customer/auth/merge-anonymous` is available only when `ENVIRONMENT=staging`, `CUSTOMER_AUTH_ENABLED=true` with complete auth settings, and `CUSTOMER_ANONYMOUS_MERGE_ENABLED=true`. It takes `{ "consent": true }`, a live `X-Customer-Session`, and a signed event token in `X-Anonymous-Session`. A raw anonymous ID, assistant `session_id`, or caller-supplied customer ID cannot select a source or destination. DNT/GPC requests, missing consent, invalid token, empty source, events older than 24 hours, more than 100 events, and any event already owned by a customer are refused. The operation changes `events.customer_id` only. It never imports memory or overwrites an explicit preference. An unowned event arriving after a successful merge stays separate and makes subsequent merge attempts fail with `source_changed`.

The merge ledger stores a digest of the anonymous session ID, customer ID, event count and time. A content-free audit row is written in the same transaction. Replays for the same customer return the original count and write no new event, ledger or audit row; another customer is refused. PostgreSQL advisory locking serializes competing merges of one source across workers. The browser should switch to a new anonymous event session after a merge.

Migration `0016` adds the ledger and nullable unique `customer_sessions.exchange_hash`; it does not rewrite existing customer data. Its downgrade refuses while merge ledger rows exist. Apply it only to a disposable local/staging test database under the normal migration approval process. No shared or production database was migrated for this branch.

## QA status

Container-free implementation tests are separate from independent QA. Real PostgreSQL integration tests in `tests/integration/test_anonymous_merge.py` cover idempotency, ownership, consent, freshness, issuer binding, phone fixture, audit and isolation. Independent staging QA, fixture cleanup and a recorded staging SHA remain required by the M4 contract before Batch B.
