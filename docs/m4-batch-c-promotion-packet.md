# M4 Batch C production-memory promotion packet (readiness, not activation)

**Task ID:** `t_m4c_promotion_packet`
**Parent task:** `t_m4c_production_memory_privacy_gate`
**Idempotency key:** `m4c-production-memory-privacy-gate/promotion-packet/v1`
**Policy change key:** `m4c-provider-training-policy-relaxation/v1`
**Packet revision:** `2026-11-08-live-ref-reconciliation-provider-controls`
**State:** `STAGING_EVIDENCE_RECORDED; BLOCKED_FOR_ACTIVATION`
**`release_ready`:** `false`
**Production memory:** disabled; no activation is authorized.

Re-applying this packet updates the same task and idempotency key. It must not create duplicate tasks, select a provider, incur spend, add credentials, call a live provider, access customer data, deploy, touch `main`/VPS, close issues, or set `release_ready`.

## Candidate identity and ancestry reconciliation

The packet is reconciled to the current integration ref:

- `origin/staging-integration`: `96baedfeef6578a38c7fddf8b446b39973cebd60` (PR #193, docs-only merge; candidate implementation is promoted through PR #192)
- `origin/staging`: `e5c04c8d4097a46adf9fecf00baddd15cc860fc2` (PR #192, protected promotion)
- `origin/main`: `283b27eee90533435ef3b2e28e6a3823ee1c5d23` (unchanged)
- PR #179 provider-policy merge: `e04fb7470fb921032086f8c99217247458efec1d`; PR #191 EmbeddingGemma contract merge: `4675052b7b983c24b46b2d39fa18e4f1a8815124`; PR #193 docs merge: `96baedfeef6578a38c7fddf8b446b39973cebd60`.

The provider/privacy and production-activation gates remain open.

## Staging verification packet

The provider policy, migration fixture, and EmbeddingGemma contract are present on the promoted lineage. Independent evidence includes Gemma/contract `35 passed, 1 skipped`, evaluation `14 passed`, embedding integration `21 passed`, schema integration `6 passed`, promotion QA `24 passed, 1 skipped`, and hosted promotion CI with all required jobs passing on PR #192; docs PR #193 also passed all required CI. Local readiness at `127.0.0.1:18000` reported database/PostgreSQL, Redis, and worker connected. No secret, API-key value, customer data, deployment, provider activation, or production claim is included.

This packet remains non-production. It does not prove a hosted deployment, frontend live proxy (a disposable backend URL is still needed), embeddings activation/backfill, complete evaluation provenance, or external observability. `release_ready` remains false.

## Verified EmbeddingGemma 2 search candidate

The exact candidate merged by PR #191 at `4675052b7b983c24b46b2d39fa18e4f1a8815124` is `google/embeddinggemma-2`, pinned to Hugging Face revision `f9972ac22e696a105c482202646979e33e4b5a1e`, with model-tree SHA-256 `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b` and weights SHA-256 `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`. It is a 768-dimensional CPU/local-only search candidate; this record does not authorize hosted activation, memory extraction, deployment, or production use.

Quality evidence: overall recall `0.9973`, MRR `0.9706`, synonym recall/MRR `1.0`, hard-constraint violations `0`, and reproducibility Jaccard `1.0`. Independent QA: Gemma/contract `35 passed, 1 skipped`; eval `14 passed`; embedding integration `21 passed`; schema integration `6 passed`; compileall/diff-check passed; disposable DB backfill `8/8`, idempotent rerun, and retrieval passed. Remaining gates are hosted staging acceptance, external OTLP/Langfuse, reviewed evaluation/model provenance, and production activation/deployment; `release_ready` remains false.

## Verified readiness evidence already available

| Area | Evidence | Interpretation |
|---|---|---|
| Batch A | `dff5248e96911640c1b039481b0fd0a7464dc0d1`, QA-passed staging baseline | Satisfied prerequisite; not provider approval |
| Batch B | `6d4dcff6d2818f9b49c1d443248c0660fee14d98`, QA-passed staging baseline | Satisfied prerequisite; not provider approval |
| M4 Batch C canonical backend | `1604 passed, 601 deselected` | Implementation/readiness evidence only |
| Focused memory/privacy | `109 passed, 11 deselected` | Provider contract, consent, principal, queue/tombstone/version coverage |
| Disposable PostgreSQL | `51 passed`, 2 Testcontainers deprecation warnings | Migration and memory/merge integration; no shared/production DB |
| Migration | Alembic `0018` is head | `memory_version`/privacy epoch schema proof |
| Synthetic evaluator | 12/12; `en=5`, `roman_ur=4`, `ur=3`; two byte-identical reports | Deterministic offline fixture contract only; not model-backed evidence |
| Safety counters | `provider_calls=0`, `database_writes=0`, `release_ready=false` | Confirms the readiness run did not call a provider or write a database |
| Queue/tombstone | Disabled extraction, stale `memory_version`, replay/retry/worker-restart, tombstone boundaries covered | Pre-write fail-closed behavior; not a production activation |
| M2 search model | Local EmbeddingGemma2 promoted separately at current tip | Search/embedding only; not memory-extraction approval |

## Promotion gates and current verdict

| Gate | Required to clear | Current verdict |
|---|---|---|
| G1 Provider decision | Exact candidate terms or local isolation/license, or a complete independently verified control record for a training-enabled provider; no free/opt-out/unverified evidence | **BLOCKED** — no option selected and no control record approved |
| G2 Retention/deletion | Provider/local-store schedule, logs/queues/caches/backups, deletion proof, legal-hold/incident terms | **PARTIAL** — application tombstones/retention exist; selected provider/model behavior absent |
| G3 Residency/security | Regions, subprocessors/operators, access, encryption, keys, network isolation, incident response | **BLOCKED** — exact boundary absent |
| G4 Extraction separation | Separate extraction artifact/config/cache and fail-closed model/provider chain; M2 search model excluded | **PASS for architecture boundary; BLOCKED for model approval** |
| G5 Model-backed eval | Pinned model, offline or approved provider isolation, synthetic-only dataset, human review, thresholds and raw results | **NOT EVALUATED** — existing 12/12 runner is deterministic contract evidence, not model quality |
| G6 Tombstone/version | Delete/disable/correction bump and immediate pre-write rejection of replay/retry/restart stale work | **PASS for readiness evidence** — 109 focused, 51 disposable PostgreSQL, migration `0018` |
| G7 Customer controls | View/correct/delete/turn-off, ownership isolation, audit, retention, and no silent relaxation | **PASS for current implementation tests; activation still blocked** |
| G8 Rollback/disable | Default-off flag, kill switch, stale queue rejection, rollback runbook and bounded synthetic drill | **PASS for disable boundary; rollback drill pending** |
| G9 Independent QA | One independent reviewer signs the complete final packet and exact immutable artifact | **PASS for prior Batch C readiness artifact only; this provider-decision revision needs review if treated as a new QA artifact** |
| G10 Named approvals | Provider/privacy, security, engineering, independent QA, and Hamza/product approval; separate activation approval | **BLOCKED** — absent; policy relaxation is not provider or activation approval |

**Strict roll-up:** `BLOCKED_PROVIDER_PRIVACY_DECISION`; no promotion and no production-memory activation.

## Provider/local decision rubric (no selection made)

A paid no-training option is acceptable only if its exact account/endpoint/model terms, retention/deletion settings, residency/subprocessors, security controls, incident terms, and budget are written and independently checked. Its operational advantage is lower model-hosting burden; its risks are recurring spend, provider retention/abuse-monitoring policy, region/transfer dependency, and account configuration drift.

A self-hosted/local option is acceptable only if its exact model license/provenance/digests, offline runtime, blocked outbound sockets, host/region/operator controls, disk/log/queue/cache/backup retention, deletion proof, patching, and rollback budget are written and independently checked. Its advantage is a stronger direct no-provider-ingress boundary; its risks are model/supply-chain integrity, capacity, patching, observability, operator access, and infrastructure cost.

Neither option is selected here. This packet intentionally does not purchase an account, choose a model, request credentials, or claim that generic provider documentation is an approval.

## Evidence required before any later promotion

1. `t_m4c_provider_decision`: the approved idempotent policy change permits training-enabled providers only with the complete, use-case-scoped control record; no provider is selected. Exact provider/account/model approval remains a later checkpoint.
2. `t_m4c_memory_extraction_evals`: run the same reviewed synthetic English/Urdu/Roman Urdu cases through the pinned model, with save/do-not-save, correction, relevance, sensitive refusal, consent, and forgetting thresholds. Record model digest, runtime versions, network isolation, raw report, human review, and `provider_calls`/`database_writes` counters.
3. `t_m4c_tombstone_queue_proof`: retain the current migration/guard evidence and add the exact worker boundary proof that `accept_result` is called immediately before any write; prove delete, disable, correction, replay, retry, and worker restart cannot recreate stale memory.
4. `t_m4c_independent_qa`: exactly one independent read-only `qa-engineer` reviews the immutable candidate and packet, reruns applicable checks, and records `QA VERDICT: PASS|FAIL|PARTIAL`. A prior QA PASS for the readiness artifact does not approve an unselected provider or a new model-backed eval.
5. `t_m4c_push_staging`: only after the relevant QA PASS, commit/push documentation/evidence only to `origin/staging`, verify remote SHA equality, and leave production memory disabled. This task cannot close the gate or set `release_ready`.

## Rollback and disable controls (pre-activation contract)

- Keep `MEMORY_EXTRACTION_ENABLED=false` unless a separately approved environment-specific activation changes it.
- Require the provider/model gate to return a fixed denial for missing, unknown, free-tier, opt-out, or mixed fallback chains.
- Before every queued-memory write, reject disabled extraction, mismatched `memory_version`, replay/retry/worker-restart stale work, and work at/before a tombstone.
- If a candidate is withdrawn, set the extraction flag false, stop/drain the extraction worker, reject queued work via the version/tombstone guard, preserve PostgreSQL CRUD/customer controls, and record the exact disabled timestamp/owner. Do not delete search/embedding configuration as a substitute for memory rollback.
- A future activation runbook must name the rollback owner, health/queue signals, disable command/config change, verification probe, and synthetic cleanup evidence. No such activation runbook is approved by this packet.

## Explicit approval checkpoints

- [ ] Hamza selects one exact paid no-training contract/account **or** one exact self-hosted/local model snapshot/license for evaluation only.
- [ ] Named privacy/security owner approves no-training/isolation, retention/deletion, residency/subprocessors/operators, access, incident handling, and budget.
- [ ] Engineering owner approves extraction/search model separation and the fail-closed config.
- [ ] Synthetic model-backed evaluation is non-empty, reproducible, thresholded, human-reviewed, and not `NOT_EVALUATED`.
- [ ] Tombstone/version/queue proof and rollback/disable drill pass on synthetic/disposable infrastructure.
- [ ] Independent QA signs the exact final candidate and this packet.
- [ ] Hamza gives a separate written production-memory activation approval naming environment, exact model/provider, flag change, rollback owner, and monitoring window.

Until every applicable box is checked, the precise decision is: **do not select or purchase a provider, do not add credentials, do not run live memory extraction, do not activate production memory, and keep `release_ready=false`.**
