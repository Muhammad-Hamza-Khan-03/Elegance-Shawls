"""Evaluation runner. Usage (from the repo root):

  python evals/run_evals.py                  # recorded responses + deterministic code suites, no network or LLM quota
  python evals/run_evals.py --release-ready  # also fail while the intended release is not evidence-complete
  python evals/run_evals.py --json out.json

Suites (thresholds.yaml) guard features (release_profile.yaml). Statuses: pass | fail | not_evaluated.
- source `code`: the production code (parser, matcher) is executed against the dataset now, so the result is real for that code;
  source `recorded`: scored from recorded MODEL responses, and fixture rows (provenance other than "model") never count as evidence.
- A missing/empty dataset or a suite without a scorer is "not evaluated" and never passes a release gate.
- A suite is REQUIRED when its feature is scheduled in the release profile. A failing required suite exits 1. Failures in suites of
  unscheduled features are reported as advisory and do not block unrelated development (--strict makes them block).
- --release-ready (exit 3 while not ready) additionally needs, all VERIFIED rather than declared (attestation.py): every required
  suite passing on a dataset with a signed independent held-out review record and no leakage, every scheduled feature to have suites,
  an unchanged artifact manifest (thresholds and profile included) and a signed owner approval of exactly this candidate. The
  verification keys come from EVAL_REVIEWER_KEY / EVAL_OWNER_KEY in the environment; without them the gate stays closed.
- --release-ready judges ONLY the canonical files next to this script: it refuses --thresholds, --profile and any other --root (exit 2),
  because an override would be judged by a policy nobody approved.
Exit codes: 0 ok, 1 a required threshold failed, 2 usage/configuration error (including manifest drift), 3 not release-ready.
"""
import argparse
import importlib.util
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parent


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently keeping the last one."""


def _reject_duplicates(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:     # a membership test, so falsy keys (0, false, "", null) are caught too
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _reject_duplicates)
sys.path.insert(0, str(HERE))
import artifact_manifest  # noqa: E402
import attestation  # noqa: E402


def _printable(text: str) -> str:
    """Odd characters in a file name or value (lone surrogates) must not crash the report."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


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


def _backend_on_path() -> None:
    backend = str(HERE.parent / "apps" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)


def code_filter_parsing(examples: list[dict], root: Path) -> dict[str, float]:
    """Runs the PRODUCTION parser (catalog/query.py) on every query; nothing is recorded or mocked."""
    _backend_on_path()
    from catalog.query import parse_query
    return filter_parsing_metrics(examples, {e["id"]: parse_query(e["query"]).filters() for e in examples})


