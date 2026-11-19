# Completion ledger

"Code 100%" is defined here, not by a percentage. A phase's code is complete when every row tagged **CODE-TODO** is **CODE-DONE**. Every other row carries its reason and is not claimed done.

Tags:

- **CODE-DONE**: present on `integration` (presence confirmed by grep on 2026-11-19; per-row test coverage is not re-verified here).
- **CODE-TODO**: buildable offline, free, with fakes or synthetic data, behind a default-off flag where it changes behaviour.
- **BLOCKED-EVIDENCE**: needs a human reviewer, real queries, model weights or signed statements. Never simulated.
- **BLOCKED-APPROVAL**: needs infrastructure, a paid or external service, activation, promotion or an owner decision.

Standing limits: `release_ready=false`, E5 canonical, no deployment, no activation, no real customer data, no merge without the owner's approval.

## Phase 0 and 0.5: foundation, ingestion

| Item (issue) | Tag | Reason / note |
|---|---|---|
| Postgres + pgvector, Alembic 0001-0021, SQLAlchemy async (#93, #94, #95) | CODE-DONE | |
| Redis + arq worker, Redis-backed rate limit (#98) | CODE-DONE | |
| LLM gateway, fake provider, budgets (#99) | CODE-DONE | Live free-tier call exercised only in bounded synthetic runs |
| Events endpoint, tracker, retention (#101) | CODE-DONE | `routes/event_routes.py`, `events/`, `src/lib/tracker.ts` |
| One-source ingestion | CODE-DONE | Independent staging QA tracked separately |
| OpenTelemetry/Langfuse export to Grafana/Langfuse (#100) | BLOCKED-APPROVAL | Needs external accounts; code hooks exist and are off by default |
| Application error capture (#146) | CODE-TODO | Backend reporter + `error.tsx`/`global-error.tsx`, no-op default, no provider |
| CI: gitleaks, Trivy, CodeQL, SBOM on PRs (#103) | CODE-TODO | Workflow files only |
| CI: multi-arch GHCR push on merge to `main` (#103) | BLOCKED-APPROVAL | Publishing images is an activation |
| Postgres backup activation, R2 destination, restore drill on real copy (#105) | BLOCKED-APPROVAL | Tooling exists (M1-S5); needs destination and credentials |
| VPS + Cloudflare (#106), env strategy (#104) | BLOCKED-APPROVAL | Paid infrastructure |
| Individual admin accounts promotion plan (#145) | CODE-TODO | Written plan only; the promotion itself is BLOCKED-APPROVAL |
| Docs update for the AI platform (#107), ADR docs (#92) | CODE-TODO | Folded into each slice's docs; ADRs live in the architecture doc by decision |

## Phase 1: catalogue intelligence and search (#108, #138)

| Item | Tag | Reason / note |
|---|---|---|
| `catalog/vocab.yaml`, deterministic parser, variant-level constraints, `POST /v1/search` | CODE-DONE | |
| Hybrid endpoint `POST /v1/search/hybrid`, pgvector embeddings (0012, 0021), E5 and EmbeddingGemma adapters | CODE-DONE | Semantic scoring is NOT_EVALUATED |
| Enrichment worker and admin review flow | CODE-DONE | |
| "More like this" | CODE-TODO | Reuses stored embeddings; default off |
| SigLIP/CLIP-class image embeddings | BLOCKED-EVIDENCE | Model weights are not available locally; schema (0021) and adapter point exist |
| Eval gate wired to real datasets (#138) | CODE-DONE | Gate runs in CI; canonical `--release-ready` exits 3 by design |
| Retrieval eval passing its release gate | BLOCKED-EVIDENCE | Needs E5 weights to rerun, and reviewed data |
| Human-reviewed dataset, second reviewer, real privacy-scrubbed queries (#139) | BLOCKED-EVIDENCE | No qualified Urdu/Roman Urdu reviewer identified |
| E5 fine-tuning experiment (#156-#160) | BLOCKED-EVIDENCE | Needs local weights and reviewed split |

## Phase 2: agentic UI (#109)

| Item | Tag | Reason / note |
|---|---|---|
| `POST /v1/assistant/stream` (SSE), grounded answers, confirmed actions (0013), assistant panel with confirmed actions | CODE-DONE | Behind flags |
| Guardrails: ID validation, grounding, caps, degradation | CODE-DONE | `grounded._matches` price check lacks real-stack coverage |
| Percentage rollout flag | CODE-TODO | Verify in slice; add if missing |
| Agent eval >= 85%, zero grounding/safety violations | BLOCKED-EVIDENCE | Needs reviewed agent eval data |
| Enabling the assistant for users | BLOCKED-APPROVAL | Activation; gated on Phase 1 release |

## Phase 3: identity and memory

| Item | Tag | Reason / note |
|---|---|---|
| Customer sessions, memory, consent, anonymous merge, privacy epoch (0014-0018), memory UI | CODE-DONE | Synthetic-only |
| Recommendation impressions and explainable suggestions (0017) | CODE-DONE | |
| Batch C privacy gate | BLOCKED-EVIDENCE | Provider/privacy decision not made |
| Provider choice and credentials (#176) | BLOCKED-APPROVAL | Owner decision |

## Phase 4: voice (#111)

| Item | Tag | Reason / note |
|---|---|---|
| ASR contract, bridge, normalisation, WhatsApp voice transcription | CODE-DONE | `voice/` |
| `voice_jobs` migration and audio retention job | CODE-TODO | Schema + deletion job, no audio stored by default |
| Mic input with text fallback, 30 s limit in storefront | CODE-TODO | Flag off; fake transcriber in tests |
| faster-whisper worker dependency and models | BLOCKED-APPROVAL | New dependency and model download; optional import already present |
| Urdu ASR ML project (MLflow, DVC, WER vs Whisper) | BLOCKED-EVIDENCE | Needs recordings and reviewers |
| ASR extracted to its own service | BLOCKED-APPROVAL | Infrastructure |

## Phase 5: production platform (#112)

| Item | Tag | Reason / note |
|---|---|---|
| Ansible, k3s, OpenTofu, Helm, Argo CD, SOPS | BLOCKED-APPROVAL | Cannot be validated without infrastructure; unvalidated manifests would be unverified claims |
| SLO dashboards, alerts, k6 load tests | BLOCKED-APPROVAL | Needs a running environment (#86) |
| Nightly eval pipeline, weekly drift report | BLOCKED-APPROVAL | Scheduling is activation |
| Runbooks, postmortem template | CODE-TODO | Docs only |

## Storefront feature backlog

| Item | Tag | Reason / note |
|---|---|---|
| Size guide + FAQ trust modules (#50) | CODE-TODO | Delivery and returns pages exist |
| Wishlist (#51) | CODE-TODO | localStorage, same pattern as the cart |
| Conversion tracking hooks, WhatsApp order-click event (#52) | CODE-TODO | Uses the existing tracker; respects Do Not Track |
| Selective caching for catalogue pages (#144) | CODE-TODO | Only if it keeps price/stock correct; otherwise documented skip |
| LICENSE (#43) | BLOCKED-APPROVAL | The licence is the owner's legal choice |
| Remote image host restriction, CSP review (#80) | CODE-TODO | |
| Main branch protection (#82, #24) | BLOCKED-APPROVAL | Settings change, after approval |

## Release and promotion

| Item | Tag | Reason / note |
|---|---|---|
| `integration` to `staging` PR with diff, inventory, CI evidence, rollback plan | CODE-TODO | PR opened, not merged |
| `staging` to `main` (385 files, migrations) | BLOCKED-APPROVAL | Explicit production approval required |
| Dependabot PRs targeting `main` | BLOCKED-APPROVAL | Dependabot reads `.github/dependabot.yml` from the default branch (`main`); the retarget in #203 only reaches it on promotion |
