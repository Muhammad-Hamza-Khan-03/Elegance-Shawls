# Real-stack E2E: unresolved coverage gaps

Recorded separately from the suite description so they are not mistaken for covered behaviour. None of these is claimed by `e2e-real-stack`.

| Gap | Why it matters | Needed to close it |
|---|---|---|
| Editor-role authorization | Only viewer (denied writes) and owner exist in tests; the editor boundary (writes allowed, `accounts:manage`/`audit:read` denied) is unproven end to end | create an editor via `/v1/admin/accounts`; assert allowed and denied routes and the audit rows |
| Session expiry | Expiry/TTL (default 8h) is enforced server-side but never exercised | short-TTL setting or time control in a disposable backend; assert 401 and cookie clearing |
| Logout and revocation | `DELETE /api/admin/session` must revoke server-side; a reused token must fail | sign in, capture token, sign out, replay the token against the backend |
| Throttling / rate limits | Raised to 100000 for the run, so public/admin/login throttles are unexercised (the login throttle also locks the client for 15 minutes, so it needs its own isolated run) | dedicated spec with default limits against a separate backend port |
| Semantic ranking | No embedding model in CI; hybrid is proven only to degrade to lexical (`semantic:false`) | the evaluation framework in issues #138/#139, then a model-backed job |
| Production build and CSP | The suite uses `next dev`; production sets a strict CSP and security headers, and dev logs CSP `eval` warnings | run against `next build && next start` and assert response headers and a clean console |
| Redis behaviour | `REDIS_URL` is blank: shared rate limits, arq jobs and the WhatsApp stream are untested here | Redis service container plus worker readiness checks |
| LLM-backed assistant wording | `ASSISTANT_LLM=false` | fake-provider gateway run; real providers stay out of CI |
| Google sign-in, customer memory, WhatsApp bridge | out of scope for this suite | separate suites under their milestones |
| Concurrent/duplicate enquiries, mobile viewport, non-Chromium browsers | single desktop Chromium, sequential | add after the items above |
