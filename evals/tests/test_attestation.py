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


# ---- --release-ready judges only the canonical policy (QA finding: overrides were unbound) ----

def _loosened_and_unscheduled(tmp_path):
    thresholds = yaml.safe_load((EVALS / "thresholds.yaml").read_text())
    for suite in thresholds["suites"].values():
        suite["metrics"] = {name: {"min": 0.0} for name in suite["metrics"]}
    profile = yaml.safe_load((EVALS / "release_profile.yaml").read_text())
    for feature in profile["features"].values():
        feature["scheduled"] = False
    (tmp_path / "loose.yaml").write_text(yaml.safe_dump(thresholds))
    (tmp_path / "off.yaml").write_text(yaml.safe_dump(profile))
    return str(tmp_path / "loose.yaml"), str(tmp_path / "off.yaml")


@pytest.mark.parametrize("keys", [{}, {"EVAL_OWNER_KEY": OWNER}, ENV])
def test_release_ready_refuses_overrides_whatever_keys_are_present(tmp_path, monkeypatch, keys):
    loose, off = _loosened_and_unscheduled(tmp_path)
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    assert run_evals.main(["--release-ready", "--thresholds", loose]) == 2
    assert run_evals.main(["--release-ready", "--profile", off]) == 2
    assert run_evals.main(["--release-ready", "--thresholds", loose, "--profile", off]) == 2
    assert run_evals.main(["--release-ready", "--root", str(tmp_path)]) == 2
    assert run_evals.main(["--release-ready"]) == 3                    # the canonical policy, still closed
    assert run_evals.main(["--thresholds", loose, "--profile", off]) == 0   # overrides remain usable for ordinary development runs


def test_manifest_drift_is_exit_2_on_the_canonical_root_however_it_is_spelled(monkeypatch):
    monkeypatch.setattr(artifact_manifest, "verify", lambda root=None: ["thresholds.yaml: content changed"])
    assert run_evals.main([]) == 2
    assert run_evals.main(["--root", str(EVALS / "..", ) + "/evals"]) == 2     # same directory, different spelling
    assert run_evals.main(["--root", str(EVALS / "tests" / "..")]) == 2


# ---- leakage detection ----

@pytest.mark.parametrize("row", [
    '{"id": "t", "query": "Café Stole"}',                       # NFC vs NFD below
    '{"id": "t", "query": "brown, stole!"}',
    '{"id": "t", "utterance": "BROWN  stole"}',
    '{"id": "t", "meta": {"input": ["x", "brown stole"]}}',      # nested and list valued
    '{"id": "t", "transcript": "ｂｒｏｗｎ ｓｔｏｌｅ"}',          # full-width forms
])
def test_leakage_sees_normalised_nested_and_alternative_fields(root, row):
    (root / "datasets/held.jsonl").write_text('{"id": "h", "query": "brown stole"}\n{"id": "h2", "query": "café stole"}\n')
    (root / "datasets/train.jsonl").write_text(row + "\n")
    assert attestation.leakage(root, "datasets/held.jsonl"), row


def test_leakage_scans_subdirectories_and_ignores_unrelated_text(root):
    (root / "datasets/sub").mkdir()
    (root / "datasets/sub/more.jsonl").write_text('{"id": "x", "query": "brown stole"}\n')
    (root / "datasets/held.jsonl").write_text('{"id": "h", "query": "brown stole", "note": "grey shawl"}\n')
    assert [leak.split(":")[0] for leak in attestation.leakage(root, "datasets/held.jsonl")] == ["datasets/sub/more.jsonl"]   # `note` and ids are not queries


def test_documented_leakage_limits_are_real(root):
    (root / "datasets/held.jsonl").write_text('{"id": "h", "query": "brown stole"}\n')
    (root / "datasets/train.jsonl").write_text('{"id": "t", "query": "a brown stole"}\n')      # paraphrase is NOT detected
    assert attestation.leakage(root, "datasets/held.jsonl") == []


# ---- malformed input fails closed with a controlled message ----

@pytest.mark.parametrize("raw", ['{"payload": {}, "signature": "éè"}', "[]", "null", "not json", '{"payload": "x", "signature": 5}', '{"payload": null}'])
def test_malformed_records_are_verification_failures_not_exceptions(root, raw):
    (root / "attestations").mkdir()
    (root / "attestations/s.json").write_text(raw, encoding="utf-8")
    assert attestation.review_problems(root, "s", SUITE, ENV)
    (root / "approval.json").write_text(raw, encoding="utf-8")
    assert attestation.approval_problems(root, ENV)


