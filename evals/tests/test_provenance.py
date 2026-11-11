"""Provenance declarations: complete, hash-bound, and never an upgrade of unreviewed data."""
import json
import sys
from pathlib import Path

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))
import attestation  # noqa: E402
import provenance  # noqa: E402

REVIEWER = "r" * 40
ENV = {"EVAL_REVIEWER_KEY": REVIEWER}


def entry(path, **changes):
    base = {"origin": "synthetic_unrecorded", "review": "unreviewed", "split": "unsplit", "sha256": attestation.sha256_file(path), "note": "fixture"}
    return {**base, **changes}


def write_prov(root, **changes):
    (root / "provenance.yaml").write_text(yaml.safe_dump({"schema": 1, "min_n": 30, "datasets": {"datasets/a.jsonl": entry(root / "datasets/a.jsonl", **changes)}}))


@pytest.fixture
def root(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets/a.jsonl").write_text('{"id": "1", "q": "brown stole", "reviewed": false}\n')
    write_prov(tmp_path)
    return tmp_path


def test_the_repository_provenance_is_consistent():
    assert provenance.problems(EVALS, env={}) == []


def test_no_shipped_dataset_is_declared_verified_or_independent():
    entries = provenance.load(EVALS)["datasets"]
    assert {e["review"] for e in entries.values()} <= {"unreviewed", "ai_reviewed_only", "owner_statement_unsigned"}   # nothing verified exists
    assert not list((EVALS / "reviews").glob("*.json")) if (EVALS / "reviews").is_dir() else True


def test_voice_urdu_review_is_recorded_as_an_unsigned_owner_statement_only():
    e = provenance.load(EVALS)["datasets"]["datasets/voice_urdu.jsonl"]
    assert e["review"] == "owner_statement_unsigned" and "no signed record" in e["review_scope"] and "independent" in e["review_scope"]


def test_clean_fixture_passes(root):
    assert provenance.problems(root, env={}) == []


def test_every_dataset_needs_an_entry_and_every_entry_a_dataset(root):
    (root / "datasets/b.jsonl").write_text("{}\n")
    assert any("b.jsonl: dataset has no provenance entry" in p for p in provenance.problems(root, env={}))
    (root / "datasets/b.jsonl").unlink()
    (root / "datasets/a.jsonl").unlink()
    assert any("missing dataset" in p for p in provenance.problems(root, env={}))


def test_a_changed_dataset_invalidates_its_entry(root):
    (root / "datasets/a.jsonl").write_text('{"id": "1", "q": "changed"}\n')
    assert any("sha256 does not match" in p for p in provenance.problems(root, env={}))


@pytest.mark.parametrize("change", [{"origin": "made-up"}, {"review": "great"}, {"split": "test"}, {"note": ""}, {"review": None}])
def test_vocabulary_and_note_are_enforced(root, change):
    write_prov(root, **change)
    assert provenance.problems(root, env={})


def test_row_level_reviewed_true_cannot_upgrade_an_unreviewed_dataset(root):
    (root / "datasets/a.jsonl").write_text('{"id": "1", "q": "x", "reviewed": true}\n')
    write_prov(root)
    assert any("claim reviewed=true" in p for p in provenance.problems(root, env={}))
    write_prov(root, review="ai_reviewed_only")
    assert any("claim reviewed=true" in p for p in provenance.problems(root, env={}))
    write_prov(root, review="owner_statement_unsigned", reviewer="owner", review_date="2026-11-12", review_scope="all rows, unsigned")
    assert provenance.problems(root, env={}) == []                              # an owner statement is recorded as such, not as verification


def test_owner_statement_needs_reviewer_date_and_scope(root):
    write_prov(root, review="owner_statement_unsigned")
    assert any("needs reviewer, review_date and review_scope" in p for p in provenance.problems(root, env={}))


def _signed_record(root, **payload_changes):
    payload = {"suite": "a", "dataset": "datasets/a.jsonl", "dataset_sha256": attestation.sha256_file(root / "datasets/a.jsonl"),
               "split": "held_out", "author": "author-a", "reviewer": "reviewer-b", "reviewed_at": "2026-11-12", **payload_changes}
    (root / "reviews").mkdir(exist_ok=True)
    (root / "reviews/a.json").write_text(json.dumps({"payload": payload, "signature": attestation.sign(payload, REVIEWER)}))


def test_verified_review_needs_a_signed_independent_record_bound_to_the_hash(root):
    meta = dict(review="human_reviewed_verified", reviewer="reviewer-b", review_date="2026-11-12", review_scope="all rows")
    write_prov(root, **meta)
    assert any("no record" in p for p in provenance.problems(root, env=ENV))                    # declaring it is not enough
    _signed_record(root)
    assert provenance.problems(root, env=ENV) == []
    assert any("cannot verify" in p for p in provenance.problems(root, env={}))                  # CI without the key fails closed
    _signed_record(root, dataset_sha256="0" * 64)
    assert any("does not bind" in p for p in provenance.problems(root, env=ENV))
    _signed_record(root, reviewer="Author-A")
    assert any("does not bind" in p for p in provenance.problems(root, env=ENV))
    (root / "reviews/a.json").write_text('{"payload": {}, "signature": "approved"}')
    assert provenance.problems(root, env=ENV)


@pytest.mark.parametrize("text", ["", "[]", "min_n: 0\ndatasets: {}", "min_n: 30\ndatasets: []", "{"])
def test_malformed_provenance_file_is_one_problem_not_a_crash(tmp_path, text):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "provenance.yaml").write_text(text)
    assert len(provenance.problems(tmp_path, env={})) == 1


def test_unreadable_dataset_is_a_problem(root):
    (root / "datasets/a.jsonl").write_text("[1]\n")
    write_prov(root)
    assert any("unreadable" in p for p in provenance.problems(root, env={}))
