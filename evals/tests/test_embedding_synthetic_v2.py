"""Offline checks for the reviewed synthetic benchmark v2. Reads files only; no provider, network or app imports."""
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_embedding_eval", EVALS / "run_embedding_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

V1_SHA = "c5382437d5bad1ee823b9286fe163e4bc69b11162bdcbdb152ba4b283ab78b96"
V2_SHA = "a8511afd90b58e0bb82d4c15de5081ab20de92268c0449138f9610fbf054bdac"
V1 = (EVALS / "datasets/embedding_synthetic.jsonl").read_bytes()
V2_BYTES = (EVALS / "datasets/embedding_synthetic_v2.jsonl").read_bytes()
THR1 = yaml.safe_load((EVALS / "embedding_thresholds.yaml").read_text(encoding="utf-8"))
THR2 = yaml.safe_load((EVALS / "embedding_thresholds_v2.yaml").read_text(encoding="utf-8"))
ROWS1 = [json.loads(line) for line in V1.decode("utf-8").splitlines()]
ROWS2 = [json.loads(line) for line in V2_BYTES.decode("utf-8").splitlines()]
RECORDS = [r for r in ROWS2 if r["kind"] == "record"]
QUERIES = [r for r in ROWS2 if r["kind"] == "query"]
EXCLUDED = [r for r in ROWS2 if r["kind"] == "excluded_query"]
SYN = {r["id"]: r for r in ROWS2 if r.get("cohort") == "synonym"}
SCORED = {"SYN-Q041", "SYN-Q047", "SYN-Q056", "SYN-Q059", "SYN-Q063"}
DROPPED = {"SYN-Q037", "SYN-Q038", "SYN-Q040", "SYN-Q039", "SYN-Q042", "SYN-Q043", "SYN-Q044", "SYN-Q045", "SYN-Q046", "SYN-Q048", "SYN-Q052"}


