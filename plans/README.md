# Plans

Every plan for a system in this repo or for the store lives here, as Markdown. Write the plan first, get it agreed, then build from a branch cut from `main`.

## Conventions

- One file per plan, kebab-case name (`ai-platform.md`, `crm.md`).
- Reviews of a plan against the code sit next to it as `<plan>-alignment-review.md`.
- Plans change through pull requests. Significant decisions inside a plan also get an ADR once `docs/adr/` exists.
- Implementation state is not tracked here. Link the branch or PR instead.
- Keep `docs/` for how the system works today; keep `plans/` for where it is going.

## Index

| Plan | Status | Notes |
|---|---|---|
| [ai-platform.md](ai-platform.md) | Active (v1.0, 2026-10-29) | AI shopping assistant, hybrid search, memory, voice, platform |
| [ai-platform-alignment-review.md](ai-platform-alignment-review.md) | Active | Fit of the AI plan against the repo; open decisions before Phase 0 |
| [production-launch.md](production-launch.md) | Historical | Original launch checklist for the storefront |

The one-source ingestion design (`docs/phase-1-one-source-ingestion.md`) lives on the `phase-1/one-source-ingestion` branch and moves here when that work resumes.
