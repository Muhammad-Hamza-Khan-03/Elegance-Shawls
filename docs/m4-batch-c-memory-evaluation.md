# M4 Batch C memory-extraction evaluation

**Task:** `t_m4c_memory_extraction_evals`
**Artifact:** `evals/datasets/memory_extraction_synthetic.jsonl` + `evals/run_memory_extraction_eval.py`
**Mode:** deterministic offline synthetic proof; no provider, network, customer data, or database writes.

## Reproduce

From `apps/backend`'s parent repository root:

```bash
python evals/run_memory_extraction_eval.py --report /tmp/m4c-memory-eval.json
```

The report records `provider_calls=0`, `database_writes=0`, and always keeps `release_ready=false`. The fixture contains 12 reviewed synthetic cases across English, Urdu, and Roman Urdu, covering save, do-not-save, correction/save, sensitive-data refusal, and unsupported input (`not_evaluated` in the runner).

## Readiness interpretation

This proves the fixture, runner determinism, locale coverage, and fail-closed safety shape. It is not model-quality or production-memory approval. A future local/self-hosted model evaluation must preserve the same fixture contract, pin model files/revision, run offline with outbound sockets blocked, and record thresholds plus human review. Missing, partial, or `NOT_EVALUATED` evidence blocks promotion.

**Current result:** readiness artifact only; production memory remains blocked pending provider decision, model-backed evaluation, deletion proof, independent QA, and explicit owner approvals.
