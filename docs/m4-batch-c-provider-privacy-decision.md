# M4 Batch C provider decision record (idempotent, privacy gate only)

**Purpose and audience.** Privacy/security decision record for the owner and independent QA reviewer. It compares future memory-extraction options without selecting, purchasing, credentialing, or activating one.

**Task ID:** `t_m4c_provider_decision`
**Parent:** `t_m4c_production_memory_privacy_gate`
**Idempotency key:** `m4c-production-memory-privacy-gate/provider-decision/v1`
**Policy change key:** `m4c-provider-training-policy-relaxation/v1`
**Packet revision:** `2026-11-08-staging-integration-provider-controls`
**Decision state:** `BLOCKED_PROVIDER_PRIVACY_DECISION`
**Selection:** none. No provider has been selected, purchased, credentialed, called, or activated.

Re-applying this record updates this same task and idempotency key. It must not create a second provider-decision task, alter `release_ready`, enable production memory, send a provider request, or incur spend.

## Scope and hard boundaries

This is a production-memory privacy decision gate, not a provider rollout. Training-enabled (`may_train`) providers are now eligible for assistant, customer-memory, and extraction paths only when the complete use-case control record below is present and independently verified. No-training and self-hosted providers retain their existing eligibility; unknown, opt-out, missing, conflicting, free-tier, or unverified records deny.

The change does not select or purchase a provider. Customer memory extraction remains disabled by default (`MEMORY_EXTRACTION_ENABLED=false`); PostgreSQL remains the sole application database. No real customer data, credentials, live provider calls, production/VPS/main changes, deployment, spend, issue closure, or `release_ready=true` is allowed by this record.

## Current staging evidence — 2026-11-08

The policy record is present in the current staging lineage: PR #179 merged to `staging-integration` as `e04fb7470fb921032086f8c99217247458efec1d`, and PR #184 promoted that policy tree to staging as `3b4f7b10d953a5e30cde50a7b2c714f59f43bc8d`. The current `origin/staging-integration` tip for this pass is `63f1730663114d31085967ae01a05687bd614979` (PR #194); the migration fixture was merged by PR #185 at `5a6ed21a5665d254ac345749811efa9dc63a8722` and the current `origin/staging` is `e5c04c8d4097a46adf9fecf00baddd15cc860fc2`. `origin/main` remains `283b27eee90533435ef3b2e28e6a3823ee1c5d23`.

Independent evidence recorded for this staging-only milestone includes M4 QA (`119 passed, 29 deselected`), migration promotion QA (`23 passed, 2 warnings`), and targeted migration suites (`70 passed`). Local disposable Redis was healthy at `127.0.0.1:6380`; backend readiness at `127.0.0.1:18000` reported database/PostgreSQL, Redis, and worker connected; and the synthetic arq job completed `queued → deferred → queued → complete` on attempt 2. A bounded Groq synthetic smoke made two calls only. No API key, credential, customer data, deployment, or provider activation is claimed.

The separate M2 search candidate is verified on the current integration lineage: `google/embeddinggemma-2`, Hugging Face revision `f9972ac22e696a105c482202646979e33e4b5a1e`, tree SHA-256 `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b`, weights SHA-256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`, 768 dimensions, CPU/local-only. Quality was recall `0.9973`, MRR `0.9706`, synonym recall/MRR `1.0`, zero hard-constraint violations, and reproducibility Jaccard `1.0`; QA was Gemma/contract `35 passed, 1 skipped`, eval `14 passed`, embedding integration `21 passed`, schema integration `6 passed`, compileall/diff-check passed, and disposable backfill `8/8` with idempotent rerun/retrieval pass. This candidate evidence is not provider/privacy approval or hosted activation.

Remaining blockers are the disposable backend URL needed for frontend live-proxy verification, hosted staging acceptance, external OTLP/Langfuse, reviewed evaluation/model provenance, deployment/production activation, and `release_ready=false`.

## Current implementation boundary (verified against origin/staging)

- `MemoryProvider` is a provider-neutral PostgreSQL CRUD/consent contract; it does not install or call an extraction model (`apps/backend/memory/provider.py`).
- The current PostgreSQL provider receives only a server-verified customer principal and returns a public item shape without owner/fingerprint fields; it is not evidence that a model provider has been approved.
- `memory/queue_guard.py` is a fail-closed pre-write guard. It rejects disabled extraction, mismatched `memory_version`, pre-tombstone source time, and future-dated work.
- M2 local EmbeddingGemma2 candidate `google/embeddinggemma-2` is pinned to Hugging Face revision `f9972ac22e696a105c482202646979e33e4b5a1e`, tree SHA-256 `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b`, and weights SHA-256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`; it is 768-dimensional CPU/local-only search evidence. It is **not** a memory-extraction model or provider/privacy approval.
- The M4 synthetic runner is a deterministic rule/fixture contract check. It makes no provider calls and no database writes; it is not a model-quality or production approval.

