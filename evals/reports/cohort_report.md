# Retrieval cohort report (generated; do not edit)

> **Synthetic, unreviewed data.** Engineering signal for choosing cutoffs and finding weak cohorts, **not** evidence of real-world
> accuracy and **not** release evidence. No real customer query is in the data. `release_ready` is unaffected by this report.

## Provenance

- dataset `datasets/roman_urdu_queries.jsonl` sha256 `f7783379728434359ddd3eae9818659405ff9662c6f048b308481ca8e596bb78`
- origin `synthetic_generator`, review `unreviewed`, split `mixed` (rows carry a `heldout` field)
- 310 rows are written by evals/make_roman_urdu_queries.py from vocabulary tables that overlap the production parser (circular); 52 rows carry heldout (true = 32, "v3" = 20) and are hand-written phrasing by the same author. All rows are synthetic and reviewed=false. No real customer query is included.
- low-n threshold: fewer than 30 scored queries
- results: the RECORDED local-E5 run in `evals/roman_urdu_results.json` (sha256 `e4ac0915a04f0be3b5febc3296f40fee0e8ef6c2e875e96bbc9a550597ceb3ba`). The E5 weights are not in the repository, so these numbers are quoted, not reproduced, by this report.

## Vocabulary circularity (computed from the dataset now)

| cohort | dataset rows | fully in generator/production vocabulary | token coverage | verdict |
|---|---|---|---|---|
| en | 52 | 44 (85%) | 0.86 | circular |
| roman_ur | 198 | 160 (81%) | 0.88 | circular |
| ur | 71 | 64 (90%) | 0.92 | circular |
| mixed | 41 | 41 (100%) | 1.00 | circular |
| ALL | 310 | 290 (94%) | 0.95 | circular |
| HELDOUT | 32 | 18 (56%) | 0.81 | circular |
| HELDOUT_V3 | 20 | 1 (5%) | 0.55 | partly independent of the vocabulary |

## Scores by cohort (recorded run)

Roman Urdu (`roman_ur`), Urdu (`ur`), English (`en`) and mixed cohorts are listed separately; HELDOUT cohorts are separate again.