def code_variant_constraints(examples: list[dict], root: Path) -> dict[str, float]:
    """Parser + matcher over the fixture catalogue, via the existing deterministic runner (run_retrieval_evals.py)."""
    _backend_on_path()
    spec = importlib.util.spec_from_file_location("run_retrieval_evals", HERE / "run_retrieval_evals.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    products = module.load_catalogue(root / "fixtures" / "retrieval_catalogue.json")
    return module.run(examples, products)["metrics"]


# Suites whose source is `code`. A code suite without a scorer here (retrieval, grounding, action_safety) is "not evaluated".
CODE_SCORERS = {"filter_parsing": code_filter_parsing, "variant_constraints": code_variant_constraints}


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


def evaluate(root: Path, thresholds: dict, profile: dict | None = None, env: dict | None = None) -> list[dict]:
    env = os.environ if env is None else env
    required = _required_suites(thresholds, profile)
    results = []
    for name, suite in thresholds["suites"].items():
        review = attestation.review_problems(root, name, suite, env)   # derived, never declared in configuration
        base = {"suite": name, "feature": suite.get("feature"), "evidence": "reviewed" if not review else "unverified",
                "evidence_problems": review, "source": suite.get("source", "recorded"), "required": name in required}
        try:
            examples = load_jsonl(root / suite["dataset"])
            malformed = not all(isinstance(e, dict) for e in examples)
        except Exception:    # noqa: BLE001 - bad JSON, deep nesting, unreadable file: a malformed dataset, never a traceback
            examples, malformed = [], True
        if malformed:
            results.append({**base, "status": "not_evaluated", "examples": 0, "metrics": {}, "failures": ["dataset is malformed (every line must be a JSON object)"]})
            continue
        if not examples:
            results.append({**base, "status": "not_evaluated", "examples": 0, "metrics": {}, "failures": ["no dataset"]})
            continue
        if base["source"] == "code":
            scorer = CODE_SCORERS.get(name)
            if scorer is None:
                results.append({**base, "status": "not_evaluated", "examples": len(examples), "metrics": {},
                                "failures": ["no scorer implemented for this suite"]})
                continue
            try:
                metrics, genuine = scorer(examples, root), True
            except Exception as error:   # noqa: BLE001 - a scorer that cannot handle its dataset is a failed suite, never a skipped one
                results.append({**base, "status": "fail", "examples": len(examples), "metrics": {},
                                "failures": [f"scorer error on this dataset ({type(error).__name__}); check the rows"]})
                continue
        else:
            if name not in SCORERS:
                results.append({**base, "status": "not_evaluated", "examples": len(examples), "metrics": {},
                                "failures": ["no scorer implemented for this suite"]})
                continue
            try:
                recorded = load_jsonl(root / "recorded" / f"{name}.jsonl")
                metrics = SCORERS[name](examples, {r["id"]: r["response"] for r in recorded})
                genuine = bool(recorded) and all(r.get("provenance") == "model" for r in recorded)
            except Exception as error:   # noqa: BLE001 - malformed recorded rows fail the suite instead of crashing the run
                results.append({**base, "status": "fail", "examples": len(examples), "metrics": {},
                                "failures": [f"recorded responses or scorer error ({type(error).__name__}); check the rows"]})
                continue
        failures = _check(metrics, suite["metrics"])
        status = "fail" if failures else "pass" if genuine else "not_evaluated"
        if status == "not_evaluated":
            failures = ["recorded responses are fixtures, not model output (harness check only)"]
        results.append({**base, "status": status, "examples": len(examples), "metrics": metrics, "failures": failures})
    return results


def _required_suites(thresholds: dict, profile: dict | None) -> set[str]:
    """Suites guarding a scheduled feature. Without a profile every suite is required (the pre-profile behaviour)."""
    if profile is None:
        return set(thresholds["suites"])
    scheduled = {name for name, feature in profile["features"].items() if feature.get("scheduled")}
    return {name for name, suite in thresholds["suites"].items() if suite.get("feature") in scheduled}


def _is_limit(limit) -> bool:
    return isinstance(limit, dict) and len(limit) == 1 and set(limit) <= {"min", "max"} \
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in limit.values())


def profile_problems(thresholds: dict, profile: dict) -> list[str]:
    """Configuration errors: strict shape, and the profile and thresholds must describe the same suites and features.
    Unknown keys are errors so a flag the gate does not read (a self-declared `evidence`, `approval`...) can never look meaningful."""
    problems, listed, owners = [], set(), {}
    problems += [f"profile: unknown key {k} (approval and evidence are signed records, see attestation.py)"
                 for k in profile if k not in {"features", "other_settings"}]
    for fname, feature in profile["features"].items():
        problems += [f"feature {fname}: unknown key {k}" for k in feature if k not in {"scheduled", "suites", "settings"}]
        if not isinstance(feature.get("scheduled"), bool):
            problems.append(f"feature {fname}: scheduled must be a true/false boolean, got {feature.get('scheduled')!r}")
        for key in ("suites", "settings"):
            if not isinstance(feature.get(key), list) or not all(isinstance(i, str) for i in feature[key]):
                problems.append(f"feature {fname}: {key} must be a list of names")
        for setting in feature.get("settings") or []:
            if owners.setdefault(setting, fname) != fname:
                problems.append(f"setting {setting} is listed under both {owners[setting]} and {fname}")
        for suite in feature.get("suites") or []:
            listed.add(suite)
            if suite not in thresholds["suites"]:
                problems.append(f"feature {fname} lists unknown suite {suite}")
            elif thresholds["suites"][suite].get("feature") != fname:
                problems.append(f"suite {suite} says feature {thresholds['suites'][suite].get('feature')}, profile lists it under {fname}")
    problems += [f"suite {n} is not listed under any feature" for n in thresholds["suites"] if n not in listed]
    for name, suite in thresholds["suites"].items():
        problems += [f"suite {name}: unknown key {k}" + (" (evidence is derived from signed attestations, not declared)" if k == "evidence" else "")
                     for k in suite if k not in {"dataset", "source", "feature", "metrics"}]
        dataset = suite.get("dataset")
        if not isinstance(dataset, str) or not dataset or Path(dataset).is_absolute() or ".." in Path(dataset).parts:
            problems.append(f"suite {name}: dataset must be a relative path inside the evals directory")
        if suite.get("source") not in {"code", "recorded"}:
            problems.append(f"suite {name}: source must be code or recorded")
        if not isinstance(suite.get("metrics"), dict) or not suite["metrics"] or not all(_is_limit(v) for v in suite["metrics"].values()):
            problems.append(f"suite {name}: metrics must map names to exactly one finite, non-negative numeric min or max")
    return problems


