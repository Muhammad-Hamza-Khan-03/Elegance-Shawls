"""Evaluation runner. Usage (from the repo root):

  python evals/run_evals.py                  # recorded responses, no network or LLM quota
  python evals/run_evals.py --release-ready  # also fail while any suite is "not evaluated"
  python evals/run_evals.py --json out.json

Statuses: pass | fail | not_evaluated. A missing or empty dataset is "not evaluated", and so is a
suite whose recorded responses are not genuine model output (provenance other than "model", for
example the reference-copy "fixture" rows): the metrics still run as a harness check and can fail,
but they never count as evidence. "Not evaluated" does not fail an ordinary pull request, but it
always blocks AI release readiness (--release-ready).
Exit codes: 0 ok, 1 a threshold failed, 2 usage/live mode unavailable, 3 not release-ready.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(filters: dict) -> dict:
    return {k: sorted(v) if isinstance(v, list) else v for k, v in filters.items() if v not in (None, [], "")}


def _pairs(filters: dict) -> set[tuple[str, str]]:
    out = set()
    for key, value in _norm(filters).items():
        for item in value if isinstance(value, list) else [value]:
            out.add((key, json.dumps(item)))
    return out


def filter_parsing_metrics(examples: list[dict], responses: dict[str, dict]) -> dict[str, float]:
    exact = tp = predicted = expected_total = 0
    for example in examples:
        expected, got = example["expected"], responses.get(example["id"], {})
        exact += _norm(expected) == _norm(got)
        e, g = _pairs(expected), _pairs(got)
        tp, predicted, expected_total = tp + len(e & g), predicted + len(g), expected_total + len(e)
    return {
        "exact_match": exact / len(examples),
        # With nothing to predict (or nothing predicted) the vacuous value is 1.0, never a crash.
        "constraint_precision": tp / predicted if predicted else 1.0,
        "constraint_recall": tp / expected_total if expected_total else 1.0,
    }


SCORERS = {"filter_parsing": filter_parsing_metrics}


def _check(metrics: dict[str, float], limits: dict) -> list[str]:
    failures = []
    for name, limit in limits.items():
        value = metrics.get(name)
        if value is None:
            failures.append(f"{name}: not produced")
        elif "min" in limit and value < limit["min"]:
            failures.append(f"{name}={value:.3f} < min {limit['min']}")
        elif "max" in limit and value > limit["max"]:
            failures.append(f"{name}={value:.3f} > max {limit['max']}")
    return failures


def evaluate(root: Path, thresholds: dict) -> list[dict]:
    results = []
    for name, suite in thresholds["suites"].items():
        examples = load_jsonl(root / suite["dataset"])
        if not examples:
            results.append({"suite": name, "status": "not_evaluated", "examples": 0, "metrics": {}, "failures": []})
            continue
        if name not in SCORERS:
            results.append({"suite": name, "status": "not_evaluated", "examples": len(examples), "metrics": {},
                            "failures": ["no scorer implemented for this suite"]})
            continue
        recorded = load_jsonl(root / "recorded" / f"{name}.jsonl")
        responses = {r["id"]: r["response"] for r in recorded}
        metrics = SCORERS[name](examples, responses)
        failures = _check(metrics, suite["metrics"])
        genuine = bool(recorded) and all(r.get("provenance") == "model" for r in recorded)
        status = "fail" if failures else "pass" if genuine else "not_evaluated"
        if status == "not_evaluated":
            failures = ["recorded responses are fixtures, not model output (harness check only)"]
        results.append({"suite": name, "status": status, "examples": len(examples),
                        "metrics": metrics, "failures": failures})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--mode", choices=["recorded", "live"], default="recorded")
    parser.add_argument("--release-ready", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "live":
        print("live mode is not available yet: no parser prompt exists. Pull requests use recorded responses.")
        return 2
    thresholds = yaml.safe_load((args.thresholds or args.root / "thresholds.yaml").read_text(encoding="utf-8"))
    results = evaluate(args.root, thresholds)
    for r in results:
        detail = ", ".join(f"{k}={v:.3f}" for k, v in r["metrics"].items()) or "-"
        print(f"{r['suite']:<22} {r['status'].upper():<14} n={r['examples']:<4} {detail}")
        for failure in r["failures"]:
            print(f"    - {failure}")
    not_evaluated = [r["suite"] for r in results if r["status"] == "not_evaluated"]
    failed = [r["suite"] for r in results if r["status"] == "fail"]
    release_ready = not failed and not not_evaluated
    print(f"\nrelease_ready={str(release_ready).lower()}"
          + (f" (not evaluated: {', '.join(not_evaluated)})" if not_evaluated else ""))
    if args.json:
        args.json.write_text(json.dumps({"release_ready": release_ready, "suites": results}, indent=2), encoding="utf-8")
    if failed:
        return 1
    return 3 if args.release_ready and not_evaluated else 0


if __name__ == "__main__":
    sys.exit(main())
