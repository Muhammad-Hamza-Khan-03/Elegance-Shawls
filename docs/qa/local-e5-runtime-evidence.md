# Local E5 runtime and image evidence (#136/#137)

This record supplements the implementation and lock evidence for the exact QA image
`qa-elegance-136-137:1d22d73`. It is local evidence only; it does not activate E5,
run a production backfill, or change the #134 defaults.

## Runtime measurement

The successful bounded measurement used the QA image with MLflow stopped temporarily
to avoid local memory pressure. It ran offline against synthetic passages, with no database connection and no real database backfill:

```text
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python scripts/e5_measure.py <model_dir> --rows 500 --batch 16
```

The host had `MemTotal=3838861312` bytes (about 3.84 GB). The measured JSON artifact
is `/home/hamza/llmops/elegance-llmops/evidence/e5-runtime-qa-image-1d22d73.json`.
The recorded values are:

| Measurement | Value |
|---|---:|
| Model load | 7.1 s |
| RSS before load | 33.3 MB |
| RSS after load | 848.1 MB |
| Peak RSS | 1143.6 MB |
| First single-text embedding | 0.188 s |
| Second single-text embedding | 0.092 s |
| Best batch time (`batch=16`) | 0.737 s |
| Per-row batch time | 0.0461 s |
| Linear projection for 500 rows | 23.0 s |

`23.0 s` is a linear projection from the measured batch throughput, not a measured
backfill duration. In particular, it is not evidence that 500 database rows were
read or written. No real database backfill measurement is claimed here.

The thread controls, row count and batch size are part of the evidence and must be
reported with comparisons: `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `rows=500`, and
`batch=16`. These figures are local, CPU-only measurements and are not a production
capacity guarantee. MLflow was restarted afterward and `/health` returned HTTP 200.

## Image-size comparison

The before/after pair was inspected by image identity, not inferred from a build log:

| Image | Size (bytes) |
|---|---:|
| `elegance-e5-eval:61ed0e3e` (before) | 5,734,203,017 |
| `qa-elegance-136-137:1d22d73` (after) | 5,738,687,310 |
| Delta | +4,484,293 bytes (+4.277 MiB) |

The after image is the exact QA image used for the runtime measurement above.

## Limitations and operational recommendation

- The measurement was made with MLflow stopped because the local Docker host was
  memory-constrained. It therefore does not demonstrate coexistence with MLflow or
  a shared-host production workload.
- The model load and embedding timings are measured; the 500-row backfill number is
  projected only. The run used synthetic passages and no database.
- The model remains lazy and local-only. The safe defaults remain
  `RUN_E5_BACKFILL_ON_STARTUP=false`, `EMBEDDING_ENABLED=false`, and
  `LOCAL_SEMANTIC_SEARCH_ENABLED=false`.
- No worker split is implemented by #136/#137. If a future bounded measurement shows
  model load plus backfill can exceed the 180-second health-check start period, or
  model RSS is a large share of the container limit, run embedding/backfill in a
  separate worker container. This is an operational recommendation, not a measured
  result from this change, and keeps API readiness and memory independent of E5.
