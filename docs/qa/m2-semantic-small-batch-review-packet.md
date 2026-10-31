# M2 Semantic-Search Small-Batch Multilingual Review Packet

**Packet status:** `READY_FOR_HUMAN_REVIEW` (mechanical preparation only)

**Release status:** `NOT_EVALUATED`; `release_ready=false`

This packet is a read-only review handoff for the accepted M2 tip. It does not authorize provider calls, model activation, staging, deployment, fixture mutation, or release-flag changes.

## 1. Frozen review boundary

| Item | Value |
|---|---|
| Repository | `/home/hamza/worktrees/m2-semantic-review-packet-44c0d13` |
| Application/evaluation baseline SHA | `44c0d1374e6d478658b10121bb4c8d40c24a3850` |
| Application/evaluation baseline parent | `d7ebaefa67901132a05aaf32ac1c374227ff3dcd` |
| Packet artifact commit before this metadata correction | `36dfa8cd8899ff0949ac58e7e8202b7244ac6b60` |
| Worktree | detached, isolated from the canonical checkout |
| Representation version | `ps-v1` |
| Evaluator | `evals/semantic_eval.py` |
| Global runner | `evals/run_evals.py` |
| Thresholds | `evals/thresholds.yaml` |
| Semantic fixture | `evals/synthetic/semantic_retrieval.jsonl` |
| Parser fixture | `evals/datasets/filter_parsing.jsonl` |
| Semantic fixture SHA-256 | `a27e3ceb36eece21386bd0e3bc3716d4e6ab3790fe578f4d294e6aeadb3d6209` |
| Parser fixture SHA-256 | `d021ab12244f78ff56d8fe7685e01334e857ad2b30369e72af213cbe38cb78de` |
| Thresholds SHA-256 | `b80a4db1670d28a0aa7977d00ef617252143a0fb9a3ed533ea23b367ba591f1a` |
| Semantic evaluator SHA-256 | `563036a4cf103424aa78599effb9ca8d7e668c52aed2ddce1724bd87465c7d64` |
| Global runner SHA-256 | `e736df702fc88a33e346af3f04443562659e2bea75992060d88fa5fbd91cecef` |

The semantic checksum above is the digest of the exact JSONL bytes, not a digest of parsed or normalized JSON.

## 2. What is currently present

- `semantic_retrieval.jsonl`: **2** synthetic English retrieval cases; both have `reviewed: false`.
- `filter_parsing.jsonl`: **17** parser cases: English **10**, Roman Urdu **4**, Urdu **3**.
- Parser coverage includes **3** negation cases — `fp-003` (`not black`), `fp-010` (`not under 1000`), and `fp-015` (`white nahi`) — and **8** price-constrained cases.
- `datasets/variant_constraints.jsonl` is **absent**. Same-variant behavior is therefore a required manual review topic, not a currently scored global suite.
- The semantic evaluator uses `fake` / `fake-hash-v1`, 64 dimensions, `k=3`; this is a harness provider and cannot constitute quality evidence.

## 3. Small-batch review plan

Review in batches of at most five cases. Each reviewer should mark each case independently before discussing disagreements. Use the existing fixture IDs where available; do not edit the canonical fixture during review.

### Batch A — English baseline and negation (5 cases)

`fp-001`, `fp-002`, `fp-003`, `fp-004`, `fp-005`

Check:

- lexical intent and category (`stole`, `shawl`, `scarves`);
- color inclusion (`brown`, `black`, `maroon`);
- explicit negation: `not black` must become an exclusion, not an additional included color;
- `in stock` must be a hard availability constraint;
- `under` and `between` must be interpreted consistently with the approved numeric-bound policy.

### Batch B — Roman Urdu and Urdu (5 cases)

`fp-006`, `fp-007`, `fp-008`, `fp-009`, `fp-017`

Check:

