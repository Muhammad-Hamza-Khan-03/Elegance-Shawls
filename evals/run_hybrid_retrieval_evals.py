"""Phase 1 hybrid retrieval fixture check (offline, deterministic, no model, no network, no database).

  python evals/run_hybrid_retrieval_evals.py [--json out.json]     # from the repo root

S4a has no embeddings yet, so this checks only the dataset and fixture integrity and that catalogue text
representations stay free of private, price and stock data. Semantic metrics (recall@k, MRR) are reported as
NOT_EVALUATED and release_ready is always false. Separate from run_retrieval_evals.py and run_evals.py.
Exit codes: 0 integrity passed (semantic quality still NOT_EVALUATED), 1 integrity failed, 2 dataset missing or empty.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "apps" / "backend"))

from search.representations import product_representation, variant_representation  # noqa: E402

SCOPE = "store-a"
LANGUAGES = {"en", "ur", "roman_ur"}


def _attrs(rows: list[dict]) -> list[SimpleNamespace]:
    return [SimpleNamespace(**row) for row in rows]


def representations(product: dict) -> list[str]:
    texts = [product_representation(product["name"], product["category"], product["material"], product["description"],
                                    _attrs(product["attributes"])).text]
    texts += [variant_representation(product["name"], v["name"], v["color"], product["category"], product["material"],
                                     _attrs(v["attributes"])).text for v in product["variants"]]
    return texts


def leaks(product: dict, text: str) -> list[str]:
    """Private, staged, id, sku, price and stock values of a product that appear in its embedded text."""
    secrets = [product["private_note"], product.get("staged_suggestion"), product["id"]]
    for v in product["variants"]:
        secrets += [v["sku"], str(v["price"]), str(v["stock"]), v["id"]]
    tokens = set(re.findall(r"\w+", text.lower()))
    # Multi-word values match as substrings; single tokens (numbers, ids) as whole words so "0" is not found inside "10".
    return [s for s in secrets if s and (s.lower() in text.lower() if " " in s else s.lower() in tokens)]


def check(cases: list[dict], products: list[dict]) -> list[str]:
    errors = []
    by_id = {p["id"]: p for p in products}
    eligible = {p["id"] for p in products if p["status"] == "active" and p["scope"] == SCOPE}
    for case in cases:
        for pid in case["relevant_ids"]:
            if pid not in eligible:
                errors.append(f"{case['id']}: relevant {pid} is not an active in-scope product")
        for pid in case["decoy_ids"]:
            if pid not in by_id or pid in eligible:
                errors.append(f"{case['id']}: decoy {pid} must exist and be draft, archived or out of scope")
    if {c["lang"] for c in cases} != LANGUAGES:
        errors.append(f"dataset must cover exactly {sorted(LANGUAGES)}")
    for product in products:
        for text in representations(product):
            errors += [f"{product['id']}: {s!r} leaked into text" for s in leaks(product, text)]
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    path = args.root / "datasets" / "retrieval_hybrid.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
    if not cases:
        print("retrieval_hybrid  NOT_EVALUATED  n=0 (missing or empty dataset)")
        return 2
    errors = check(cases, json.loads((args.root / "fixtures" / "hybrid_catalogue.json").read_text(encoding="utf-8")))
    result = {"gate": "retrieval_hybrid", "scope": "fixture integrity only; no embeddings exist yet", "examples": len(cases),
              "fixture_integrity": "fail" if errors else "pass", "errors": errors, "release_ready": False,
              "semantic_metrics": {"recall_at_10": None, "mrr": None, "status": "NOT_EVALUATED"}}
    print(f"retrieval_hybrid  fixture_integrity={result['fixture_integrity'].upper()}  n={len(cases)}  "
          "semantic_metrics=NOT_EVALUATED  release_ready=false")
    for error in errors:
        print("    -", error)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
