"""Review workflow tooling, tested ONLY with synthetic fixtures, fake names and throwaway keys. Nothing here is a real review."""
import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))
import attestation  # noqa: E402
import intake  # noqa: E402
import provenance  # noqa: E402
import review  # noqa: E402

KEY = "k" * 40
ENV = {"EVAL_REVIEWER_KEY": KEY}
ROWS = [{"id": f"r{i}", "q": f"fake query {i}", "lang": "roman_ur"} for i in range(6)]


@pytest.fixture
def root(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets/fixture.jsonl").write_text('{"kind": "meta", "note": "synthetic"}\n' + "".join(json.dumps(r) + "\n" for r in ROWS))
    return tmp_path


def decisions_file(root, name, reviewer, decisions, qualification="fake qualification for tests", date="2026-11-12"):
    packet = review.export_packet(root, "datasets/fixture.jsonl")
    lines = [{"header": {"reviewer": reviewer, "qualification": qualification, "date": date}}]
    lines += [{"id": p["id"], "decision": d, **({"corrected": "x"} if d == "correct" else {})} for p, d in zip(packet, decisions)]
    path = root / name
    path.write_text("".join(json.dumps(l) + "\n" for l in lines))
    return path


def sign(root, files, author="fake author", split="dev", env=ENV):
    return review.sign_record(root, "datasets/fixture.jsonl", files, author, split, env, today="2026-11-12")


# ---- the repository itself: nothing has been reviewed ----

def test_the_repository_contains_no_review_records_and_no_decisions():
    assert not (EVALS / "reviews").exists() or not list((EVALS / "reviews").glob("*.json"))
    assert not list(EVALS.glob("**/decisions*.jsonl"))
    assert not any(e["review"] == "human_reviewed_verified" for e in provenance.load(EVALS)["datasets"].values())


def test_the_documents_state_that_nothing_was_reviewed_and_the_blockers():
    text = (EVALS / "review/README.md").read_text(encoding="utf-8")
    for needle in ("no dataset in this repository has been reviewed", "none may be created by an AI assistant", "has not been identified", "BLOCKED"):
        assert needle in text, needle


# ---- packet, ids, decisions ----

def test_packet_skips_meta_rows_and_ids_are_content_hashes(root):
    packet = review.export_packet(root, "datasets/fixture.jsonl")
    assert len(packet) == 6 and all(p["row"].get("kind") != "meta" for p in packet)
    changed = {**ROWS[0], "q": "different"}
    assert review.row_id(changed) != review.row_id(ROWS[0]) and review.row_id(ROWS[0]) == packet[0]["id"]


def test_valid_decisions_pass_and_every_defect_is_reported(root):
    packet = review.export_packet(root, "datasets/fixture.jsonl")
    good = decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6)
    assert review.decision_problems(packet, good)[2] == []
    short = decisions_file(root, "b.jsonl", "Fake Reviewer A", ["accept"] * 5 + [None])
    lines = short.read_text().splitlines()[:-1]
    short.write_text("\n".join(lines) + "\n")
    assert any("has no valid decision" in p for p in review.decision_problems(packet, short)[2])
    bad = decisions_file(root, "c.jsonl", "", ["accept"] * 6, qualification="")
    assert len([p for p in review.decision_problems(packet, bad)[2] if "header needs" in p]) == 2
    unknown = root / "d.jsonl"
    unknown.write_text(good.read_text() + json.dumps({"id": "ffff", "decision": "accept"}) + "\n" + json.dumps({"id": packet[0]["id"], "decision": "accept"}) + "\n")
    found = " ".join(review.decision_problems(packet, unknown)[2])
    assert "unknown row id" in found and "decided twice" in found
    nodecision = decisions_file(root, "e.jsonl", "Fake Reviewer A", ["maybe"] * 6)
    assert "needs decision" in " ".join(review.decision_problems(packet, nodecision)[2])
    nocorrected = root / "f.jsonl"
    nocorrected.write_text(good.read_text().replace('"decision": "accept"', '"decision": "correct"', 1))
    assert "gives no corrected value" in " ".join(review.decision_problems(packet, nocorrected)[2])


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"header": 5}\n', '{"nope": 1}\n', "\x00"])
def test_garbage_decisions_files_are_one_problem_not_a_crash(root, raw):
    path = root / "g.jsonl"
    path.write_text(raw)
    assert len(review.decision_problems(review.export_packet(root, "datasets/fixture.jsonl"), path)[2]) >= 1


