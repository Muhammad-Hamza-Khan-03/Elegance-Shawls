# Real customer queries: collection status

**Status: BLOCKED. No real customer query is collected, stored, scored or fabricated.** (Recorded 2026-11-12, issue #139.)

Why it is blocked:
- There is no live customer traffic. The only catalogue is synthetic (`scripts/seed_local`), the storefront is not launched, and the WhatsApp flows run locally only.
- Collecting real enquiries needs a privacy policy and the owner's written consent for logging, privacy scrubbing (names, phone numbers, addresses, order references removed before anything enters this repository), and a retention rule. None of these exist yet (see the provider and privacy gates in `docs/ELEGANCE_AI_COMMERCE_ARCHITECTURE.md`, sections 3.5 and 3.6).

What must exist before this is unblocked:
1. Live or pilot traffic with consent to use enquiry text for evaluation.
2. A scrubbing step that is itself reviewed, and a documented retention and deletion rule.
3. A qualified Urdu / Roman Urdu human reviewer, independent of whoever wrote the system, to label the scrubbed queries (see `evals/provenance.py` for the review vocabulary).

Until then, every dataset in `evals/datasets/` is synthetic, and `evals/provenance.yaml` says so. Do not add rows here that look like customer queries; do not mark any dataset human-reviewed without a signed review record.
