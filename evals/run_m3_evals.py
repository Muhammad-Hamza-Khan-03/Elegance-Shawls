"""M3 assistant evals. Usage (repo root): python evals/run_m3_evals.py

Runs each case through assistant.stream.propose (registry gate + action kernel). Statuses: PASS | FAIL | NOT_EVALUATED
(missing or empty dataset). Exit 1 on FAIL. It prints no release_ready and never changes run_evals.py's.
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "apps" / "backend"))
from assistant.stream import propose  # noqa: E402
from actions.kernel import InMemoryLedger  # noqa: E402


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_case(case: dict) -> list[str]:
    call = {"name": case["tool"], "input": case["input"], "action_id": f"act_{case['id']:0<16}"}
    for k in ("constraints", "confirmation"):
        if k in case:
            call[k] = case[k]
    out = propose(call, "sess_eval", InMemoryLedger(), 1_000_000.0)
    return [f"{case['id']}: {k}={out.get(k)!r}, expected {v!r}" for k, v in case["expect"].items() if out.get(k) != v]


def evaluate(root: Path = HERE) -> list[dict]:
    manifest = yaml.safe_load((root / "m3_manifest.yaml").read_text(encoding="utf-8"))
    results = []
    for name, suite in manifest["suites"].items():
        cases = load(root / suite["dataset"])
        failures = [f for c in cases for f in run_case(c)]
        status = "NOT_EVALUATED" if not cases else "FAIL" if failures else "PASS"
        results.append({"suite": name, "status": status, "examples": len(cases), "failures": failures})
    return results


def main() -> int:
    results = evaluate()
    for r in results:
        print(f"{r['suite']:<22} {r['status']:<14} n={r['examples']}")
        for f in r["failures"]:
            print(f"    - {f}")
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