# ---- agreement ----

def test_cohen_kappa_known_values():
    assert review.kappa(["accept"] * 4, ["accept"] * 4) == 1.0
    assert review.kappa(["a", "a", "b", "b"], ["a", "a", "b", "b"]) == 1.0
    assert review.kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)
    assert round(review.kappa(["a", "a", "a", "b"], ["a", "a", "b", "b"]), 3) == 0.5
    with pytest.raises(ValueError):
        review.kappa([], [])
    with pytest.raises(ValueError):
        review.kappa(["a"], ["a", "b"])


# ---- signing ----

def test_one_independent_reviewer_signs_a_record_that_provenance_accepts(root, tmp_path):
    out, problems = sign(root, [decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept", "correct"] * 3)])
    assert problems == [] and out == root / "reviews/fixture.json"
    record = json.loads(out.read_text())
    assert record["payload"]["reviewer"] == "Fake Reviewer A" and record["payload"]["author"] == "fake author"
    assert record["payload"]["dataset_sha256"] == attestation.sha256_file(root / "datasets/fixture.jsonl")
    payload, why = attestation._load_signed(out, KEY, "EVAL_REVIEWER_KEY", attestation.REVIEW_FIELDS)
    assert why is None and payload["suite"] == "fixture"


def test_signing_needs_the_key_and_writes_nothing_otherwise(root):
    files = [decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6)]
    for env in ({}, {"EVAL_REVIEWER_KEY": "short"}):
        out, problems = sign(root, files, env=env)
        assert out is None and "only the reviewer key holder can sign" in problems[0]
    assert not (root / "reviews").exists()


@pytest.mark.parametrize("author,reviewer", [("Fake Reviewer A", "fake reviewer a"), ("Fake  Reviewer A.", "Fake Reviewer A"), ("ｆａｋｅ reviewer a", "Fake Reviewer A")])
def test_the_author_cannot_be_the_reviewer(root, author, reviewer):
    out, problems = sign(root, [decisions_file(root, "a.jsonl", reviewer, ["accept"] * 6)], author=author)
    assert out is None and any("is the dataset author" in p for p in problems)


def test_unresolved_rejects_and_incomplete_coverage_block_signing(root):
    out, problems = sign(root, [decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept", "accept", "reject", "accept", "accept", "accept"])])
    assert out is None and any("is `reject`" in p for p in problems)
    path = decisions_file(root, "b.jsonl", "Fake Reviewer A", ["accept"] * 6)
    path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
    out, problems = sign(root, [path])
    assert out is None and any("has no valid decision" in p for p in problems)


def test_two_reviewers_need_to_be_different_and_to_agree(root):
    a = decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6)
    same = decisions_file(root, "same.jsonl", "fake reviewer a", ["accept"] * 6)
    assert any("same reviewer" in p for p in sign(root, [a, same])[1])
    agree = decisions_file(root, "b.jsonl", "Fake Reviewer B", ["accept"] * 6)
    out, problems = sign(root, [a, agree])
    assert problems == [] and json.loads(out.read_text())["payload"]["reviewer"] == "Fake Reviewer A & Fake Reviewer B"
    (root / "reviews/fixture.json").unlink()
    split = decisions_file(root, "c.jsonl", "Fake Reviewer C", ["accept", "correct", "accept", "correct", "accept", "correct"])
    out, problems = sign(root, [a, split])
    assert out is None and any("agreement is too low" in p for p in problems)


def test_split_and_file_count_are_validated(root):
    a = decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6)
    assert sign(root, [a], split="test")[0] is None
    assert sign(root, [])[0] is None and sign(root, [a, a, a])[0] is None


def test_a_signed_review_record_makes_provenance_accept_verified_only_with_the_key(root):
    import yaml
    out, problems = sign(root, [decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6)])
    assert problems == []
    entry = {"origin": "synthetic_unrecorded", "review": "human_reviewed_verified", "split": "unsplit", "sha256": attestation.sha256_file(root / "datasets/fixture.jsonl"),
             "note": "fixture", "reviewer": "Fake Reviewer A", "review_date": "2026-11-12", "review_scope": "all rows"}
    (root / "provenance.yaml").write_text(yaml.safe_dump({"schema": 1, "min_n": 30, "datasets": {"datasets/fixture.jsonl": entry}}))
    assert provenance.problems(root, env=ENV) == []
    assert any("cannot verify" in p for p in provenance.problems(root, env={}))
    (root / "datasets/fixture.jsonl").write_text((root / "datasets/fixture.jsonl").read_text() + '{"id": "new", "q": "added later"}\n')
    entry["sha256"] = attestation.sha256_file(root / "datasets/fixture.jsonl")        # even re-pinning the hash cannot reuse the old signature
    (root / "provenance.yaml").write_text(yaml.safe_dump({"schema": 1, "min_n": 30, "datasets": {"datasets/fixture.jsonl": entry}}))
    assert any("does not bind" in p for p in provenance.problems(root, env=ENV))


