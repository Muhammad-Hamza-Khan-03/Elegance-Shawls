"""The standard report: provenance and sample size on every cohort, honest intervals, low-n flags, circularity, offline reproducibility."""
import json
import math
import shutil
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS))
import circularity  # noqa: E402
import report  # noqa: E402


def test_wilson_matches_known_values_and_stays_in_range():
    low, high = report.wilson(8, 10)
    assert (round(low, 3), round(high, 3)) == (0.490, 0.943)
    assert report.wilson(0, 0) == (0.0, 1.0)
    assert report.wilson(0, 20)[0] == 0.0 and report.wilson(20, 20)[1] == 1.0
    assert report.wilson(1, 17)[0] < 1 / 17 < report.wilson(1, 17)[1]


def test_hoeffding_is_wide_for_small_n_and_clipped():
    low, high = report.hoeffding(0.94, 32)
    assert round(0.94 - low, 3) == round(math.sqrt(math.log(40) / 64), 3) == 0.240 and high == 1.0
    assert report.hoeffding(0.5, 1000)[1] - 0.5 < 0.05
    assert report.hoeffding(0.5, 0) == (0.0, 1.0)


def test_committed_report_and_checksum_reproduce_offline():
    assert report.check(EVALS) == []


def test_report_lists_every_cohort_with_n_interval_and_provenance():
    text = report.render(EVALS)
    results = json.loads((EVALS / "roman_urdu_results.json").read_text(encoding="utf-8"))["cohorts"]
    for key, row in results.items():
        system, cohort = key.split("/")
        assert f"| {system} | {cohort} | {row['n']} | recall@10 |" in text, key
    assert "synthetic_generator" in text and "unreviewed" in text and "Hoeffding" in text
    assert "Synthetic, unreviewed data" in text and "**not** release evidence" in text


def test_low_n_cohorts_are_flagged_and_large_ones_are_not():
    text = report.render(EVALS)
    results = json.loads((EVALS / "roman_urdu_results.json").read_text(encoding="utf-8"))["cohorts"]
    for key, row in results.items():
        system, cohort = key.split("/")
        line = next(l for l in text.splitlines() if l.startswith(f"| {system} | {cohort} | {row['n']} | recall@10"))
        assert ("LOW-N" in line) == (row["n"] < 30), line


def test_roman_urdu_and_synonym_cohorts_are_reported_separately_and_the_gaps_are_stated():
    text = report.render(EVALS)
    assert "| pipeline | roman_ur |" in text and "| pipeline | ur |" in text and "| pipeline | en |" in text
    assert "## Synonym cohort" in text and "LOW-N, no interval is meaningful" in text
    assert "no qualified independent reviewer" in text and "BLOCKED" in text and "not reproduced" in text


def test_heldout_phrasing_is_labelled_synthetic_and_circular_where_it_is():
    text = report.render(EVALS)
    assert "held-out but synthetic, same-author phrasing" in text
    circ = {l.split("|")[1].strip(): l.split("|")[5].strip() for l in text.splitlines() if l.startswith("| ") and l.count("|") == 6 and "%" in l}
    assert circ["ALL"] == "circular" and circ["HELDOUT"] == "circular" and circ["HELDOUT_V3"].startswith("partly independent")


def test_a_tampered_report_or_checksum_is_detected(tmp_path):
    root = tmp_path / "evals"
    shutil.copytree(EVALS, root, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (tmp_path / "apps/backend/catalog").mkdir(parents=True)
    shutil.copy(EVALS.parent / "apps/backend/catalog/vocab.yaml", tmp_path / "apps/backend/catalog/vocab.yaml")
    assert report.check(root) == []
    (root / "reports/cohort_report.md").write_text("edited\n", encoding="utf-8")
    assert len(report.check(root)) == 1                              # the checksum still matches the fresh render, the file does not
    report_text = report.render(root)
    (root / "reports/cohort_report.md").write_text(report_text, encoding="utf-8")
    (root / "reports/cohort_report.sha256").write_text("0" * 64 + "  cohort_report.md\n")
    assert report.check(root) == ["reports/cohort_report.sha256 does not match a fresh render"]
    results = json.loads((root / "roman_urdu_results.json").read_text(encoding="utf-8"))
    results["cohorts"]["pipeline/ALL"]["recall10"] = 0.5            # a changed input makes the committed report stale
    (root / "roman_urdu_results.json").write_text(json.dumps(results))
    assert report.check(root)


# ---- circularity ----

def test_overlap_detects_queries_made_only_of_vocabulary_words():
    vocabulary = {"kala", "shaal", "chahiye"}
    stats = circularity.overlap(["Kala SHAAL chahiye", "kala shaal dikhao", "bilkul alag"], vocabulary)
    assert stats == {"n": 3, "fully_in_vocabulary": 1, "token_coverage": 0.625}
    assert circularity.overlap([], vocabulary) == {"n": 0, "fully_in_vocabulary": 0, "token_coverage": 0.0}


def test_generator_and_production_vocabularies_contain_the_known_shared_words():
    generator, production = circularity.generator_vocabulary(EVALS), circularity.production_vocabulary(EVALS)
    assert {"gulabi", "bhoora", "shaal", "chahiye"} <= generator
    assert "pashmina" in production and "brown" in production
    assert generator & production                                   # the circularity the issue describes: shared words exist


def test_generated_rows_are_detected_as_in_vocabulary_by_construction():
    rows = [json.loads(l) for l in (EVALS / "datasets/roman_urdu_queries.jsonl").read_text(encoding="utf-8").splitlines()]
    generated = [r["q"] for r in rows if not r.get("heldout")]
    stats = circularity.overlap(generated, circularity.generator_vocabulary(EVALS))
    assert stats["fully_in_vocabulary"] / stats["n"] > 0.9


def test_low_n_boundary_is_exactly_below_thirty(tmp_path):
    root = tmp_path / "evals"
    shutil.copytree(EVALS, root, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (tmp_path / "apps/backend/catalog").mkdir(parents=True)
    shutil.copy(EVALS.parent / "apps/backend/catalog/vocab.yaml", tmp_path / "apps/backend/catalog/vocab.yaml")
    results = json.loads((root / "roman_urdu_results.json").read_text(encoding="utf-8"))
    results["cohorts"]["pipeline/en"]["n"], results["cohorts"]["pipeline/ur"]["n"] = 30, 29
    (root / "roman_urdu_results.json").write_text(json.dumps(results))
    lines = report.render(root).splitlines()
    en = next(l for l in lines if l.startswith("| pipeline | en | 30 | recall@10"))
    ur = next(l for l in lines if l.startswith("| pipeline | ur | 29 | recall@10"))
    assert "LOW-N" not in en and "LOW-N" in ur


def test_tokens_split_on_punctuation_and_underscores_and_casefold():
    assert circularity.tokens("Kala-SHAAL, chahiye! (dikhao)_x") == ["kala", "shaal", "chahiye", "dikhao", "x"]
    assert circularity.overlap(["kala, shaal!"], {"kala", "shaal"})["fully_in_vocabulary"] == 1
