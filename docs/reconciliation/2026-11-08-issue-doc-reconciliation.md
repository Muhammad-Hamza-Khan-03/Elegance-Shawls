# Issue and documentation reconciliation — 2026-11-08

## Current evidence boundary

- `origin/staging-integration`: `96baedfeef6578a38c7fddf8b446b39973cebd60` (PR #193, merged; docs CI passed).
- `origin/staging`: `e5c04c8d4097a46adf9fecf00baddd15cc860fc2` (PR #192, merged; hosted promotion CI required jobs passed).
- `origin/main`: `283b27eee90533435ef3b2e28e6a3823ee1c5d23` unchanged.
- EmbeddingGemma provenance: `google/embeddinggemma-2`, HF revision `f9972ac22e696a105c482202646979e33e4b5a1e`, tree digest `8338594ef62c913285891b775b6c3084e518001f499c1f97df61904c57ad708b`, weights digest `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79`, 768d CPU/local-only.
- QA evidence: Gemma/contract `35 passed, 1 skipped`; eval `14 passed`; embedding integration `21 passed`; schema integration `6 passed`; promotion QA `24 passed, 1 skipped`; docs PR #193 CI passed. Local `/health` and `/ready` returned 200 with DB/Postgres/Redis/worker connected.
- Boundary: `release_ready=false`; no main, production, deployment, credentials, provider selection, or production-memory activation.

## Open issue map

| Classification | Issues |
|---|---|
| VERIFIED COMPLETE (no closure: not an eligible close under the stated boundary) | none |
| IN PROGRESS | #49, #92, #94, #95, #98, #99, #100, #101, #108, #109, #129, #138, #139, #147, #156, #157, #158, #159, #160, #176 |
| DEFERRED / APPROVAL-GATED | #24, #43, #44, #93, #103, #104, #105, #106, #107, #111, #112, #145 |
| BLOCKED | #80, #82, #86, #138, #139, #146, #156, #157, #158, #159, #160, #176 |
| NOT STARTED / RECOMMENDATION | #45, #46, #50, #51, #52, #144 |

Some issues span two states: implementation evidence exists while an independent, hosted, approval, or real-data gate remains blocked. No open issue is closed by this reconciliation; epics, future phases, infrastructure/deployment, store recommendations, and issues without complete acceptance evidence remain open.

## Remaining blockers

Hosted staging acceptance and live proxy evidence, comparative/real-data evaluation provenance, external OTLP/Langfuse verification, provider/privacy and named-owner approvals, branch-protection approval, capacity measurements, backup/restore activation, and the approved E5 runtime/backfill remain outside the verified boundary. EmbeddingGemma evidence is local-only search/contract evidence and must not be treated as memory-extraction or production approval.