def test_cli_export_refuses_datasets_dir_and_check_and_agree_work(root, tmp_path, capsys):
    assert review.main(["export", "datasets/fixture.jsonl", "--root", str(root), "--out", str(root / "datasets/packet.jsonl")]) == 2
    out = tmp_path / "packet.jsonl"
    assert review.main(["export", "datasets/fixture.jsonl", "--root", str(root), "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 6
    a, b = decisions_file(root, "a.jsonl", "Fake Reviewer A", ["accept"] * 6), decisions_file(root, "b.jsonl", "Fake Reviewer B", ["accept"] * 6)
    assert review.main(["check", "datasets/fixture.jsonl", "--root", str(root), "--decisions", str(a)]) == 0
    assert review.main(["agree", "--root", str(root), "--decisions", str(a), "--decisions", str(b)]) == 0
    assert '"kappa": 1.0' in capsys.readouterr().out


# ---- real-query intake stays blocked ----

def test_intake_refuses_while_blocked_and_reads_nothing(tmp_path):
    assert intake.is_blocked(EVALS)
    missing = tmp_path / "nope.jsonl"
    with pytest.raises(intake.Blocked):
        intake.load_real_queries(missing, EVALS)             # not even opened: no FileNotFoundError
    assert intake.is_blocked(tmp_path)                       # a missing status file also means blocked


@pytest.mark.parametrize("text,kind", [("call me 0300 1234567", "phone number"), ("mail a.b@example.com", "email address"), ("see https://x.example/y", "link"),
                                       ("order ES-AB12CD", "enquiry reference"), ("ping @someone", "handle"), ("pin 1234567", "long digit run"), ("+92 300 1234567", "phone number")])
def test_scrub_patterns_catch_obvious_personal_data(text, kind):
    assert kind in intake.scrub_problems(text)


def test_clean_queries_pass_the_scrub():
    for text in ("kala shaal chahiye", "brown stole under 4000", "سیاہ شال 2500 تک"):
        assert intake.scrub_problems(text) == []


def test_once_unblocked_rows_need_consent_and_a_scrubbed_query(tmp_path):
    (tmp_path / "real_queries_status.md").write_text("Status: UNBLOCKED by the owner (fixture)\n")
    path = tmp_path / "q.jsonl"
    path.write_text(json.dumps({"query": "kala shaal", "consent_ref": "fixture-consent-1", "source": "real"}) + "\n")
    assert len(intake.load_real_queries(path, tmp_path)) == 1
    for row, why in (({"query": "kala shaal", "source": "real"}, "consent_ref"), ({"query": "call 0300 1234567", "consent_ref": "c", "source": "real"}, "personal data"),
                     ({"query": "x", "consent_ref": "c", "source": "synthetic"}, "source 'real'")):
        path.write_text(json.dumps(row) + "\n")
        with pytest.raises(ValueError, match=why) as error:
            intake.load_real_queries(path, tmp_path)
        assert "0300" not in str(error.value)                # the offending text is never echoed
    path.write_text(json.dumps({"query": "A  Shaal", "consent_ref": "c", "source": "real"}) + "\n" + json.dumps({"query": "a shaal", "consent_ref": "c", "source": "real"}) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        intake.load_real_queries(path, tmp_path)