- `bhoora`, `safaid`, `کالا`, and `کریم` map only to the controlled canonical vocabulary;
- `shawal` / `شال` and `stole` / `اسٹول` preserve the intended category;
- Urdu-Indic digits (`۴۰۰۰`) parse identically to ASCII digits;
- language classification is `roman_ur` or `ur`, with no silent unsupported-language fallback;
- reviewer is a native or qualified language reviewer, or records that this is unavailable.

### Batch C — Price and contradiction boundaries (5 cases)

`fp-010`, `fp-012`, `fp-013`, `fp-014`, `fp-016`

Check:

- `not under 1000` means a lower bound (`min_price=1000`), not a negated query or `max_price`;
- `above` / `se zyada` and `under` / `se kam` follow one documented inclusivity rule;
- `grey or beige` is intentionally ambiguous in the parser contract and must not be promoted to a silent single-color interpretation;
- price currency defaults and stated currency are recorded with provenance;
- mixed/unsupported currency and malformed numeric inputs are rejected or routed to review.

### Batch D — Same-variant retrieval semantics (manual fixture required)

Use a reviewer-created, non-production micro-corpus with opaque synthetic IDs. It must contain at least:

1. one product with a **single variant** satisfying both requested color and size;
2. one product where color exists on variant A and size exists on variant B, but **no single variant** satisfies both;
3. one inactive/draft product and one out-of-stock variant;
4. one exact-boundary price case and one outside the price bound;
5. one stale/missing-vector record that must not rank above eligible records.

For a query such as `in stock brown medium shawl under 4000`, accept only a result whose same variant is brown **and** medium, active, purchasable, and within the bound. Product-level aggregation across different variants is a failure. Record the synthetic corpus digest and do not use customer/provider data.

## 4. Reviewer evidence fields

One row is required per reviewed case or manual same-variant scenario.

| Field | Required content |
|---|---|
| `case_id` | Fixture ID or reviewer-created opaque scenario ID |
| `batch_id` | `A`, `B`, `C`, or `D` |
| `fixture_sha256` | Exact raw fixture digest used for the review |
| `repo_sha` | Exact reviewed commit SHA |
| `query_text` | Exact query, preserved as UTF-8; do not normalize it in the evidence record |
| `language` | `en`, `ur`, `roman_ur`, or `n/a` |
| `expected_intent` | Categories, included/excluded colors, price bounds, stock, and provenance expectations |
| `observed_intent` | Parser/evaluator output under review |
| `expected_result_ids` | Ordered or set-valued IDs with ordering policy stated |
| `observed_result_ids` | Actual result IDs, including excluded candidates if useful for diagnosis |
| `same_variant_check` | `pass`, `fail`, or `not_applicable`; explain variant IDs when applicable |
| `negation_check` | `pass`, `fail`, or `not_applicable` |
| `price_boundary_check` | `pass`, `fail`, or `not_applicable`; state inclusive/exclusive interpretation |
| `reviewer_id` | Human reviewer handle, not email/phone/PII |
| `reviewer_qualification` | Native/qualified language or domain reviewer; state `not_available` if absent |
| `reviewed_at` | UTC timestamp |
| `decision` | `accept`, `reject`, or `needs_discussion` |
| `notes` | Brief rationale and disagreement reference; no raw provider response or secret |

A case marked `accept` is not a release approval. It is only human evidence for that case.

## 5. Regression metrics and minimum evidence

Report metrics separately for each language and for the aggregate. Do not average away a failing cohort.

Required metrics:

- parser exact match;
- constraint precision and recall, with included and excluded constraints counted separately;
- negation precision/recall;
- price-bound precision/recall plus boundary-case accuracy;
- same-variant hard-constraint violations (must be **0**);
- recall@3 for the semantic micro-batch and recall@10 for the eventual larger retrieval set;
- missing/stale-vector exclusion errors (must be **0**);
- repeat-run stability / Jaccard for deterministic ranking;
- count of ambiguous or unsupported queries correctly routed to human review;
- per-cohort counts and denominators.