def test_v1_is_unchanged_and_checksums_are_deterministic():
    assert hashlib.sha256(V1).hexdigest() == V1_SHA == THR1["fixture"]["sha256"]
    assert hashlib.sha256(V2_BYTES).hexdigest() == V2_SHA == THR2["fixture"]["sha256"]
    assert THR2["fixture"]["path"] == "datasets/embedding_synthetic_v2.jsonl"
    assert ROWS2[0]["provenance"]["v1_sha256"] == V1_SHA
    # tracked v1 files are byte-identical to the base commit
    out = subprocess.run(["git", "diff", "--stat", "c71ef03", "--", "evals/datasets/embedding_synthetic.jsonl",
                          "evals/embedding_thresholds.yaml"], cwd=EVALS, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""


def test_exact_counts_unique_ids_and_corpus_preserved():
    assert (len(ROWS2), len(RECORDS), len(QUERIES), len(EXCLUDED)) == (161, 96, 53, 11)
    ids = [r["id"] for r in ROWS2 if r["kind"] != "meta"]
    assert len(ids) == len(set(ids)) == 160
    v1_lines, v2_lines = V1.decode().splitlines(), V2_BYTES.decode().splitlines()
    assert [l for l in v1_lines if '"kind": "record"' in l] == [l for l in v2_lines if '"kind": "record"' in l]
    keep = lambda lines: [l for l in lines if '"kind": "query"' in l and '"cohort": "synonym"' not in l]
    assert len(keep(v1_lines)) == 48 and keep(v1_lines) == keep(v2_lines)
    assert {r["id"] for r in SYN.values()} == {r["id"] for r in ROWS1 if r.get("cohort") == "synonym"}
    assert {q["id"] for q in QUERIES if q["cohort"] == "synonym"} == SCORED
    assert {q["id"] for q in EXCLUDED} == DROPPED
    states = [r["vector_state"] for r in RECORDS]
    assert states.count("missing") == 10 and states.count("stale") == 10
    for c, n in THR2["fixture"]["queries_per_cohort"].items():
        assert sum(q["cohort"] == c for q in QUERIES) == n


def test_fixture_passes_the_v1_validator_with_v2_counts():
    thr = copy.deepcopy(THR2)
    assert isinstance(THR1["fixture"]["queries_per_cohort"], int) and isinstance(THR2["fixture"]["queries_per_cohort"], dict)
    assert ev.check_fixture(ROWS2, RECORDS, QUERIES, thr) == []  # mapping accepted; excluded_query rows are not queries
    thr["fixture"]["queries_per_cohort"]["synonym"] = 7
    assert ev.check_fixture(ROWS2, RECORDS, QUERIES, thr) == ["cohort synonym: 5 queries"]
    thr["fixture"]["queries_per_cohort"] = 16  # scalar semantics unchanged for v1
    assert "cohort synonym: 5 queries" in ev.check_fixture(ROWS2, RECORDS, QUERIES, thr)
    assert ev.check_fixture(ROWS1, [r for r in ROWS1 if r["kind"] == "record"],
                            [r for r in ROWS1 if r["kind"] == "query"], THR1) == []
    assert sum(bool(q["constraints"]) for q in QUERIES) == THR2["fixture"]["min_hard_constraint_queries"]
    assert len({t for q in QUERIES for t in q["constraint_types"]}) == 8


def test_reviewed_cases_carry_no_unsupported_attributes():
    for q in QUERIES:
        if q["id"] in SCORED:
            assert "category" not in q["semantic_attrs"]
            assert q["id"] == "SYN-Q056" or q["constraints"] == {}
    # no material other than the explicit wool, no category, no stock/size from dispatch or ambiguous wording
    for q in SYN.values():
        attrs = q.get("semantic_attrs", q.get("supported_attrs"))
        assert set(attrs) <= {"motif", "material", "edge_finish"} and attrs.get("material", "wool") == "wool"
        assert not re.search(r"silk|cotton|pashmina|shawl|stole|scarf|wrap|ship|small|tasselled|neck|cover|drape",
                             q["text"], re.I)
    for qid, attrs in (("SYN-Q038", {"edge_finish": "fringed"}), ("SYN-Q040", {"edge_finish": "fringed", "material": "wool"})):
        assert SYN[qid]["kind"] == "excluded_query" and SYN[qid]["supported_attrs"] == attrs
        assert "edge_finish" in SYN[qid]["reason"] and "outside the current v2 corpus/schema" in SYN[qid]["reason"]
    assert not any("edge_finish" in r or "tasselled" in str(r.get("supported_attrs")) for r in RECORDS + EXCLUDED)
    assert SYN["SYN-Q063"]["constraints"] == {} and SYN["SYN-Q059"]["constraints"] == {}
    assert SYN["SYN-Q056"]["constraints"] == {"color": "grey", "size": "large", "same_variant": True}
    assert SYN["SYN-Q039"]["supported_attrs"] == {} and SYN["SYN-Q039"]["reason"]
    assert all(q["reason"] and "relevant_ids" not in q for q in EXCLUDED)


def test_thresholds_not_relaxed():
    a, b = copy.deepcopy(THR1), copy.deepcopy(THR2)
    assert a["fixture"]["records"] == b["fixture"]["records"] == 96
    assert a["fixture"]["cohorts"] == b["fixture"]["cohorts"]
    assert a["fixture"]["missing_vector_records"] == b["fixture"]["missing_vector_records"]
    assert a["fixture"]["stale_vector_records"] == b["fixture"]["stale_vector_records"]
    for k in ("path", "sha256", "queries", "queries_per_cohort", "min_hard_constraint_queries"):
        a["fixture"].pop(k), b["fixture"].pop(k)
    assert a == b  # every metric, constraint, vector, exclusion, fallback, reproducibility and bounds value is identical
    assert THR2["fallback"]["allowed"] is False and THR2["constraints"]["hard_violations"]["max"] == 0


def test_no_secrets_urls_or_customer_data():
    text = V2_BYTES.decode("utf-8")
    assert not ev.LEAK.search(json.dumps(ROWS2, ensure_ascii=False))
    assert not re.search(r"sk-|api[_-]?key|secret|password|token", text, re.I)
    assert all(re.fullmatch(r"SYN-[RQ]\d{3}", r["id"]) for r in ROWS2 if r["kind"] != "meta")
    assert all(r["name"].startswith("Sample Loom ") for r in RECORDS)


def test_recorded_v2_run_is_not_evaluated_and_release_false(tmp_path, capsys):
    rep = tmp_path / "r.json"
    args = ["--synthetic-only", "--recorded", "--thresholds", str(EVALS / "embedding_thresholds_v2.yaml"), "--report", str(rep)]
    assert ev.main(args, env={}) == 3
    r = json.loads(rep.read_text(encoding="utf-8"))
    assert r["semantic_metrics"] == "NOT_EVALUATED" and r["release_ready"] is False and r["gates"]["failed_metrics"] == []
    assert "release_ready=false" in capsys.readouterr().out


def test_provenance_and_release_flags_stay_false():
    rev = ROWS2[0]["provenance"]["review"]
    assert (rev["reviewer"], rev["date"], rev["batches"], rev["model_evaluated"]) == ("Hamza", "2026-10-30", 4, False)
    assert rev["external_signoff"].startswith("none: no external reviewer") and "not yet model-evaluated" in rev["external_signoff"]
    doc = (EVALS.parent / "docs/qa/embedding-synthetic-v2-review.md").read_text(encoding="utf-8")
    assert V1_SHA in doc and V2_SHA in doc and "not yet model-evaluated" in doc and "2026-10-30" in doc
    tpl = (EVALS.parent / "docs/qa/embedding-provider-evaluation-template.md").read_text(encoding="utf-8")
    assert "embedding-synthetic-v2-review.md" in tpl and V1_SHA in tpl
    spec2 = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
    run_evals = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(run_evals)
    assert run_evals.main([]) == 0 and run_evals.main(["--release-ready"]) == 3
    assert "embedding" not in (EVALS / "thresholds.yaml").read_text(encoding="utf-8")
