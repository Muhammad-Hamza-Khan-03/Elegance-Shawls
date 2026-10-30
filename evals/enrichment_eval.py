"""Synthetic-only evaluation gate for staff enrichment suggestions (M2-S5). No network, no production data.

  python evals/enrichment_eval.py [--dataset evals/synthetic/enrichment_suggestions.jsonl] [--release-ready]

Cases must be explicitly synthetic ("synthetic": true, ids prefixed "syn-"). The report is PASS only when the
cases are non-empty, every case is marked "reviewed": true by a human, the dataset matches the pinned sha256
sidecar (<dataset>.sha256), coverage is complete (all fields, all outcomes, photo and text sources) and every
threshold holds. Empty, unreviewed, unpinned or incomplete data is NOT_EVALUATED; a threshold miss or checksum
mismatch is FAIL. Exit: 0 ok, 2 refused input, 3 --release-ready requested but not ready.
"""
import argparse
import hashlib
import json
import platform
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "apps" / "backend"))

from semantic.enrichment import (ENRICHMENT_VERSION, FIELDS, REVIEW_BELOW, FakeEnrichmentProvider,  # noqa: E402
                                 Outcome, suggest)

DEFAULT_DATASET = HERE / "synthetic" / "enrichment_suggestions.jsonl"
THRESHOLDS = {"field_accuracy": {"min": 0.95}, "unsupported_photo_leaks": {"max": 0},
              "provenance_gaps": {"max": 0}, "privacy_leaks": {"max": 0}}
LEAK = re.compile(r"@|https?://|\d{7,}")


class NonSyntheticInput(ValueError):
    pass


def _require_synthetic(cases: list[dict]) -> None:
    if any(c.get("synthetic") is not True or not str(c.get("id", "")).startswith("syn-") for c in cases):
        raise NonSyntheticInput("evaluation cases must be explicitly synthetic with syn- ids")


def load_cases(raw: bytes) -> list[dict]:
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    _require_synthetic(cases)
    return cases


def evaluate(cases: list[dict], provider, dataset_sha256: str = "", pinned_sha256: str = "") -> dict:
    _require_synthetic(cases)
    right = total = leaks = gaps = privacy = 0
    outcomes, fields, sources = set(), set(), set()
    for c in cases:
        result = suggest(provider, c["product"], c.get("photos", []), c.get("fields", FIELDS))
        for f in result.fields:
            want = c["expected"].get(f.field, {})
            total += 1
            right += f.outcome.value == want.get("outcome") and f.value == want.get("value")
            outcomes.add(f.outcome.value)
            fields.add(f.field)
            if f.outcome is Outcome.SUGGESTED:
                sources.add(f.source)
                leaks += f.source == "photo" and f.field in ("material", "fabric")
                gaps += not (f.source and f.evidence)
                privacy += bool(LEAK.search(f"{f.value} {f.evidence}"))
    metrics = {"field_accuracy": right / total if total else None, "unsupported_photo_leaks": leaks,
               "provenance_gaps": gaps, "privacy_leaks": privacy}
    coverage = {"fields": sorted(fields), "outcomes": sorted(outcomes), "sources": sorted(sources)}
    complete = (fields == set(FIELDS) and outcomes == {o.value for o in Outcome} and sources == {"text", "photo"})
    pinned = bool(pinned_sha256) and pinned_sha256 == dataset_sha256
    reasons = [r for r, bad in (("no cases (empty evaluation)", not cases),
                                ("cases not human-reviewed", bool(cases) and not all(c.get("reviewed") is True for c in cases)),
                                ("dataset checksum is not pinned", bool(cases) and not pinned_sha256),
                                ("coverage incomplete", bool(cases) and not complete)) if bad]
    failures = []
    if pinned_sha256 and not pinned:
        failures.append("dataset sha256 does not match the pinned checksum")
    for name, limit in THRESHOLDS.items():
        v = metrics[name]
        if v is not None and (("min" in limit and v < limit["min"]) or ("max" in limit and v > limit["max"])):
            failures.append(f"{name}={v} violates {limit}")
    ready = not reasons and not failures
    return {
        "status": "PASS" if ready else "FAIL" if failures else "NOT_EVALUATED",
        "release_ready": ready, "reasons": reasons + failures, "metrics": metrics, "thresholds": THRESHOLDS,
        "coverage": coverage,
        "reproducibility": {
            "enrichment_version": ENRICHMENT_VERSION, "provider": provider.name, "model": provider.model,
            "provider_version": provider.version, "review_below": REVIEW_BELOW, "cases": len(cases),
            "dataset_sha256": dataset_sha256, "pinned_sha256": pinned_sha256, "python": platform.python_version(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--release-ready", action="store_true")
    args = parser.parse_args(argv)
    path = args.dataset.resolve()
    if path.parent != (HERE / "synthetic").resolve():
        print("refused: datasets must live in evals/synthetic/", file=sys.stderr)
        return 2
    raw = path.read_bytes() if path.is_file() else b""
    sidecar = path.with_name(path.name + ".sha256")
    pinned = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() and sidecar.read_text().strip() else ""
    try:
        cases = load_cases(raw)
    except NonSyntheticInput as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    report = evaluate(cases, FakeEnrichmentProvider(), hashlib.sha256(raw).hexdigest(), pinned)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 3 if args.release_ready and not report["release_ready"] else 0


if __name__ == "__main__":
    sys.exit(main())
