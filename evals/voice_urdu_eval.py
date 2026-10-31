"""Offline M5-S1 voice evaluation gate.

Usage: python evals/voice_urdu_eval.py [--release-ready]
The only score is the mean of exact PKR-price and exact negation correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "apps" / "backend"
sys.path.insert(0, str(BACKEND))
from voice.evaluation import evaluate_cases, release_gate  # noqa: E402

DATASET = HERE / "datasets" / "voice_urdu.jsonl"
CHECKSUM = HERE / "datasets" / "voice_urdu.sha256"


def load() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-ready", action="store_true")
    args = parser.parse_args(argv)
    rows = load() if DATASET.is_file() else []
    expected = CHECKSUM.read_text(encoding="utf-8").split()[0] if CHECKSUM.is_file() else ""
    actual = hashlib.sha256(DATASET.read_bytes()).hexdigest() if DATASET.is_file() else ""
    if not rows or expected != actual:
        print("voice_urdu BLOCKED: empty or checksum mismatch")
        return 3 if args.release_ready else 1
    result = evaluate_cases(rows)
    gate = release_gate([{"reviewed": row.get("reviewed"), "passed": result.passed} for row in rows])
    print(f"voice_urdu {result.score:.3f} price={result.price_accuracy:.3f} negation={result.negation_accuracy:.3f} n={result.examples}")
    print(f"release_ready={str(gate.ready).lower()} reason={gate.reason}")
    return 0 if gate.ready else (3 if args.release_ready else 1)


if __name__ == "__main__":
    raise SystemExit(main())