The current parser threshold file requires `exact_match >= 0.90`, `constraint_precision >= 0.95`, and `constraint_recall >= 0.95`. These thresholds do not waive human review, same-variant evidence, fixture provenance, or the non-test-provider requirement. A perfect mechanical score from fixture responses remains `NOT_EVALUATED`.

## 6. Fixture/version/checksum rules

Before review begins, record the frozen application/evaluation baseline and the packet artifact separately:

```text
application_evaluation_baseline_sha=44c0d1374e6d478658b10121bb4c8d40c24a3850
application_evaluation_baseline_parent=d7ebaefa67901132a05aaf32ac1c374227ff3dcd
packet_artifact_commit_before_metadata_correction=36dfa8cd8899ff0949ac58e7e8202b7244ac6b60
representation_version=ps-v1
semantic_fixture_sha256=a27e3ceb36eece21386bd0e3bc3716d4e6ab3790fe578f4d294e6aeadb3d6209
parser_fixture_sha256=d021ab12244f78ff56d8fe7685e01334e857ad2b30369e72af213cbe38cb78de
thresholds_sha256=b80a4db1670d28a0aa7977d00ef617252143a0fb9a3ed533ea23b367ba591f1a
evaluator_sha256=563036a4cf103424aa78599effb9ca8d7e668c52aed2ddce1724bd87465c7d64
```

Any fixture, threshold, evaluator, representation, or ranking change invalidates prior review evidence. Recompute all hashes and restart the affected batch. Do not overwrite a prior evidence record; link the new record to the new digest.

## 7. Mechanical commands and observed baseline

Executed from the isolated worktree, without provider/network calls:

```bash
sha256sum evals/synthetic/semantic_retrieval.jsonl evals/datasets/filter_parsing.jsonl \
  evals/thresholds.yaml evals/semantic_eval.py evals/run_evals.py
python evals/semantic_eval.py --release-ready     # exit 3
python evals/run_evals.py --release-ready         # exit 3
python -m pytest -q apps/backend/tests/test_evals_runner.py \
  apps/backend/tests/test_semantic_contract.py   # 30 passed
```

Observed evaluator result: `recall_at_3=1.0`, `cases=2`, status `NOT_EVALUATED`, reasons `cases not human-reviewed` and `test-only fake provider is not evidence`, `release_ready=false`.

Observed global result: all five configured suites are `NOT_EVALUATED`; parser harness metrics are exact match `1.0`, constraint precision `1.0`, constraint recall `1.0`, but recorded responses are fixtures rather than model output; `release_ready=false`.

## 8. Explicit release-gate semantics

The release gate remains closed until all of the following are true:

1. required fixture cohorts exist and their exact digests are recorded;
2. English, Urdu, and Roman Urdu cases have qualified human review evidence;
3. negation, price-bound, contradiction, and same-variant cases pass with zero hard-constraint violations;
4. all required regression metrics meet thresholds for aggregate and each required cohort;
5. semantic results come from an approved non-test provider/model with pinned provenance, not `fake` / fixture rows;
6. the global runner has no `NOT_EVALUATED` or failed required suite;
7. an independent QA reviewer confirms the packet, evidence integrity, and no-provider/no-release boundary.

Until those conditions are met, the only valid global state is:

```text
semantic_status=NOT_EVALUATED
release_ready=false
```

A reviewer must not pass `--release-ready`, edit release flags, activate a feature flag, deploy, or infer provider compatibility from this packet. Mechanical harness success, local integration success, or a perfect fake-provider recall score cannot change that state.

## 9. Handoff outcome

This packet is a docs-only review artifact. It deliberately does not add or mutate fixtures, evaluator code, thresholds, provider configuration, release state, or canonical checkout contents. Human reviewers should return the completed evidence table and any proposed fixture additions for a separately scoped, independently reviewed change.
