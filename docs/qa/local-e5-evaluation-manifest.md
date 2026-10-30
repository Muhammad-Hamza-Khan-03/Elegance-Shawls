# Local multilingual-e5 evaluation manifest (redacted)

Evidence for one local, offline run of the synthetic embedding gate. It is not independent QA, not semantic-quality sign-off, and changes no release flag (`release_ready` stays false in the report).

| Item | Value |
|---|---|
| Model | `intfloat/multilingual-e5-base` (the only name `local_e5` accepts) |
| Snapshot path pattern | `<hf-cache>/models--intfloat--multilingual-e5-base/snapshots/<upstream-commit>` (the directory passed as `--local-model-path`) |
| Model revision (sha256 tree digest) | `3d11724217c5941fba4a83d1ec0b9baa8dacb07fb7985c56b987188324d0107d` |
| Dimension | 768 |
| Runtime | CPU only, `local_files_only`, `HF_HUB_OFFLINE=1`, outbound sockets blocked while loading and encoding, no hosted fallback |
| Provider allowlist | `local_e5` is selected by `--provider local_e5`; any other model name, dimension or revision is refused |

The revision is a digest of the files on the evaluation machine (`python -m embeddings.providers.local_e5 <model dir>`), recomputed on every load. It is not an upstream Hugging Face commit hash; the upstream source of the weights is not recorded here.

## Command shape

All `EMBEDDING_EVAL_*_API_KEY` variables and app/database configuration must be unset (the runner refuses otherwise):

```
env -u EMBEDDING_EVAL_GEMINI_API_KEY -u EMBEDDING_EVAL_GROQ_API_KEY EMBEDDING_EVAL_LIVE=1 \
  python evals/run_embedding_eval.py --synthetic-only --live --no-fallback \
  --provider local_e5 --model intfloat/multilingual-e5-base \
  --local-model-path <snapshot dir> --local-model-revision 3d11724217c5941fba4a83d1ec0b9baa8dacb07fb7985c56b987188324d0107d \
  --batch-size 16 --timeout 20 --max-input-chars 256 --repeats 3 --max-requests 32 --report <path outside the repo>
```

The `--repeats 3` value is read from the report (`reproducibility.repeats`); the other flag values follow the template and are not recorded in the report.

## v2 report (kept outside the repo)

- Path: `/tmp/embedding-eval-local-e5-v2-20261030.json`
- sha256: `912f721fe47511993721308c96b3d361b60ca50d92ebe42df0f86845e3a0d0fa`
- Recorded: outcome `passed`, mode `live`, 96 records, 53 queries, 27 requests, top-10 Jaccard 1.0 over 3 repeats, no errors, `release_ready: false`, `release_flags_changed: false`, fallback not used.
- Fixture: `evals/datasets/embedding_synthetic_v2.jsonl`, sha256 `a8511afd90b58e0bb82d4c15de5081ab20de92268c0449138f9610fbf054bdac` (matches the report and this tree), 96 records, 53 queries, 13 hard-constraint queries. Thresholds: `evals/embedding_thresholds_v2.yaml`.
- Semantic metrics (report `semantic_metrics`), all gates `pass`:

| Cohort | Queries | recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|
| overall | 53 | 0.954 | 0.941 | 0.930 |
| en | 16 | 1.000 | 1.000 | 1.000 |
| ur | 16 | 0.969 | 0.969 | 0.954 |
| roman_ur | 16 | 0.892 | 0.836 | 0.822 |
| synonym | 5 | 0.960 | 1.000 | 0.974 |

Roman Urdu is the weakest cohort. The fixture is synthetic and user-reviewed; passing it is not production proof of retrieval quality.

## Reproducing the v2 report

This tree is stacked on commit `24346e8` and includes the v2 fixture and v2 thresholds, so the fixture and thresholds are no longer missing. The report is still **not reproducible without the local model snapshot**, which is external to the repository:

- The snapshot is a local directory of `intfloat/multilingual-e5-base` files. The current QA machine may not have it. No network access or download was attempted, so its presence and content were not checked here.
- Needed: `EMBEDDING_EVAL_LIVE=1`, the snapshot directory (`--local-model-path` or `EMBEDDING_EVAL_LOCAL_MODEL_PATH`), and the model-tree revision `3d11724217c5941fba4a83d1ec0b9baa8dacb07fb7985c56b987188324d0107d` (`--local-model-revision` or `EMBEDDING_EVAL_LOCAL_MODEL_REVISION`). The loader recomputes the digest and refuses a mismatch.
- Run the command above with `--thresholds evals/embedding_thresholds_v2.yaml`. The fixture comes from that file; the v1 fixture and thresholds (`c5382437d5bad1ee823b9286fe163e4bc69b11162bdcbdb152ba4b283ab78b96`, 64 queries) are unchanged and would give a v1 result.
- The revision is a tree digest, not an upstream Hugging Face commit hash.
- `release_ready` stays false.
