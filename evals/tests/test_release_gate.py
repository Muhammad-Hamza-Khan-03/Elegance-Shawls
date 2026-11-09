"""Gate semantics: feature-aware requirements, advisory failures, evidence and approval rules, and the shipped state."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)
THRESHOLDS = yaml.safe_load((EVALS / "thresholds.yaml").read_text())
PROFILE = yaml.safe_load((EVALS / "release_profile.yaml").read_text())


def result(suite, status="pass", required=True, evidence="reviewed"):
    return {"suite": suite, "status": status, "required": required, "evidence": evidence, "metrics": {}, "failures": []}


def profile(**features):
    return {"approval": {"recorded": True, "reference": "owner-approval-1"}, "features": features}


def test_shipped_gate_is_not_release_ready():
    results = run_evals.evaluate(EVALS, THRESHOLDS, PROFILE)
    assert run_evals.release_blockers(results, PROFILE), "release_ready must stay false until evidence and approval exist"
    assert run_evals.main([]) == 0 and run_evals.main(["--release-ready"]) == 3


def test_profile_and_thresholds_describe_the_same_suites():
    assert run_evals.profile_problems(THRESHOLDS, PROFILE) == []


def test_only_scheduled_features_make_suites_required():
    required = run_evals._required_suites(THRESHOLDS, PROFILE)
    assert required == {"filter_parsing", "variant_constraints"}
    scheduled = {**PROFILE, "features": {**PROFILE["features"], "semantic_search": {**PROFILE["features"]["semantic_search"], "scheduled": True}}}
    assert "retrieval" in run_evals._required_suites(THRESHOLDS, scheduled)    # scheduling a feature cannot skip its suite


def test_disabled_feature_failure_is_advisory_but_a_scheduled_one_blocks(tmp_path, monkeypatch):
    bad = {"suites": {"s": {"dataset": "d.jsonl", "source": "code", "feature": "f", "metrics": {"m": {"min": 1}}}}}
    (tmp_path / "d.jsonl").write_text('{"id": "x"}\n')
    monkeypatch.setitem(run_evals.CODE_SCORERS, "s", lambda examples, root: {"m": 0.0})
    for scheduled, expected in ((False, 0), (True, 1)):
        (tmp_path / "thresholds.yaml").write_text(yaml.safe_dump(bad))
        (tmp_path / "release_profile.yaml").write_text(yaml.safe_dump({"features": {"f": {"scheduled": scheduled, "suites": ["s"]}}}))
        assert run_evals.main(["--root", str(tmp_path)]) == expected
    assert run_evals.main(["--root", str(tmp_path), "--strict"]) == 1            # strict mode makes advisory failures block


def test_release_needs_pass_reviewed_evidence_suites_and_approval():
    p = profile(a={"scheduled": True, "suites": ["s"]})
    assert run_evals.release_blockers([result("s")], p) == []
    assert "reviewed" in run_evals.release_blockers([result("s", evidence="synthetic")], p)[0]     # synthetic data never qualifies
    assert "not_evaluated" in run_evals.release_blockers([result("s", "not_evaluated")], p)[0]
    assert "fail" in run_evals.release_blockers([result("s", "fail")], p)[0]
    assert any("no evaluation suite" in b for b in run_evals.release_blockers([], profile(a={"scheduled": True, "suites": []})))
    assert any("approval" in b for b in run_evals.release_blockers([result("s")], {**p, "approval": {"recorded": False, "reference": None}}))
    assert any("approval" in b for b in run_evals.release_blockers([result("s")], {**p, "approval": {"recorded": True, "reference": None}}))
    assert run_evals.release_blockers([result("s")], None)                                          # unknown intent is never ready


def test_unscheduled_feature_does_not_block_release_of_the_rest():
    p = profile(a={"scheduled": True, "suites": ["s"]}, b={"scheduled": False, "suites": ["t"]})
    assert run_evals.release_blockers([result("s"), result("t", "not_evaluated", required=False)], p) == []


def test_configuration_drift_is_an_error():
    thresholds = {"suites": {"s": {"feature": "f"}, "orphan": {"feature": "f"}}}
    assert run_evals.profile_problems(thresholds, {"features": {"f": {"suites": ["s", "ghost"]}}})   # unknown + unlisted suites
    assert run_evals.profile_problems({"suites": {"s": {"feature": "x"}}}, {"features": {"f": {"suites": ["s"]}}})   # wrong feature


def test_missing_profile_is_an_error_not_a_weaker_gate(tmp_path):
    (tmp_path / "thresholds.yaml").write_text(yaml.safe_dump(THRESHOLDS))
    assert run_evals.main(["--root", str(tmp_path)]) == 2
