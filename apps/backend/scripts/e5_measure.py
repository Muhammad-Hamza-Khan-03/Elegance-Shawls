"""Reproducible local E5 cost measurement: model load, memory, first/subsequent embedding latency, backfill projection.

Run inside the E5 image or an env with the lock installed, against a model dir (scripts/fetch_e5_model.py):
  python scripts/e5_measure.py /opt/e5-model [--rows 500] [--batch 32]
Prints JSON. Offline, read-only, synthetic passages; it does not touch the database. The backfill figure is a linear
projection from the measured batch throughput (rows x seconds/row), not a database run.
"""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from embeddings.providers.local_e5 import _load_model  # noqa: E402


def positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return n


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # peak RSS, Linux reports KiB


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("--rows", type=positive_int, default=500, help="backfill size to project (the Dockerfile uses --limit 500)")
    ap.add_argument("--batch", type=positive_int, default=32)
    return ap


def main() -> None:
    a = build_parser().parse_args()
    texts = [f"passage: Embroidered pashmina shawl number {i}, wool blend, colour burgundy, winter wear" for i in range(a.batch)]
    out = {"rss_mb_before_load": round(rss_mb(), 1)}
    t = time.perf_counter(); model = _load_model(a.model_dir, None); out["load_s"] = round(time.perf_counter() - t, 2)
    out["rss_mb_after_load"] = round(rss_mb(), 1)
    t = time.perf_counter(); model.encode(texts[:1]); out["first_embed_single_s"] = round(time.perf_counter() - t, 3)
    t = time.perf_counter(); model.encode(texts[:1]); out["second_embed_single_s"] = round(time.perf_counter() - t, 3)
    runs = []
    for _ in range(3):
        t = time.perf_counter(); model.encode(texts, batch_size=a.batch); runs.append(time.perf_counter() - t)
    per_row = min(runs) / a.batch
    out.update(batch=a.batch, batch_best_s=round(min(runs), 3), per_row_s=round(per_row, 4),
               projected_backfill_s={str(a.rows): round(per_row * a.rows, 1)}, rss_mb_peak=round(rss_mb(), 1))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