## Training-enabled provider control record

For each exact provider/account/endpoint/model and each applicable use case (`assistant`, `memory`, `extraction`), `LLM_PROVIDER_CONTROL_RECORDS` must contain exactly these eight boolean fields, all `true`: `disclosure_consent`, `retention_deletion`, `residency_security`, `provider_terms`, `data_classification`, `opt_out_deletion`, `audit_evidence`, and `rollback_disable`. The record is a declaration of independently verified evidence, not a provider selection. Missing, extra, malformed, conflicting, or stale fields fail closed; free-tier providers remain denied even with a record. Consent remains a literal prerequisite for customer-memory use, and extraction remains off until separately activated.

The deterministic gate is use-case scoped and tests all fallback-chain members. This preserves the default-off, unknown-deny behavior while allowing a training-enabled provider only after disclosure/consent where applicable, retention/deletion/residency/security, exact provider terms, classification/minimization, opt-out/deletion, audit evidence, and rollback/disable controls are recorded.


| Criterion | Paid no-training API | Self-hosted/local model |
|---|---|---|
| Training/data-use boundary | Must attach the exact commercial/API terms plus account/endpoint eligibility proving no training or model improvement for submitted memory content. “Default” language is not enough without account-level verification. | No third-party prompt recipient when runtime is offline and outbound sockets are blocked. Must still review model license, weight provenance, telemetry, host operators, and supply-chain risk. |
| Retention/deletion | Must obtain exact request/log/abuse-monitoring retention, deletion SLA, backup deletion, legal-hold, and account termination behavior; prove the configured retention setting and deletion request path. | Define local request, cache, application log, worker queue, backup/snapshot, and crash-dump retention. Prove deletion from each applicable store and document backup expiry/crypto-erasure behavior. |
| Residency/subprocessors | Must name processing regions, subprocessors, transfer mechanism, support access, incident notice, and customer-controlled region/endpoint. Verify the exact purchased service, not a generic provider page. | Choose the host/region and operators; document ingress/egress, disks/backups, admin access, patching, key management, isolation, and incident response. No network egress is required for inference. |
| Operational burden | Lower model operations burden; recurring usage cost and provider-policy/availability dependency. Budget, rate limits, abuse controls, and provider outage behavior require approval. | Higher responsibility for capacity, patching, model integrity, observability, deletion, failover, and rollback; avoids per-request provider spend but may require infrastructure spend. |
| Extraction/model separation | Contract and runtime configuration must prove the approved extraction model is distinct from search embeddings and cannot silently fall back to a non-cleared model. | Pin a separate extraction artifact and runtime; outbound network must be blocked; search model and extraction model use separate config names, caches, eval reports, and rollback switches. |
| Current status | **Candidate only; not selected.** No account, contract, setting, credential, or spend approved. | **Candidate only; not selected.** No snapshot/license/digest has been approved for memory extraction. |

### Evidence references (pointers, not approvals)

