# Synthetic embedding benchmark v2 — review record

v2 is **reviewed but not yet model-evaluated**. No provider, network or API call was made to build it. It does not set
`release_ready` or any other release flag, and it is not a QA claim.

| Field | Value |
|---|---|
| v1 (immutable, unchanged) | `evals/datasets/embedding_synthetic.jsonl`, sha256 `c5382437d5bad1ee823b9286fe163e4bc69b11162bdcbdb152ba4b283ab78b96`, thresholds `evals/embedding_thresholds.yaml` |
| v2 | `evals/datasets/embedding_synthetic_v2.jsonl`, sha256 `a8511afd90b58e0bb82d4c15de5081ab20de92268c0449138f9610fbf054bdac`, thresholds `evals/embedding_thresholds_v2.yaml` |
| Reviewer | Hamza (no external reviewer) |
| Review date | 2026-10-30 |
| Process | Four batches covering all 16 original synonym queries |
| Scope | The 16 synonym-cohort queries only. The en, ur and roman_ur cohorts (48 queries) were **not** part of this review and are copied byte-identical from v1; the Urdu/Roman Urdu text is still unreviewed by a native speaker. |

## What is unchanged

All 96 records (IDs, text, missing/stale states, fictional-only content) and all 48 en/ur/roman_ur queries are
byte-identical to v1. Only the 16 synonym rows differ; the file keeps the same row count (161).

## Review decisions applied

- Descriptive properties do not imply a material: smooth/lustrous ≠ silk; breathable/lightweight ≠ cotton; goat-hair/soft ≠ pashmina.
- fringe ≠ tasselled. Human correction: explicit "fringed edges" maps to `edge_finish=fringed`, not `motif=tasselled`. The 96-record corpus has no `edge_finish` attribute and none was added, so the fringed queries (Q038, Q040, Q042) are excluded.
- "neck piece", "shoulder cover", "blanket-style cover" and "long neck drape" do not establish a category, so no category label or constraint is kept.
- "ready to ship now" is dispatch-readiness wording, not necessarily `in_stock`, so the stock constraint is dropped.
- Q063 "small" is ambiguous between size and pattern; no size constraint is imposed.
- Explicit wool, floral, checked, geometric and striped wording was kept as supported.

## The 16 queries

Scored (5, `kind: query`; gold recomputed from record metadata, ≤ 10 per query):

| ID | v2 text | Labels |
|---|---|---|
| SYN-Q041 | checked design | checked |
| SYN-Q047 | floral pattern in wool | floral, wool |
| SYN-Q056 | something in grey, large size | constraints only: grey + large, same variant (the original's cotton/shawl labels dropped) |
| SYN-Q059 | geometric pattern | geometric (stock constraint dropped) |
| SYN-Q063 | woollen with a geometric pattern | wool, geometric (size constraint dropped) |

Excluded from scoring (11, `kind: excluded_query`, no gold; the file keeps the revised text and reason):

| ID | Reason |
|---|---|
| SYN-Q037 | only floral supported; 11 current records match, above the top-10 gold cap |
| SYN-Q038 | reviewed attribute edge_finish=fringed is outside the current v2 corpus/schema; no supported scored gold set |
| SYN-Q039 | paisley was not among the mappings marked supported |
| SYN-Q040 | edge_finish=fringed (plus material=wool) is outside the current v2 corpus/schema; no supported scored gold set |
| SYN-Q042 | long neck drape is not a category; remaining edge_finish=fringed is outside the corpus/schema |
| SYN-Q043 | duplicates SYN-Q041 once the unsupported category is removed |
| SYN-Q044 | no supported attribute remains |
| SYN-Q045 | no supported attribute remains |
| SYN-Q046 | wool alone matches 28 records, above the top-10 gold cap |
| SYN-Q048 | striped alone matches 18 records, above the top-10 gold cap |
| SYN-Q052 | striped alone matches 18 records; the scarf category constraint was unsupported |

## Limitations

- The synonym cohort shrinks from 16 to 5 scored queries; per-cohort metrics there are coarse. Total scored queries: 53 (v1: 64).
- Hard-constraint queries drop from 16 to 13 (still all 8 constraint types, via the other cohorts).
- `embedding_thresholds_v2.yaml` keeps every metric, constraint, vector, exclusion, fallback, reproducibility and bounds
  value identical to v1. Only the fixture section differs (path, sha256, query counts, per-cohort counts, hard-constraint
  minimum) because the fixture itself changed.
- `evals/run_embedding_eval.py` now accepts `queries_per_cohort` as a scalar (v1) or a per-cohort mapping (v2); no metric threshold or
  gate was changed. v2 is run with `--thresholds evals/embedding_thresholds_v2.yaml`. It has not been run against any model.
- Wording of Q041, Q047, Q056, Q059 and Q063 and the Q038/Q040 correction were confirmed by Hamza after QA; exclusion reasons are the implementer's.
- No external reviewer, no native-speaker review, no model evaluation.
