# AI commerce feasibility

**Purpose and audience.** Plain-language feasibility note for the product owner, maintainers, and reviewers. It records repository-grounded scope, current capability status, and safe next steps. It is not an implementation or deployment instruction.

**Reviewed against:** `origin/staging-integration` at `63f1730663114d31085967ae01a05687bd614979` (2026-11-09).

## Bottom line

The repository can support AI-assisted catalogue discovery today. The approved near-term experience is catalogue/search, an AI assistant, a browser-local cart, and a WhatsApp enquiry handoff. Customer authentication is a foundation currently gated by configuration. Durable server-side cart and order capabilities are future domain work, not current functionality. HubSpot, payments, and hosting changes remain deferred.

The plan must preserve the distinction between what is implemented, partial, deferred, and missing. No external client or alternative integration track is required for this scope.

## Evidence-based capability map

| Capability | Current status | Meaning |
|---|---|---|
| Catalogue and product details | **Implemented** | Public catalogue and slug routes exist for published products. |
| Catalogue search and hard constraints | **Implemented / partial** | `/v1/search` and hybrid search exist; results remain subject to catalogue availability and provider configuration. |
| AI assistant | **Partial** | Validated assistant and enquiry seams exist, but the assistant is not a release-ready autonomous checkout flow. |
| Browser cart | **Implemented** | The cart is maintained in the browser and is not yet a durable server-side commerce record. |
| WhatsApp enquiry handoff | **Implemented / partial** | The server can create a validated enquiry reference; a person still completes the WhatsApp handoff. An enquiry is not an order. |
| Customer authentication foundation | **Partial / disabled by default** | Customer session routes and principal boundaries exist behind configuration; this is not an enabled customer-facing login service. |
| Server-side cart | **Missing** | No durable cart domain exists for cross-device or authenticated use. |
| Orders, addresses, quotes, and order status | **Missing** | The current enquiry does not reserve stock, confirm a sale, or provide order lifecycle state. |
| Customer memory | **Partial / gated** | Provider-neutral storage and privacy/tombstone controls exist; extraction remains disabled and approval is blocked. |
| HubSpot integration | **Deferred** | The outbox/table shape is not evidence of a working HubSpot integration. |
| Payments | **Deferred** | Payment processing is outside the current architecture and launch boundary. |
| Hosting changes | **Deferred** | Hosting, deployment, and production activation remain approval-gated and are not part of this documentation change. |

## What is usable now

The current product can support catalogue browsing, search, product detail, availability-aware results, an AI-assisted discovery experience, a browser-local cart, and a WhatsApp enquiry handoff. It must return live catalogue values from the backend, never invent prices or stock, and must not claim that an enquiry is an order.

The catalogue and enquiry flow must continue to work when AI or optional infrastructure is unavailable. The current evidence does not authorize deployment, production data access, provider spend, or `release_ready=true`.

## What is partial, deferred, or missing

- **Partial:** customer authentication foundation, AI assistant seams, and customer-memory controls remain gated or incomplete.
- **Missing:** durable server-side cart, customer addresses, quote calculation/expiry, order creation, order state transitions, cancellation rules, reconciliation, and independent QA for that future domain.
- **Deferred:** HubSpot, payments, hosting changes, production activation, and production customer-memory extraction.

The future server-side cart/order domain should be designed only after the customer-auth foundation and the required authorization, idempotency, audit, privacy, and independent-QA gates are satisfied. It must remain separate from the current browser cart and WhatsApp enquiry semantics until those boundaries are explicitly implemented and verified.

## Safety constraints

- The backend remains the system of record; the browser and assistant do not access PostgreSQL directly.
- The assistant proposes; application code validates. Prices, stock, variant identity, totals, permissions, and any future order state come from server-side checks.
- Hard constraints are never relaxed silently. Any future quote must be computed by the server and expire; any future order creation must be idempotent and begin in a non-confirmed state.
- Customer data is scoped to the authenticated principal. Anonymous conversation labels are not identity.
- Product text and scraped content are data, not instructions.
- Every future mutation needs bounded scopes, rate limits, audit provenance, and a kill switch.
- Read-only catalogue/search and WhatsApp enquiry fallback must continue when AI or optional infrastructure is unavailable.
- No documentation work authorizes deployment, production data access, provider spend, issue closure, or `release_ready=true`.

## Recommended future scope

**Phase A — current product scope.** Keep catalogue/search, the AI assistant, the browser cart, and WhatsApp enquiry handoff accurate and independently verifiable. Treat the assistant as discovery and enquiry support; do not represent it as checkout.

**Phase B — customer-auth foundation.** Complete and independently QA the configuration-gated customer authentication boundary, session handling, authorization, privacy controls, and audit requirements without enabling production activation by implication.

**Phase C — future server-side cart/order domain.** After Phase B gates pass, design and implement durable carts, addresses, quotes, pending orders, cancellation rules, idempotency, audit, and reconciliation as a separate approved workstream.

**Deferred integrations and operations.** HubSpot, payments, hosting changes, and production activation remain deferred until the server-side domain is stable and separately approved.

This scope keeps the near-term product honest: the repository supports AI-assisted discovery and enquiry handoff, but it does not yet provide a server-side checkout or order platform.