def release_blockers(results: list[dict], profile: dict | None, root: Path | None = None, env: dict | None = None) -> list[str]:
    """Why the intended release is not evidence-complete (empty list = ready). Never inferred from the environment or declared in YAML."""
    if profile is None or root is None:
        return ["no release profile: the intended release configuration is unknown"]
    env = os.environ if env is None else env
    blockers = [f"artifact integrity: {p}" for p in artifact_manifest.verify(root)]
    for fname, feature in profile["features"].items():
        if feature.get("scheduled") and not feature.get("suites"):
            blockers.append(f"feature {fname} is scheduled but has no evaluation suite")
    for r in results:
        if not r["required"]:
            continue
        if r["status"] != "pass":
            blockers.append(f"suite {r['suite']}: {r['status']}")
        elif r["evidence"] != "reviewed":
            blockers.append(f"suite {r['suite']}: no verified independent held-out review ({'; '.join(r['evidence_problems'])})")
    blockers += [f"owner approval: {p}" for p in attestation.approval_problems(root, env)]
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=HERE)
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--mode", choices=["recorded", "live"], default="recorded")
    parser.add_argument("--release-ready", action="store_true")
    parser.add_argument("--strict", action="store_true", help="advisory failures (unscheduled features) also fail")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.release_ready and (args.thresholds or args.profile or args.root.resolve() != HERE):
        print("configuration error: --release-ready judges the canonical thresholds, profile and root only; --thresholds, --profile and --root are refused")
        return 2
    if args.mode == "live":
        print("live mode is not available yet: no parser prompt exists. Pull requests use recorded responses.")
        return 2
    profile_path = args.profile or args.root / "release_profile.yaml"
    thresholds_path = args.thresholds or args.root / "thresholds.yaml"
    for path in (profile_path, thresholds_path):
        if not path.is_file():   # never lenient: a missing file, or a FIFO/device in its place, must not weaken the gate or hang it
            print(f"configuration error: {path.name} missing or not a regular file ({path})")
            return 2
    try:
        thresholds = yaml.load(thresholds_path.read_text(encoding="utf-8"), Loader=_StrictLoader)
        profile = yaml.load(profile_path.read_text(encoding="utf-8"), Loader=_StrictLoader)
        if not (isinstance(thresholds, dict) and isinstance(thresholds.get("suites"), dict)
                and all(isinstance(x, dict) for x in thresholds["suites"].values())
                and isinstance(profile, dict) and isinstance(profile.get("features"), dict)
                and all(isinstance(f, dict) for f in profile["features"].values())):
            raise ValueError("wrong top-level shape")
    except Exception as error:   # noqa: BLE001 - empty, invalid or hostile YAML is a configuration error, not a traceback
        print(f"configuration error: thresholds or profile unreadable ({type(error).__name__}: {error})")
        return 2
    if problems := profile_problems(thresholds, profile):
        for problem in problems:
            print("configuration error:", problem)
        return 2
    if args.root.resolve() == HERE and (drift := artifact_manifest.verify(HERE)):
        for problem in drift:
            print("configuration error: frozen artifact:", _printable(problem))
        return 2
    results = evaluate(args.root, thresholds, profile)
    for r in results:
        detail = ", ".join(f"{k}={v:.3f}" for k, v in r["metrics"].items()) or "-"
        tag = "REQUIRED" if r["required"] else "advisory"
        print(f"{r['suite']:<22} {r['status'].upper():<14} {tag:<9} {r['evidence']:<10} n={r['examples']:<4} {detail}")
        for failure in r["failures"]:
            print(f"    - {failure}")
    failed = [r["suite"] for r in results if r["status"] == "fail" and (r["required"] or args.strict)]
    blockers = release_blockers(results, profile, args.root)
    canonical = args.root.resolve() == HERE and not (args.thresholds or args.profile)
    release_ready = canonical and not failed and not blockers    # a scratch root or override is never reported as release-ready
    print(f"\nrelease_ready={str(release_ready).lower()}")
    for blocker in blockers:
        print(f"  blocked: {_printable(blocker)}")
    if args.json:
        args.json.write_text(json.dumps({"release_ready": release_ready, "blockers": blockers, "suites": results}, indent=2), encoding="utf-8")
    if failed:
        return 1
    return 3 if args.release_ready and not release_ready else 0


if __name__ == "__main__":
    sys.exit(main())
