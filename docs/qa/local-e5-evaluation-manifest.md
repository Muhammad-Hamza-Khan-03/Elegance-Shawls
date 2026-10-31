# Local multilingual-e5 evaluation manifest (redacted)

Evidence for one local, offline run of the synthetic embedding gate. It is not independent QA, not semantic-quality sign-off, and changes no release flag (`release_ready` stays false in the report).

| Item | Value |
|---|---|
| Model | `intfloat/multilingual-e5-base` (the only name `local_e5` accepts) |
| Snapshot path pattern | A curated local runtime directory containing the PyTorch/Sentence-Transformers files listed below; the directory is passed as `--local-model-path` |
| Hugging Face source revision | `d128750597153bb5987e10b1c3493a34e5a4502a` (`intfloat/multilingual-e5-base`) |
| Runtime file boundary | `config.json`, `.gitattributes`, `modules.json`, `model.safetensors`, `README.md`, `sentence_bert_config.json`, `sentencepiece.bpe.model`, `special_tokens_map.json`, `tokenizer_config.json`, `tokenizer.json`, `1_Pooling/config.json` |
| Model revision (sha256 tree digest) | `f6f46ac9f90d7b301eae789de47f616dfd84bac4cf645ef784503e4056fa3781` |
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
  --local-model-path <snapshot dir> --local-model-revision f6f46ac9f90d7b301eae789de47f616dfd84bac4cf645ef784503e4056fa3781 \
  --batch-size 16 --timeout 20 --max-input-chars 256 --repeats 3 --max-requests 32 --report <path outside the repo>
```

The `--repeats 3` value is read from the report (`reproducibility.repeats`); the other flag values follow the template and are not recorded in the report.

## v2 report (kept outside the repo)

- Path: `/tmp/option-b-live-diagnostic.json`
- sha256: `905acbae9e9cdd33f683a7167428713c0c7066a60fe38f1805155efa0dc647ba`
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

This tree is stacked on commit `24346e8` and includes the v2 fixture and v2 thresholds. The live report was reproduced with the curated local runtime snapshot described above; the snapshot itself remains external to the repository and must be provisioned on each evaluation machine.

- The snapshot source is Hugging Face revision `d128750597153bb5987e10b1c3493a34e5a4502a`; only the runtime file boundary listed above is included in the digest.
- Needed: `EMBEDDING_EVAL_LIVE=1`, the snapshot directory (`--local-model-path` or `EMBEDDING_EVAL_LOCAL_MODEL_PATH`), and the model-tree revision `f6f46ac9f90d7b301eae789de47f616dfd84bac4cf645ef784503e4056fa3781` (`--local-model-revision` or `EMBEDDING_EVAL_LOCAL_MODEL_REVISION`). The loader recomputes the digest and refuses a mismatch.
- Run the command above with `--thresholds evals/embedding_thresholds_v2.yaml`. The fixture comes from that file; the v1 fixture and thresholds (`c5382437d5bad1ee823b9286fe163e4bc69b11162bdcbdb152ba4b283ab78b96`, 64 queries) are unchanged and would give a v1 result.
- The revision is a tree digest, not an upstream Hugging Face commit hash.
- `release_ready` stays false.
