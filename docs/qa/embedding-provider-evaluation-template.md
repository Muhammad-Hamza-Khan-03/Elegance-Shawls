# Embedding provider evaluation record — template

Copy this file per candidate, fill it in, and keep it free of raw artifacts. One provider/model candidate per record; the
programme evaluates at most 4. This gate uses only the fictional corpus `evals/datasets/embedding_synthetic.jsonl`
(96 records, 64 queries). A pass here is evidence about retrieval on that corpus. It does **not** set `release_ready`
in `run_evals.py` or any other release flag, and it is not a decision to enable embeddings in the product.

## Corpus provenance and review (fixed record; do not edit per candidate)

| Field | Value |
|---|---|
| Reviewed file | `evals/datasets/embedding_synthetic.jsonl` |
| Reviewed sha256 | `c5382437d5bad1ee823b9286fe163e4bc69b11162bdcbdb152ba4b283ab78b96` (pinned in `embedding_thresholds.yaml`) |
| Reviewer role / date | Implementing engineer (Claude, an AI assistant), 2026-10-30, repeated after independent QA findings |
| Scope | All 96 records and all 64 query gold sets, checked against record metadata, query constraints and each query's `semantic_attrs` |
| Authorship | Generated once by a throwaway script from hand-written vocabulary tables; gold sets are explicit ID lists in the file |

Checked, each by script and by reading the file:

- Counts, cohort sizes (16 each), 10 missing and 10 stale records, 16 hard-constraint queries covering all 8 constraint types.
- Every gold ID exists, has a current vector, satisfies the query's hard constraints, and gold equals *every* such record matching `semantic_attrs` (no omitted or extra members).
- Price comparators: queries use "above / more than / zyada" and "under / less than / kam" (strict), while the evaluator compares inclusively. Each of the four price queries (SYN-Q049, Q050, Q057, Q058) therefore uses a bound that no record's price equals, so both readings give the same gold set. Fixture validation and the tests enforce this.
- Fictional only: `SYN-` IDs, `Sample Loom NNN` names, no URLs, emails, phone-like numbers or names from the other eval catalogues.
- Language and comparator wording per cohort (English, Urdu script, Roman Urdu, paraphrase).

No external human, native-speaker or domain-expert review has taken place. The Urdu and Roman Urdu text is formulaic
(word lists, not fluent prose) and should get a native-speaker read before it is cited as evidence of Urdu quality.

### Synonym-cohort diagnostic (offline, not a provider result)

`python evals/run_synonym_error_analysis.py` is a string-matching diagnostic over the unchanged fixture: the 16 synonym
queries replace canonical attributes with descriptive phrases, so lexical matching recognises none of them. It also
applies `evals/synonym_aliases.yaml`, a one-directional, prototype/evaluation-only map (15 reviewed phrases, synonym
cohort only, reviewed by the implementing engineer only). Its numbers are attribute coverage of query wording, **not**
embedding quality; the alias map is not production vocabulary, and it changes no threshold, gold set or release flag.
A provider still has to pass the semantic gates on its own merits.

## Candidate

| Field | Value |
|---|---|
| Date / operator | |
| Repo commit | |
| Provider / model | |
| Output dimension | |
| Fixture sha256 (must equal `embedding_thresholds.yaml`) | |
| Thresholds file sha256 | |

## Preconditions (all must be true before a live run)

- [ ] Recorded run exits 3 with `semantic_metrics=NOT_EVALUATED` and no failed gates
- [ ] Provider and model approved by the owner and listed in `EMBEDDING_EVAL_ALLOWED_MODELS`; credential is `EMBEDDING_EVAL_<PROVIDER>_API_KEY` only
- [ ] Clean shell: no `DATABASE_URL`, `REDIS_URL`, `ADMIN_API_KEY`, `INTERNAL_API_TOKEN` or `SESSION_SIGNING_KEY` set
- [ ] Price per million tokens taken from the provider's current price page: ______ (source and date: ______)
- [ ] Cost ceiling (≤ $2), request cap (≤ 32), batch (≤ 16), input (≤ 256 chars), timeout (≤ 20 s), repeats (2–3) chosen

## Command (secrets not recorded)

```
EMBEDDING_EVAL_LIVE=1 python evals/run_embedding_eval.py --synthetic-only --live --no-fallback \
  --provider <p> --model <m> --dimension <d> --batch-size 16 --timeout 20 --max-input-chars 256 \
  --repeats 3 --max-requests 32 --max-cost-usd 2 --usd-per-million-tokens <price> --report <path outside the repo>
```

## Outcome

One of: `unsupported` · `blocked_by_policy` · `failed_validation` · `failed_budget_or_timeout` · `failed_quality` · `passed`

Outcome: ______  Exit code: ______  Error codes: ______

## Results (aggregate only)

| Metric | Overall | en | ur | roman_ur | synonym | Gate (overall / cohort) |
|---|---|---|---|---|---|---|
| Recall@10 | | | | | | ≥ 0.85 / ≥ 0.80 |
| MRR@10 | | | | | | ≥ 0.70 / ≥ 0.60 |
| nDCG@10 | | | | | | ≥ 0.75 / ≥ 0.65 |

| Check | Result | Gate |
|---|---|---|
| Hard-constraint violations (16 queries) | | 0 |
| Unconstrained ranking would have violated (informational) | | — |
| Vector count / finite / stable dimension | | 100% |
| Missing / stale records ranked | | 0 |
| Coverage: scored / missing / stale of 96 | | reported only |
| Repeat top-10 Jaccard | | ≥ 0.99 |
| Requests / transport retries | | ≤ 32 / ≤ 1 per request |
| Estimated tokens / estimated cost | | ≤ $2 (estimate, chars/4, not billed usage) |
| Latency total / mean / max (ms) | | recorded |
| Fallback used | | none, ever |

## Review

- [ ] Report holds only aggregates and `SYN-` case IDs: no input text, vectors, provider responses, URLs or keys
- [ ] No raw artifact, vector file or provider response committed
- [ ] Billed usage from the provider dashboard (if available): ______
- [ ] Reviewer / decision / date: ______

A `passed` outcome is one input to a later, separate decision. Record that decision elsewhere.