| system | cohort | n | metric | estimate | 95% interval (Hoeffding) | flags |
|---|---|---|---|---|---|---|
| keyword | en | 42 | recall@10 | 0.891 | 0.68 to 1.00 | circular |
| keyword | en | 42 | MRR@10 | 0.905 | 0.70 to 1.00 | circular |
| keyword | roman_ur | 185 | recall@10 | 0.780 | 0.68 to 0.88 | circular |
| keyword | roman_ur | 185 | MRR@10 | 0.811 | 0.71 to 0.91 | circular |
| keyword | ur | 67 | recall@10 | 0.908 | 0.74 to 1.00 | circular |
| keyword | ur | 67 | MRR@10 | 0.940 | 0.77 to 1.00 | circular |
| keyword | mixed | 41 | recall@10 | 0.894 | 0.68 to 1.00 | circular |
| keyword | mixed | 41 | MRR@10 | 0.951 | 0.74 to 1.00 | circular |
| keyword | ALL | 283 | recall@10 | 0.894 | 0.81 to 0.97 | circular |
| keyword | ALL | 283 | MRR@10 | 0.929 | 0.85 to 1.00 | circular |
| keyword | HELDOUT | 32 | recall@10 | 0.570 | 0.33 to 0.81 | circular; held-out but synthetic, same-author phrasing |
| keyword | HELDOUT | 32 | MRR@10 | 0.594 | 0.35 to 0.83 | circular; held-out but synthetic, same-author phrasing |
| keyword | HELDOUT_V3 | 20 | recall@10 | 0.400 | 0.10 to 0.70 | LOW-N (n<30); held-out but synthetic, same-author phrasing |
| keyword | HELDOUT_V3 | 20 | MRR@10 | 0.400 | 0.10 to 0.70 | LOW-N (n<30); held-out but synthetic, same-author phrasing |
| pipeline | en | 42 | recall@10 | 0.857 | 0.65 to 1.00 | circular |
| pipeline | en | 42 | MRR@10 | 0.857 | 0.65 to 1.00 | circular |
| pipeline | roman_ur | 185 | recall@10 | 0.936 | 0.84 to 1.00 | circular |
| pipeline | roman_ur | 185 | MRR@10 | 0.932 | 0.83 to 1.00 | circular |
| pipeline | ur | 67 | recall@10 | 0.955 | 0.79 to 1.00 | circular |
| pipeline | ur | 67 | MRR@10 | 0.955 | 0.79 to 1.00 | circular |
| pipeline | mixed | 41 | recall@10 | 0.983 | 0.77 to 1.00 | circular |
| pipeline | mixed | 41 | MRR@10 | 0.980 | 0.77 to 1.00 | circular |
| pipeline | ALL | 283 | recall@10 | 0.939 | 0.86 to 1.00 | circular |
| pipeline | ALL | 283 | MRR@10 | 0.936 | 0.86 to 1.00 | circular |
| pipeline | HELDOUT | 32 | recall@10 | 0.940 | 0.70 to 1.00 | circular; held-out but synthetic, same-author phrasing |
| pipeline | HELDOUT | 32 | MRR@10 | 0.944 | 0.70 to 1.00 | circular; held-out but synthetic, same-author phrasing |
| pipeline | HELDOUT_V3 | 20 | recall@10 | 0.885 | 0.58 to 1.00 | LOW-N (n<30); held-out but synthetic, same-author phrasing |
| pipeline | HELDOUT_V3 | 20 | MRR@10 | 0.874 | 0.57 to 1.00 | LOW-N (n<30); held-out but synthetic, same-author phrasing |
| raw E5 | en | 42 | recall@10 | 0.950 | 0.74 to 1.00 | circular |
| raw E5 | en | 42 | MRR@10 | 0.988 | 0.78 to 1.00 | circular |
| raw E5 | roman_ur | 185 | recall@10 | 0.568 | 0.47 to 0.67 | circular |
| raw E5 | roman_ur | 185 | MRR@10 | 0.710 | 0.61 to 0.81 | circular |
| raw E5 | ur | 67 | recall@10 | 0.688 | 0.52 to 0.85 | circular |
| raw E5 | ur | 67 | MRR@10 | 0.815 | 0.65 to 0.98 | circular |
| raw E5 | mixed | 41 | recall@10 | 0.434 | 0.22 to 0.65 | circular |
| raw E5 | mixed | 41 | MRR@10 | 0.665 | 0.45 to 0.88 | circular |
| raw E5 | ALL | 283 | recall@10 | 0.618 | 0.54 to 0.70 | circular |
| raw E5 | ALL | 283 | MRR@10 | 0.752 | 0.67 to 0.83 | circular |
| raw E5 | HELDOUT | 32 | recall@10 | 0.618 | 0.38 to 0.86 | circular; held-out but synthetic, same-author phrasing |
| raw E5 | HELDOUT | 32 | MRR@10 | 0.812 | 0.57 to 1.00 | circular; held-out but synthetic, same-author phrasing |
| raw E5 | HELDOUT_V3 | 20 | recall@10 | 0.720 | 0.42 to 1.00 | LOW-N (n<30); held-out but synthetic, same-author phrasing |
| raw E5 | HELDOUT_V3 | 20 | MRR@10 | 0.800 | 0.50 to 1.00 | LOW-N (n<30); held-out but synthetic, same-author phrasing |

## Synonym cohort (embedding fixture v2)

- 5 scored queries, which is below the low-n threshold of 30: **LOW-N, no interval is meaningful at this size.**
- review `owner_statement_unsigned`: the 16 original synonym-cohort queries only (5 scored, 11 excluded), as recorded in the file's own provenance block. The en, ur and roman_ur cohorts of this file were NOT reviewed. No external reviewer, no signed record.
- no per-query results for this cohort are committed (the recorded run lives outside the repository, referenced by SHA-256 in `docs/qa/local-e5-evaluation-manifest.md`), so no score is reported here.

## Not covered

- No human-reviewed (signed) dataset exists for Urdu or Roman Urdu; no qualified independent reviewer has been identified.
- No real, privacy-scrubbed customer queries exist; collection is recorded as BLOCKED in `evals/real_queries_status.md`.
- Per-query values are not committed, so Wilson and bootstrap intervals are not available for recall@10 and MRR@10.

Regenerate: `python evals/report.py --write`; verify offline: `python evals/report.py --check`.
