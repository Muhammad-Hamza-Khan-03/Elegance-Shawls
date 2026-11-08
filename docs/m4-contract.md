# M4 contract expansion: staged returning-customer experience

**Contract ID:** `t_aba73777` (expanded in place; do not create a second M4 contract)
**Status:** `staging evidence recorded; activation deferred`, `release_ready=false`

## Verified milestone state — 2026-11-08

The provider-training policy gate and migration downgrade fixture are present in the staging tree. This is staging/integration evidence only; it is not deployment, provider activation, production readiness, or M4 completion.

| Evidence | Exact reference | Interpretation |
|---|---|---|
| Current integration tree | `origin/staging-integration` = `4675052b7b983c24b46b2d39fa18e4f1a8815124` (PR #191) | Documentation and evidence are based on the current staging-integration tip. |
| Provider policy | PR #179 merged as `e04fb7470fb921032086f8c99217247458efec1d` | Eight-control, use-case-scoped training-provider policy is in the integration tree; no provider is selected or activated. |
| Provider policy promotion | PR #184 merged to staging as `3b4f7b10d953a5e30cde50a7b2c714f59f43bc8d` | The policy tree was promoted to staging without production/main changes. |
| Migration downgrade fixture | PR #185 merged as `5a6ed21a5665d254ac345749811efa9dc63a8722` | Synthetic memory rows are isolated before the intentional downgrade guard is exercised. |
| Migration fixture promotion | PR #186 merged to staging as `d020d521f2666726a2b82316785c8bf72669e83a` | `origin/staging` is the staging release candidate; `origin/main` remains `283b27eee90533435ef3b2e28e6a3823ee1c5d23`. |

### Verification boundaries

- Independent M4 QA: `119 passed, 29 deselected`.
- Migration promotion QA: `23 passed, 2 warnings`; targeted migration suites: `70 passed`.
- Local disposable Redis `elegance-local-staging-redis-1` was healthy at `127.0.0.1:6380`. The local backend readiness probe at `127.0.0.1:18000` reported database/PostgreSQL, Redis, and worker connected.
- The arq synthetic job completed `queued → deferred → queued → complete` on attempt 2.
- Groq smoke was bounded synthetic-only: two calls, no customer data, no credentials or API-key values recorded, and no activation.
- **EmbeddingGemma 2 local candidate:** `google/embeddinggemma-2`, Hugging Face revision `f9972ac22e696a105c482202646979e33e4b5a1e`, tree SHA-256 `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b`, weights SHA-256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`, 768 dimensions, CPU-only. Quality: recall `0.9973`, MRR `0.9706`, synonym recall/MRR `1.0`, hard constraints `0`, reproducibility Jaccard `1.0`. QA: Gemma/contract `35 passed, 1 skipped`; eval `14 passed`; embedding integration `21 passed`; schema integration `6 passed`; compileall/diff-check passed; backfill `8/8`, idempotent rerun, and retrieval passed. This verifies local search candidate behavior only.

The evidence above does not claim deployment, production activation, provider selection/credentialing, live customer data, external observability, or `release_ready=true`. EmbeddingGemma activation remains local-only pending hosted staging acceptance, external OTLP/Langfuse, reviewed model/evaluation provenance, and production activation/deployment.
**Baseline preserved:** M3 canonical action contracts and M4 Batch 1 commit `1823d47a071c713b6ca00348364260a93c8a584f` / task `t_2f755ea0`
**Scope:** bounded staging-only batches; synthetic identities, provider mocks, and synthetic catalogue/events only

This document is the idempotent M4 contract record. Re-applying this change updates the same task IDs and batch gates; it must not create duplicate tasks, enable production memory, close issues, or change `release_ready`.

## Non-negotiable boundaries

- No `main`, production, VPS, deployment, provider credential, live customer data, production database, or real identity-provider exchange.
- Supabase, if later selected, is identity-only; PostgreSQL remains the sole application database and FastAPI owns local session issuance, lookup, expiry, and revocation.
- Anonymous IDs, assistant `session_id`, external identity subjects, and local customer IDs are distinct. Client input never selects the customer principal.
- Customer memory extraction remains disabled. The existing explicit `MemoryProvider` and consent/tombstone contract is preserved.
- No issue is closed by this contract. No phase may set `release_ready=true`.

## Sequential batches and exact task IDs

The batches are strictly ordered. A later batch cannot start until the prior batch's implementation tests and independent QA evidence are recorded against its acceptance criteria.

### Batch A — staging-only customer identity/login and conservative anonymous merge

**Parent task:** `t_m4a_customer_identity_login_merge`

**Specialist implementation tasks:**

- `t_m4a_identity_provider_mock`: synthetic Google/phone-OTP provider adapters and deterministic fixtures only; no real credentials or network exchange.
- `t_m4a_fastapi_sessions`: FastAPI-owned opaque sessions, hash-only persistence, expiry, per-session logout, logout-all, revocation, and fail-closed principal resolution.
- `t_m4a_conservative_merge`: merge only server-resolved anonymous state into the authenticated customer when ownership, freshness, consent, and conflict rules pass; ambiguous/conflicting records remain separate and are auditable.
- `t_m4a_canonical_tests`: canonical backend/frontend tests for login, session lifecycle, isolation, replay/idempotency, and merge refusal cases.
- `t_m4a_independent_qa`: independent QA using synthetic accounts and a staging test database; implementation authors do not self-approve.
- `t_m4a_push_staging`: after QA PASS, push the exact QA-passed SHA to `origin/staging` and record the SHA; never promote to `main`.

**Acceptance criteria:**

1. With the feature flag/configuration off or incomplete, login is unavailable or fails closed; no provider call and no database identity decision is made on the disabled path.
2. Mock provider identities are mapped by verified `(issuer, subject)` only. Tokens, provider credentials, and secrets never enter Git, logs, browser responses, or chat.
3. FastAPI creates an opaque local session; PostgreSQL stores only a token digest plus customer, expiry, and revocation state. Every request rechecks expiry, revocation, and customer status.
4. Logout revokes exactly one session; logout-all revokes all sessions for that customer. Invalid, expired, revoked, mismatched, oversized, and verifier-error sessions produce the same unauthenticated response class.
5. Anonymous merge is server-side, one-way, conservative, idempotent, and auditable. It never overwrites explicit authenticated preferences with anonymous values; conflicts are retained separately or refused.
6. Repeating the same synthetic exchange/merge fixture produces no duplicate customer, identity, session, memory, or audit rows.
7. Independent QA proves customer isolation, revocation, merge refusal, cleanup of synthetic fixtures, and no live provider/database access.

**Batch A gate:** `QA_PASS` plus recorded staging SHA. Without both, Batch B is blocked.

### Batch B — explainable recommendation read path

**Parent task:** `t_m4b_explainable_recommendation_read_path`

**Specialist implementation tasks:**

- `t_m4b_preference_projection`: read explicit preferences and permitted session constraints only; define deterministic conflict/absence behavior.
- `t_m4b_reasoned_ranker`: feature-flagged, read-only recommendation projection with hard catalogue constraints and machine-readable reason codes.
- `t_m4b_impression_logging`: idempotent impression/event records containing recommendation ID, product/variant, position, feature flag, experiment arm, preference snapshot/version, catalogue revision, and timestamp.
- `t_m4b_canonical_tests`: canonical tests for explainability, constraints, deterministic fallback, duplicate-safe impressions, and disabled-flag behavior.
- `t_m4b_independent_qa`: independent QA on synthetic preferences, catalogue, impressions, and randomized control/treatment fixtures only.
- `t_m4b_push_staging`: after QA PASS, push the exact QA-passed SHA to `origin/staging` and record the SHA.

**Acceptance criteria:**

1. The read path is disabled by default and can run only in staging/synthetic mode behind an explicit feature flag.
2. Recommendations use explicit preferences and allowed session constraints; no inferred sensitive attributes and no production customer memory are read.
3. Every returned recommendation has a stable reason code and human-readable explanation grounded in the preference/constraint snapshot and catalogue revision used.
4. Hard catalogue constraints are enforced in application code; unavailable, unpublished, or non-matching variants are never recommended.
5. Impressions are append-only, idempotent for the same request/arm/position key, and record enough provenance to answer why a customer saw an item. Control/treatment assignment is deterministic for a synthetic subject and does not alter catalogue truth.
6. If the flag is off or the read path errors, the system falls back to normal catalogue browsing/search without writing memory or mutating customer state.
7. Independent QA verifies reason fidelity, no silent constraint relaxation, duplicate-safe logging, isolation, and that no live customer/provider data is touched.

**Batch B gate:** `QA_PASS` plus recorded staging SHA. Without both, Batch C is blocked.

### Batch C — privacy-gated production-memory readiness (blocked until approvals)

**Parent task:** `t_m4c_production_memory_privacy_gate`

**Specialist tasks:**

- `t_m4c_provider_decision`: record the approved `m4c-provider-training-policy-relaxation/v1` gate; no provider selection or activation.
- `t_m4c_memory_extraction_evals`: build and run reviewed synthetic memory extraction evals covering save, do-not-save, correction, relevance, sensitive-data refusal, consent, and forgetting; record reproducible results.
- `t_m4c_tombstone_queue_proof`: prove delete/disable tombstones and `memory_version` prevent queued jobs and retries from recreating deleted memory; include replay, retry, and worker-restart cases.
- `t_m4c_promotion_packet`: assemble model/provider evidence, eval report, deletion proof, threat/privacy review, rollback plan, and explicit owner approvals. This task cannot enable memory by itself.
- `t_m4c_independent_qa`: independent QA of the complete gate packet against synthetic data only.
- `t_m4c_push_staging`: only after QA PASS, push the QA-passed gate/evidence changes to `origin/staging`; this does not enable production memory.

**Acceptance criteria:**

1. Production-memory extraction remains disabled until the complete use-case control record is present and independently verified for the exact selected model/provider. Training-enabled providers are permitted by policy but no provider is selected here; free-tier or unverified providers are rejected.
2. Verification includes explicit disclosure/consent where applicable, retention/deletion behavior, region/subprocessor/security review, data classification/minimization, opt-out/deletion behavior, audit evidence, rollback/disable controls, and a tested fail-closed configuration. No credential is committed or shared in chat.
3. Memory extraction evals are non-empty, reproducible, human-reviewed, and pass agreed thresholds for save/do-not-save, correction, relevance, sensitive-data refusal, consent, and forgetting. Missing or `NOT_EVALUATED` evidence blocks the gate.
4. Delete, disable, tombstone, version, retry, replay, and worker-restart tests prove queued jobs cannot recreate deleted or disabled memory.
5. View/correct/delete/turn-off, audit, ownership isolation, retention, and rollback evidence is complete for the explicit `MemoryProvider` contract.
6. Independent QA signs the packet, and named product, privacy/security, and engineering owners explicitly approve promotion. QA alone cannot promote or set `release_ready=true`.

**Current state:** `BLOCKED_PROVIDER_PRIVACY_DECISION` — no paid no-training/self-hosted model has been selected and verified in the supplied context, and no memory extraction eval or queued-job deletion proof is available. Do not guess a provider, enable extraction, or treat Batch C as complete.

## Current next action

Batch A and Batch B gates are satisfied on the recorded staging SHAs. Batch C remains **privacy-readiness only**: the policy and migration fixture are in staging, but provider activation and production-memory promotion are deferred. Continue the idempotent task records `t_m4c_provider_decision`, `t_m4c_memory_extraction_evals`, `t_m4c_tombstone_queue_proof`, `t_m4c_promotion_packet`, `t_m4c_independent_qa`, and `t_m4c_push_staging` with synthetic/local proof only; production memory remains disabled and `release_ready` remains false.

### Remaining blockers

- Frontend live proxy verification needs a disposable backend URL.
- Embeddings activation/backfill is unavailable; the local embedding path is not an activation or backfill proof.
- Evaluation provenance is incomplete; fixture/deterministic evidence is not model-backed release evidence.
- External observability has not been exercised.
- Deployment, production activation, provider selection/credentialing, and any `release_ready` transition remain separately deferred.

## Approvals required

- **Batch A:** engineering owner approves scope; independent QA approves synthetic login/session/merge evidence; staging owner approves push to `origin/staging`.
- **Batch B:** product/engineering owner approves reason vocabulary and experiment flag; independent QA approves explainability/impression evidence; staging owner approves push to `origin/staging`.
- **Batch C:** provider/privacy decision owner approves the paid no-training/self-hosted model and terms; privacy/security approves data handling; engineering approves extraction/tombstone implementation; independent QA approves eval and queued-job proof; product owner explicitly approves any later promotion. No approval is implied by this document.

## Explicit non-claims

This contract does not claim that customer login is enabled, that recommendations are active, that a provider is selected, that production memory is available, that any deployment occurred, or that any customer data was accessed. It records work order and gates only.
