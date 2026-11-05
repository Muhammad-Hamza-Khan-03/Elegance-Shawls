import importlib.util
import json
from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_m3_evals", EVALS / "run_m3_evals.py")
m3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m3)


def test_shipped_suites_pass():
    r = m3.evaluate()
    assert {x["suite"]: x["status"] for x in r} == {s: "PASS" for s in ("behavior", "safety", "grounding", "no_silent_relaxation")}


def test_missing_and_empty_datasets_are_not_evaluated(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "m3_behavior.jsonl").write_text("")
    (tmp_path / "m3_manifest.yaml").write_text(yaml.safe_dump({"suites": {
        "behavior": {"dataset": "datasets/m3_behavior.jsonl"}, "safety": {"dataset": "datasets/nope.jsonl"}}}))
    assert [x["status"] for x in m3.evaluate(tmp_path)] == ["NOT_EVALUATED", "NOT_EVALUATED"]


def test_wrong_expectation_fails(tmp_path):
    (tmp_path / "datasets").mkdir()
    row = {"id": "x1", "tool": "delete_everything", "input": {}, "expect": {"outcome": "validated"}}
    (tmp_path / "datasets" / "d.jsonl").write_text(json.dumps(row) + "\n")
    (tmp_path / "m3_manifest.yaml").write_text(yaml.safe_dump({"suites": {"safety": {"dataset": "datasets/d.jsonl"}}}))
    assert m3.evaluate(tmp_path)[0]["status"] == "FAIL"


def test_results_carry_no_release_ready():
    assert all("release_ready" not in r for r in m3.evaluate())
