import importlib.util
import json
from pathlib import Path

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[3] / "evals"
spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)

THRESHOLDS = {"suites": {"filter_parsing": {"dataset": "datasets/filter_parsing.jsonl", "metrics": {
    "exact_match": {"min": 0.9}, "constraint_precision": {"min": 0.9}, "constraint_recall": {"min": 0.9}}}}}


def workspace(tmp_path, examples, recorded, thresholds=THRESHOLDS):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "recorded").mkdir()
    if examples is not None:
        (tmp_path / "datasets/filter_parsing.jsonl").write_text("\n".join(json.dumps(e) for e in examples))
    (tmp_path / "recorded/filter_parsing.jsonl").write_text("\n".join(json.dumps(r) for r in recorded))
    (tmp_path / "thresholds.yaml").write_text(yaml.safe_dump(thresholds))
    return tmp_path


EX = [{"id": "a", "query": "brown stole", "expected": {"category": "stoles", "colors": ["brown"]}},
      {"id": "b", "query": "not red", "expected": {"exclude_colors": ["red"]}}]
GOOD = [{"id": "a", "provenance": "model", "response": {"category": "stoles", "colors": ["brown"]}},
        {"id": "b", "provenance": "model", "response": {"exclude_colors": ["red"]}}]


def test_shipped_seed_is_a_harness_check_not_evidence():
    thresholds = yaml.safe_load((EVALS / "thresholds.yaml").read_text())
    results = {r["suite"]: r for r in run_evals.evaluate(EVALS, thresholds)}
    result = results["filter_parsing"]
    assert result["examples"] >= 10
    assert result["metrics"]["exact_match"] == 1.0              # the harness itself works...
    assert result["status"] == "not_evaluated"                  # ...but fixtures are not model output
    assert "fixtures" in result["failures"][0]
    recorded = run_evals.load_jsonl(EVALS / "recorded/filter_parsing.jsonl")
    assert recorded and all(r["provenance"] == "fixture" for r in recorded)
    scripts = {e["lang"] for e in run_evals.load_jsonl(EVALS / "datasets/filter_parsing.jsonl")}
    assert scripts == {"en", "ur", "roman_ur"}


def test_shipped_suites_without_data_are_not_evaluated_and_block_release():
    assert run_evals.main([]) == 0                      # an ordinary pull request is not blocked
    assert run_evals.main(["--release-ready"]) == 3     # AI release readiness is


def test_missing_dataset_is_not_evaluated_not_pass(tmp_path):
    root = workspace(tmp_path, None, GOOD)
    [result] = run_evals.evaluate(root, THRESHOLDS)
    assert result["status"] == "not_evaluated"
    assert run_evals.main(["--root", str(root), "--release-ready"]) == 3


def test_empty_dataset_is_not_evaluated(tmp_path):
    root = workspace(tmp_path, [], GOOD)
    assert run_evals.evaluate(root, THRESHOLDS)[0]["status"] == "not_evaluated"


def test_passing_suite_is_release_ready(tmp_path):
    root = workspace(tmp_path, EX, GOOD)
    assert run_evals.main(["--root", str(root), "--release-ready"]) == 0


def test_metric_below_threshold_turns_the_run_red(tmp_path):
    bad = [{"id": "a", "provenance": "model", "response": {"category": "shawls", "colors": ["black"]}},   # wrong
           {"id": "b", "provenance": "model", "response": {"exclude_colors": ["red"]}}]
    root = workspace(tmp_path, EX, bad)
    [result] = run_evals.evaluate(root, THRESHOLDS)
    assert result["status"] == "fail" and result["metrics"]["exact_match"] == 0.5
    assert run_evals.main(["--root", str(root)]) == 1


def test_missing_recorded_response_counts_against_the_suite(tmp_path):
    root = workspace(tmp_path, EX, GOOD[:1])
    assert run_evals.evaluate(root, THRESHOLDS)[0]["status"] == "fail"


def test_negation_dropped_is_a_recall_failure_and_wrong_extra_is_a_precision_failure():
    ex = [{"id": "n", "expected": {"colors": ["maroon"], "exclude_colors": ["black"]}}]
    dropped = run_evals.filter_parsing_metrics(ex, {"n": {"colors": ["maroon"]}})
    assert dropped["constraint_recall"] == 0.5 and dropped["constraint_precision"] == 1.0
    flipped = run_evals.filter_parsing_metrics(ex, {"n": {"colors": ["maroon", "black"]}})
    assert flipped["constraint_precision"] < 1.0


def test_list_order_does_not_matter():
    ex = [{"id": "x", "expected": {"colors": ["beige", "grey"]}}]
    assert run_evals.filter_parsing_metrics(ex, {"x": {"colors": ["grey", "beige"]}})["exact_match"] == 1.0


def test_live_mode_is_refused_so_pull_requests_never_spend_quota():
    assert run_evals.main(["--mode", "live"]) == 2


def test_json_report_records_release_readiness(tmp_path):
    out = tmp_path / "report.json"
    run_evals.main(["--json", str(out)])
    report = json.loads(out.read_text())
    assert report["release_ready"] is False
    assert {s["suite"] for s in report["suites"]} >= {"filter_parsing", "retrieval"}


def test_fixture_responses_never_count_as_evaluated_even_when_perfect(tmp_path):
    fixtures = [{**r, "provenance": "fixture"} for r in GOOD]
    root = workspace(tmp_path, EX, fixtures)
    [result] = run_evals.evaluate(root, THRESHOLDS)
    assert result["status"] == "not_evaluated" and result["metrics"]["exact_match"] == 1.0
    assert run_evals.main(["--root", str(root)]) == 0
    assert run_evals.main(["--root", str(root), "--release-ready"]) == 3


def test_responses_without_provenance_are_not_trusted(tmp_path):
    unlabeled = [{k: v for k, v in r.items() if k != "provenance"} for r in GOOD]
    assert run_evals.evaluate(workspace(tmp_path, EX, unlabeled), THRESHOLDS)[0]["status"] == "not_evaluated"


def test_a_fixture_suite_still_fails_the_job_if_the_harness_regresses(tmp_path):
    broken = [{"id": "a", "provenance": "fixture", "response": {}}, {"id": "b", "provenance": "fixture", "response": {}}]
    assert run_evals.main(["--root", str(workspace(tmp_path, EX, broken))]) == 1
