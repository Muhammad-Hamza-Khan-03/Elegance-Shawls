# M4 Batch C promotion packet (readiness, not activation)

**Task:** `t_m4c_promotion_packet`
**Parent:** `t_m4c_production_memory_privacy_gate`
**State:** `BLOCKED`; `release_ready=false`; no production-memory activation is permitted.

## Evidence currently available

- Batch A QA-passed staging baseline: `dff5248e96911640c1b039481b0fd0a7464dc0d1`.
- Batch B QA-passed staging baseline: `6d4dcff6d2818f9b49c1d443248c0660fee14d98`.
- Existing explicit PostgreSQL `MemoryProvider`, consent, customer controls, content-free tombstones, and audit contract preserved.
- Batch C readiness artifacts: provider decision packet, synthetic multilingual evaluation fixture/runner, `memory_version` migration, and stale-work guard.

## Exact remaining gates

1. **Provider decision:** dated paid no-training contract/account evidence or pinned self-hosted model/license; no opt-out/free-tier evidence accepted.
2. **Privacy/security review:** retention/deletion, subprocessors/region, access, incident, logging, and budget review signed by named owner.
3. **Model-backed eval:** local/self-hosted or otherwise approved synthetic-only evaluation passes agreed save/do-not-save/correction/relevance/sensitive-refusal/consent/forgetting thresholds in English/Urdu/Roman Urdu where applicable.
4. **Queued-job proof:** PostgreSQL migration applied in disposable/staging DB; deletion/disable/correction bump `memory_version`; replay, retry, and worker-restart stale work is rejected immediately before write.
5. **Customer-control proof:** view/correct/delete/turn-off, ownership isolation, retention, audit, rollback, and fail-closed provider/config tests pass.
6. **Independent QA:** reviewer not implementing the artifacts signs the complete synthetic packet and records command output.
7. **Approvals:** provider/privacy owner, privacy/security owner, engineering owner, and Hamza/product owner explicitly approve later promotion. QA cannot promote or set `release_ready`.
8. **Only after all above:** a separately approved staging activation plan may be written. No deployment, VPS, main, live credentials, customer data, issue closure, or release-ready flag is authorized here.

## Current blockers and approvals needed

- Provider/model: **not selected**; Hamza approval is required before paid spend or credentials.
- Model-backed eval: **pending** approved provider/model and thresholds.
- Disposable PostgreSQL migration/integration evidence: **pending**.
- Independent QA sign-off and staging push: **pending** until implementation checks pass.
