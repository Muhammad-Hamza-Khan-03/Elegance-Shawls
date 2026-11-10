"""Evidence and approval are verified, never declared: the only path to release_ready=true runs through keys that are not in the repo."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)
attestation, artifact_manifest = run_evals.attestation, run_evals.artifact_manifest

REVIEWER, OWNER = "r" * 40, "o" * 40
ENV = {"EVAL_REVIEWER_KEY": REVIEWER, "EVAL_OWNER_KEY": OWNER}
SUITE = {"dataset": "datasets/held.jsonl", "source": "code", "feature": "f", "metrics": {"m": {"min": 0.5}}}


def write_record(path, payload, key):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"payload": payload, "signature": attestation.sign(payload, key)}))


def review_payload(root, **changes):
    return {"suite": "s", "dataset": "datasets/held.jsonl", "dataset_sha256": attestation.sha256_file(root / "datasets/held.jsonl"),
            "split": "held_out", "author": "author-a", "reviewer": "reviewer-b", "reviewed_at": "2026-11-10", **changes}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets/held.jsonl").write_text('{"id": "h1", "query": "Brown   Stole"}\n')
    (tmp_path / "datasets/train.jsonl").write_text('{"id": "t1", "query": "grey shawl"}\n')
    return tmp_path


def test_valid_independent_held_out_review_verifies(root):
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    assert attestation.review_problems(root, "s", SUITE, ENV) == []


def test_without_the_key_nothing_verifies_even_a_perfect_looking_record(root):
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    assert "cannot verify" in attestation.review_problems(root, "s", SUITE, {})[0]
    assert "cannot verify" in attestation.review_problems(root, "s", SUITE, {"EVAL_REVIEWER_KEY": "short"})[0]


@pytest.mark.parametrize("change,message", [
    ({"dataset_sha256": "0" * 64}, "differs from the attested sha256"),
    ({"split": "dev"}, "must be held_out"),
    ({"reviewer": " Author-A "}, "not independent"),
    ({"suite": "other"}, "different suite"),
])
def test_review_must_bind_dataset_split_and_independent_reviewer(root, change, message):
    write_record(root / "attestations/s.json", review_payload(root, **change), REVIEWER)
    assert message in " ".join(attestation.review_problems(root, "s", SUITE, ENV))


def test_forged_tampered_or_wrongly_keyed_records_are_rejected(root):
    path = root / "attestations/s.json"
    write_record(path, review_payload(root), "x" * 40)                                  # signed with some other key
    assert "does not verify" in attestation.review_problems(root, "s", SUITE, ENV)[0]
    write_record(path, review_payload(root), REVIEWER)
    record = json.loads(path.read_text())
    record["payload"]["reviewer"] = "someone-else"                                        # edited after signing
    path.write_text(json.dumps(record))
    assert "does not verify" in attestation.review_problems(root, "s", SUITE, ENV)[0]
    path.write_text('{"payload": {}, "signature": "approved"}')                          # a bare "approval" is not a record
    assert attestation.review_problems(root, "s", SUITE, ENV)


def test_dataset_edited_after_review_invalidates_it(root):
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    (root / "datasets/held.jsonl").write_text('{"id": "h1", "query": "brown stole"}\n{"id": "h2", "query": "easy one"}\n')
    assert "differs from the attested sha256" in " ".join(attestation.review_problems(root, "s", SUITE, ENV))


def test_held_out_leakage_blocks(root):
    (root / "datasets/train.jsonl").write_text('{"id": "t1", "q": "brown stole"}\n')    # same query, other field, other case/spacing
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    assert "leakage" in " ".join(attestation.review_problems(root, "s", SUITE, ENV))


def make_release(root):
    """A fully valid candidate in a scratch root, to show what the only road to release_ready looks like."""
    thresholds = {"suites": {"s": SUITE}}
    profile = {"features": {"f": {"scheduled": True, "suites": ["s"], "settings": []}}}
    (root / "thresholds.yaml").write_text(yaml.safe_dump(thresholds))
    (root / "release_profile.yaml").write_text(yaml.safe_dump(profile))
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    artifact_manifest.FROZEN[:] = ["datasets/held.jsonl", "thresholds.yaml", "release_profile.yaml"]
    artifact_manifest.write(root)
    write_record(root / "approval.json", {"owner": "owner", "candidate_digest": attestation.candidate_digest(root), "approved_at": "2026-11-10"}, OWNER)
    return thresholds, profile


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(artifact_manifest, "FROZEN", list(artifact_manifest.FROZEN))


def blockers(root, thresholds, profile, env=ENV):
    return run_evals.release_blockers([{"suite": "s", "status": "pass", "required": True, "evidence": "reviewed" if not attestation.review_problems(root, "s", SUITE, env) else "unverified",
                                        "evidence_problems": attestation.review_problems(root, "s", SUITE, env)}], profile, root, env)


def test_only_signed_review_signed_approval_and_unchanged_candidate_is_ready(root, frozen):
    thresholds, profile = make_release(root)
    assert blockers(root, thresholds, profile) == []
    assert any("owner approval" in b for b in blockers(root, thresholds, profile, {"EVAL_REVIEWER_KEY": REVIEWER}))   # owner key absent
    assert any("keys must differ" in b for b in blockers(root, thresholds, profile, {"EVAL_REVIEWER_KEY": OWNER, "EVAL_OWNER_KEY": OWNER}))


def test_changing_thresholds_after_approval_revokes_it_and_trips_the_manifest(root, frozen):
    thresholds, profile = make_release(root)
    (root / "thresholds.yaml").write_text(yaml.safe_dump({"suites": {"s": {**SUITE, "metrics": {"m": {"min": 0.0}}}}}))
    found = " ".join(blockers(root, thresholds, profile))
    assert "artifact integrity: thresholds.yaml" in found and "approved a different candidate" in found


def test_a_forged_approval_file_is_not_enough(root, frozen):
    thresholds, profile = make_release(root)
    (root / "approval.json").write_text(json.dumps({"payload": {"owner": "me", "candidate_digest": attestation.candidate_digest(root), "approved_at": "now"}, "signature": "x"}))
    assert any("does not verify" in b for b in blockers(root, thresholds, profile))


def test_shipped_repo_has_no_records_and_stays_closed():
    assert not (EVALS / "approval.json").exists() and not list((EVALS / "attestations").glob("*.json"))
    assert run_evals.main(["--release-ready"]) == 3
