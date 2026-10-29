"""Phase 1 retrieval / hard-constraint evaluation (offline, deterministic, no model, no network, no database).

  python evals/run_retrieval_evals.py [--json out.json]     # from the repo root

Runs the real parser and matcher (apps/backend/catalog) over a fixed catalogue fixture and checks
reference answers. This is a PHASE-SPECIFIC gate for the deterministic retrieval layer only. It is
not model evaluation and it deliberately does not touch run_evals.py / thresholds.yaml: the global
AI release_ready flag stays governed by that runner and remains false.
Exit codes: 0 gate passed, 1 gate failed, 2 dataset missing or empty (never a pass).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "apps" / "backend"))

from catalog.query import parse_query  # noqa: E402
from catalog.search import rank  # noqa: E402

GATE = {"hard_constraint_violations": ("max", 0), "recall": ("min", 1.0),
        "exact_match": ("min", 1.0), "filter_exact_match": ("min", 1.0)}


def load_catalogue(path: Path) -> list[SimpleNamespace]:
    products = []
    for raw in json.loads(path.read_text(encoding="utf-8")):
        variants = [SimpleNamespace(is_active=True, **v) for v in raw["variants"]]
        products.append(SimpleNamespace(
            id=raw["id"], name=raw["name"], category=raw["category"], status=raw["status"], material=raw["material"],
            main_description=raw["description"], item_number=raw["item_number"],
            created_at=datetime.fromisoformat(raw["created_at"]), variants=variants))
    return products


def run(cases: list[dict], products: list) -> dict:
    violations = exact = filters_ok = recalled = expected_total = 0
    failures = []
    for case in cases:
        parsed = parse_query(case["query"])
        got = [h.product.id for h in rank(parsed, products)]
        want = case["expected_ids"]
        violations += len(set(got) - set(want))
        recalled += len(set(got) & set(want))
        expected_total += len(want)
        ok_set = set(got) == set(want)
        ok_filters = bool(parsed.unsupported) == case["unsupported"] and (
            case["filters"] is None or parsed.filters() == case["filters"])
        exact += ok_set
        filters_ok += ok_filters
        if not (ok_set and ok_filters):
            failures.append({"id": case["id"], "query": case["query"], "got": sorted(got), "want": sorted(want),
                             "filters": parsed.filters(), "unsupported": list(parsed.unsupported)})
    n = len(cases)
    metrics = {"hard_constraint_violations": violations, "recall": recalled / expected_total if expected_total else 1.0,
               "exact_match": exact / n, "filter_exact_match": filters_ok / n}
    passed = all((metrics[k] <= v if kind == "max" else metrics[k] >= v) for k, (kind, v) in GATE.items())
    return {"gate": "retrieval_constraints", "scope": "deterministic parser + matcher; not model evaluation",
            "examples": n, "languages": sorted({c["lang"] for c in cases}), "metrics": metrics,
            "status": "pass" if passed and not failures else "fail", "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    path = args.root / "datasets" / "retrieval_constraints.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
    if not cases:
        print("retrieval_constraints  NOT_EVALUATED  n=0 (missing or empty dataset)")
        return 2
    result = run(cases, load_catalogue(args.root / "fixtures" / "retrieval_catalogue.json"))
    detail = ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in result["metrics"].items())
    print(f"{result['gate']:<22} {result['status'].upper():<14} n={result['examples']:<4} {detail}")
    for failure in result["failures"]:
        print("    -", json.dumps(failure, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