- OpenAI API data-use/privacy overview: <https://openai.com/enterprise-privacy/> and <https://platform.openai.com/docs/models/how-we-use-your-data>.
- Anthropic commercial/legal materials: <https://www.anthropic.com/legal> and <https://www.anthropic.com/legal/supported-regions>.
- Transformers local/offline operation: <https://huggingface.co/docs/transformers/>.

Provider terms and settings can change. The named owner must re-check the exact account/contract or model artifact immediately before any activation. No web reference alone clears this gate.

## Verifiable decision criteria

A future candidate is `CLEARED_FOR_REVIEW` only when every applicable item below has a dated artifact, owner, and reproducible verification. Until then the status is `BLOCKED_PROVIDER_PRIVACY_DECISION`.

| ID | Criterion | Required proof | Current evidence/status |
|---|---|---|---|
| PD-01 | No-training or self-hosted isolation | Signed/dated exact contract and account setting, or pinned local model snapshot/license plus offline socket-blocked runtime proof | **BLOCKED** — no candidate selected |
| PD-02 | Retention/deletion | Retention schedule for prompts, outputs, logs, queue, caches, backups; deletion/tombstone procedure and observed proof; legal-hold/incident exceptions | **PARTIAL** — application memory retention/tombstone controls exist; provider/model retention is unverified |
| PD-03 | Residency/security | Processing region, subprocessors/operators, access roles, encryption, key ownership, network controls, incident notice, audit/log policy | **BLOCKED** — exact boundary not selected/reviewed |
| PD-04 | Extraction model separation | Distinct extraction model/config/cache/eval artifact; explicit prohibition on using M2 search embeddings as extraction evidence; no-cleared-model fail-closed test | **PASS for boundary, not model approval** — code has provider gate; no extraction model selected |
| PD-05 | Eval evidence | Non-empty synthetic, reproducible, human-reviewed model-backed eval covering save, do-not-save, correction, relevance, sensitive refusal, consent, and forgetting; agreed thresholds | **NOT EVALUATED for model quality** — deterministic fixture is 12/12 only and explicitly `release_ready=false` |
| PD-06 | Tombstone/version proof | Migration head, delete/disable/correction epoch bump, replay/retry/worker-restart rejection immediately before write | **PASS for readiness artifact** — 109 focused tests, 51 disposable PostgreSQL integration tests, migration `0018` |
| PD-07 | Rollback/disable | Default-off flag, provider gate, kill switch, queue drain/reject behavior, prior safe PostgreSQL path, runbook and recovery owner | **PASS for disable boundary; rollback rehearsal pending** — default false and stale-work rejection verified |
| PD-08 | Approval checkpoints | Named provider/privacy, security, engineering, independent QA, and Hamza/product approvals recorded before credentials, spend, or activation | **BLOCKED** — no approvals recorded |

## Required approval checkpoints (must be explicit)

1. **Policy task:** update this same idempotent task with the approved training-policy relaxation; no provider is selected.
2. **Privacy/security review:** named reviewer signs PD-01 through PD-03, including retention/deletion, residency/subprocessors/operators, access, incident handling, and budget boundary.
3. **Model-backed synthetic eval:** engineering records the pinned artifact, offline/network isolation, thresholds, raw report, and human review. `NOT_EVALUATED` or fixture-only evidence blocks promotion.
4. **Operational readiness:** engineering signs PD-04, PD-06, and PD-07, including a bounded rollback/disable drill using synthetic data only.
5. **Independent QA:** exactly one independent `qa-engineer` reviews the immutable packet and reruns the applicable checks. QA cannot approve production activation or set `release_ready`.
6. **Production-memory activation:** Hamza gives a separate, explicit written approval naming the exact environment, model/provider, flag change, rollback owner, and monitoring window. Without this checkpoint, extraction remains disabled even if all prior evidence passes.

**Current owner approval:** absent.
**Current production activation approval:** absent.
**Current decision:** remain blocked; do not select, purchase, credential, call, deploy, or activate.
