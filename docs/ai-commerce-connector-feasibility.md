# AI commerce connector feasibility

**Purpose and audience.** Plain-language feasibility note for the product owner, maintainers, and reviewers. It translates the uploaded connector report into a repository-grounded decision. The original cached report is preserved outside the repository and is not overwritten.

**Reviewed against:** `origin/staging-integration` at `63f1730663114d31085967ae01a05687bd614979` (2026-11-09).

## Bottom line

A connector is feasible, but a useful **ordering** connector is not ready to build yet. The repository already supports catalogue discovery, server search, stock-aware variants, a validated browser cart, and a WhatsApp enquiry handoff. It does **not** yet provide the server-side customer, cart, order, address, quote, payment, MCP, SDK, or HubSpot capabilities that an external AI would need to place and track an order safely.

The sensible sequence is:

1. keep the first connector read-only;
2. finish and independently verify customer identity, server-side cart, quote/order state, and audit boundaries;
3. add one authenticated connector surface (MCP or REST) over those backend services;
4. treat each client (site assistant, WhatsApp automation, Claude/ChatGPT/OpenClaw, SDK) as an adapter, not a separate commerce implementation.

## Evidence-based capability map

| Capability | Current status | Meaning |
|---|---|---|
| Browse products and product details | **Implemented** | Public catalogue and slug routes exist. |
| Search and hard constraints | **Implemented / partial** | `/v1/search` and hybrid search exist; results remain subject to catalogue availability and provider configuration. |
| Stock and variants | **Implemented** | Admin-managed catalogue data is read by the API; hard constraints are application-validated. |
| Browser cart and WhatsApp handoff | **Implemented** | Cart is browser-local and the server can create a validated enquiry reference; a person still completes the WhatsApp handoff. |
| Customer authentication | **Partial / disabled by default** | Customer session routes and principal boundaries exist behind configuration; this is not an enabled customer-facing login service. |
| Customer memory | **Partial / gated** | Provider-neutral CRUD and privacy/tombstone controls exist; extraction remains disabled and provider approval is blocked. |
| Server-side cart | **Not implemented** | External agents cannot share a durable cart with the site. |
| Quotes, orders, addresses, order status | **Not implemented** | The current enquiry is not an order, does not reserve stock, and does not confirm a sale. |
| MCP server or public connector API | **Not implemented** | No remote MCP endpoint or connector contract is in the repository. |
| Python SDK / local MCP wrapper | **Not implemented** | Proposed future packaging only. |
| HubSpot sync | **Not implemented** | The outbox/table shape is not evidence of a working HubSpot integration. |
| Payments | **Deferred** | Payment processing is outside the current architecture and launch boundary. |

## What can be built now

A read-only connector can expose catalogue search, product detail, availability checks, store policy text, and the existing WhatsApp handoff link. It must return live catalogue values from the backend, never invent prices or stock, and must not claim that an enquiry is an order.

This is useful for a site assistant or a controlled demo. It does not require customer login, payment credentials, a server-side cart, HubSpot, or an external AI client to access private data.

## What is deferred or blocked

Ordering through an external AI is deferred until the repository has a durable customer/session boundary, server-side cart, address handling, quote expiry, order state transitions, idempotency, audit evidence, and independent QA. Payment links and HubSpot mirroring are later integrations, not prerequisites for the read-only connector.

Production customer-memory extraction is a separate privacy gate. The current decision is `BLOCKED_PROVIDER_PRIVACY_DECISION`; `release_ready=false`; no provider is selected, no credentials are approved, and no production activation is authorized.

## Safety constraints for any future connector

- The backend remains the system of record; an AI client never talks directly to PostgreSQL or HubSpot.
- The model proposes; application code validates. Prices, stock, variant identity, totals, permissions, and order state come from server-side checks.
- Hard constraints are never relaxed silently. A quote must be computed by the server and expire; order creation must be idempotent and begin in a non-confirmed state.
- Customer data is scoped to the authenticated principal. Anonymous conversation labels are not identity.
- Product text and scraped content are data, not instructions.
- Every tool call and mutation needs bounded scopes, rate limits, audit provenance, and a kill switch.
- Read-only fallback must continue when AI, Redis, or an external provider is unavailable.
- No connector work authorizes deployment, production data access, provider spend, issue closure, or `release_ready=true`.

## Recommended future scope

**Phase A — read-only connector.** Publish a narrow authenticated or public read-only contract for search, product detail, availability, policy, and WhatsApp handoff. Add connector-specific rate limits, event attribution, contract tests, and an abuse review.

**Phase B — customer commerce primitives.** Implement and QA customer login, server cart, addresses, quote calculation, pending orders, cancellation rules, audit, idempotency, and reconciliation with the existing enquiry flow.

**Phase C — adapters and integrations.** Add one remote MCP surface, then thin adapters for the site assistant, WhatsApp automation, and SDK clients. Consider HubSpot as a one-way operational mirror only after order records are stable. Evaluate payment links separately.

This scope keeps the useful near-term demo honest: the repository can support AI-assisted discovery today, but it is not yet an AI checkout platform.
