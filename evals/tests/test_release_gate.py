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
    return {"suite": suite, "status": status, "required": required, "evidence": evidence, "evidence_problems": ["x"], "metrics": {}, "failures": []}


def profile(**features):
    return {"features": {n: {"settings": [], **f} for n, f in features.items()}}


def blockers(results, p, tmp_path):
    """Blockers other than the (separately tested) manifest and signed-approval checks of an empty root."""
    return [b for b in run_evals.release_blockers(results, p, tmp_path, env={}) if not b.startswith(("artifact integrity", "owner approval"))]


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
        (tmp_path / "release_profile.yaml").write_text(yaml.safe_dump({"features": {"f": {"scheduled": scheduled, "suites": ["s"], "settings": []}}}))
        assert run_evals.main(["--root", str(tmp_path)]) == expected
    assert run_evals.main(["--root", str(tmp_path), "--strict"]) == 1            # strict mode makes advisory failures block


def test_release_needs_pass_verified_review_and_suites(tmp_path):
    p = profile(a={"scheduled": True, "suites": ["s"]})
    assert blockers([result("s")], p, tmp_path) == []
    assert "no verified independent held-out review" in blockers([result("s", evidence="unverified")], p, tmp_path)[0]
    assert "not_evaluated" in blockers([result("s", "not_evaluated")], p, tmp_path)[0]
    assert "fail" in blockers([result("s", "fail")], p, tmp_path)[0]
    assert any("no evaluation suite" in b for b in blockers([], profile(a={"scheduled": True, "suites": []}), tmp_path))
    assert run_evals.release_blockers([result("s")], None, tmp_path)           # unknown intent is never ready


def test_a_yaml_approval_or_evidence_flag_is_rejected_not_honoured():
    forged_profile = {**PROFILE, "approval": {"recorded": True, "reference": "anything"}}
    assert any("unknown key approval" in p for p in run_evals.profile_problems(THRESHOLDS, forged_profile))
    suites = {n: {**s, "evidence": "reviewed"} for n, s in THRESHOLDS["suites"].items()}
    assert any("evidence is derived" in p for p in run_evals.profile_problems({"suites": suites}, PROFILE))


def test_feature_configuration_cannot_hide_an_activation():
    def with_feature(**changes):
        features = {**PROFILE["features"], "semantic_search": {**PROFILE["features"]["semantic_search"], **changes}}
        return run_evals.profile_problems(THRESHOLDS, {**PROFILE, "features": features})
    assert with_feature() == []
    assert with_feature(scheduled="false")                       # a truthy string must not be read as a boolean
    assert with_feature(scheduled=None) and with_feature(enabled=True)
    assert with_feature(settings="embedding_enabled")            # not a list of names
    duplicated = {**PROFILE["features"]["assistant"], "settings": PROFILE["features"]["assistant"]["settings"] + ["embedding_enabled"]}
    assert any("both" in p for p in run_evals.profile_problems(THRESHOLDS, {**PROFILE, "features": {**PROFILE["features"], "assistant": duplicated}}))


def test_loosened_thresholds_are_malformed_or_caught_by_the_manifest():
    loosened = {"suites": {**THRESHOLDS["suites"], "variant_constraints": {**THRESHOLDS["suites"]["variant_constraints"], "metrics": {"recall": {"min": "0.1"}}}}}
    assert any("exactly one numeric" in p for p in run_evals.profile_problems(loosened, PROFILE))
    import artifact_manifest
    assert {"thresholds.yaml", "release_profile.yaml"} <= set(artifact_manifest.FROZEN)


def test_unscheduled_feature_does_not_block_release_of_the_rest(tmp_path):
    p = profile(a={"scheduled": True, "suites": ["s"]}, b={"scheduled": False, "suites": ["t"]})
    assert blockers([result("s"), result("t", "not_evaluated", required=False)], p, tmp_path) == []


def test_configuration_drift_is_an_error():
    thresholds = {"suites": {"s": {"feature": "f"}, "orphan": {"feature": "f"}}}
    assert run_evals.profile_problems(thresholds, {"features": {"f": {"suites": ["s", "ghost"]}}})   # unknown + unlisted suites
    assert run_evals.profile_problems({"suites": {"s": {"feature": "x"}}}, {"features": {"f": {"suites": ["s"]}}})   # wrong feature


def test_missing_profile_is_an_error_not_a_weaker_gate(tmp_path):
    (tmp_path / "thresholds.yaml").write_text(yaml.safe_dump(THRESHOLDS))
    assert run_evals.main(["--root", str(tmp_path)]) == 2


def test_limits_must_be_exactly_one_numeric_bound():
    assert not run_evals._is_limit({"min": 0.9, "max": 1})                  # two bounds
    assert not run_evals._is_limit({}) and not run_evals._is_limit({"min": True}) and not run_evals._is_limit({"avg": 1})
    assert run_evals._is_limit({"min": 0}) and run_evals._is_limit({"max": 0.5})