def test_invalid_utf8_record_fails_closed(root):
    (root / "attestations").mkdir()
    (root / "attestations/s.json").write_bytes(b"\xff\xfe\x00")
    assert attestation.review_problems(root, "s", SUITE, ENV)


@pytest.mark.parametrize("bad", ["[1, 2]\n", "not json\n", '"text"\n'])
def test_non_object_or_invalid_rows_in_any_dataset_block_instead_of_crashing(root, bad):
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    (root / "datasets/train.jsonl").write_text(bad)
    assert "could not be checked" in " ".join(attestation.review_problems(root, "s", SUITE, ENV))


def test_a_malformed_scored_dataset_is_not_evaluated_not_a_crash(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets/d.jsonl").write_text('[1]\n')
    thresholds = {"suites": {"s": {"dataset": "datasets/d.jsonl", "source": "code", "feature": "f", "metrics": {"m": {"min": 1}}}}}
    [result] = run_evals.evaluate(tmp_path, thresholds, None, env={})
    assert result["status"] == "not_evaluated" and "malformed" in result["failures"][0]


# ---- payload validation, digest coverage, canonicalisation, manifest problems (previously surviving mutations) ----

@pytest.mark.parametrize("change", [{"extra": "x"}, {"reviewer": ""}, {"reviewer": "  "}, {"reviewer": 5}, {"split": None}, {"reviewed_at": ["x"]}])
def test_payload_must_have_exactly_the_expected_non_empty_text_fields(root, change):
    write_record(root / "attestations/s.json", {**review_payload(root), **change}, REVIEWER)
    assert "payload must have exactly" in attestation.review_problems(root, "s", SUITE, ENV)[0]
    missing = {k: v for k, v in review_payload(root).items() if k != "reviewer"}
    write_record(root / "attestations/s.json", missing, REVIEWER)
    assert "payload must have exactly" in attestation.review_problems(root, "s", SUITE, ENV)[0]


def test_missing_dataset_file_is_a_problem(root):
    write_record(root / "attestations/s.json", review_payload(root), REVIEWER)
    (root / "datasets/held.jsonl").unlink()
    assert "differs from the attested sha256" in " ".join(attestation.review_problems(root, "s", SUITE, ENV))


def test_signature_does_not_depend_on_key_order():
    assert attestation.sign({"a": "1", "b": "2"}, REVIEWER) == attestation.sign({"b": "2", "a": "1"}, REVIEWER)
    assert attestation.sign({"a": "1"}, REVIEWER) != attestation.sign({"a": "1"}, OWNER)


def test_candidate_digest_covers_thresholds_profile_manifest_and_every_attestation(root, frozen):
    make_release(root)
    base = attestation.candidate_digest(root)
    for name in ("thresholds.yaml", "release_profile.yaml", "artifact_manifest.json", "attestations/s.json"):
        path = root / name
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        assert attestation.candidate_digest(root) != base, name
        path.write_bytes(original)
    write_record(root / "attestations/extra.json", review_payload(root, suite="extra"), REVIEWER)     # a new attestation changes it too
    assert attestation.candidate_digest(root) != base


def test_reviewer_and_author_comparison_is_normalised_and_its_limit_is_documented(root):
    for reviewer in ("AUTHOR-A", " author-a ", "ａｕｔｈｏｒ－ａ", "author-a "):       # case, space, full-width, no-break space
        write_record(root / "attestations/s.json", review_payload(root, reviewer=reviewer), REVIEWER)
        assert "not independent" in " ".join(attestation.review_problems(root, "s", SUITE, ENV)), reviewer
    write_record(root / "attestations/s.json", review_payload(root, reviewer="author-a b"), REVIEWER)
    assert attestation.review_problems(root, "s", SUITE, ENV) == []      # LIMIT: two different strings are two people as far as code can tell


def test_manifest_verify_reports_missing_manifest_missing_files_and_unlisted_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact_manifest, "FROZEN", ["a.txt", "b.txt"])
    assert artifact_manifest.verify(tmp_path) == ["artifact_manifest.json: missing"]
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "artifact_manifest.json").write_text(json.dumps({"sha256": {"a.txt": artifact_manifest.digest(tmp_path / "a.txt"), "gone.txt": "0"}}))
    found = " ".join(artifact_manifest.verify(tmp_path))
    assert "b.txt: not in the manifest" in found and "gone.txt: missing" in found
    (tmp_path / "a.txt").write_text("changed")
    assert "a.txt: content changed" in " ".join(artifact_manifest.verify(tmp_path))
