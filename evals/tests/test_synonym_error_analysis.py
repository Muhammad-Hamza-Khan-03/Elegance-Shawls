"""Offline tests for the synonym error-analysis diagnostic. Pure string matching; nothing here may touch a network."""
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_synonym_error_analysis", EVALS / "run_synonym_error_analysis.py")
sea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sea)

THR = yaml.safe_load((EVALS / "embedding_thresholds.yaml").read_text(encoding="utf-8"))
SCRIPT = (EVALS / "run_synonym_error_analysis.py").read_text(encoding="utf-8")
ALIASES = sea.load_aliases()
EXPECTED = {
    "flower pattern": ("motif", "floral"), "goat-hair fabric": ("material", "pashmina"),
    "blanket-style cover": ("category", "wrap"), "fringe edges": ("motif", "tasselled"),
    "lustrous fabric": ("material", "silk"), "neck piece": ("category", "scarf"),
    "teardrop motif": ("motif", "paisley"), "woollen fabric": ("material", "wool"),
    "square grid design": ("motif", "checked"), "shoulder cover": ("category", "shawl"),
    "long neck drape": ("category", "stole"), "breathable light fabric": ("material", "cotton"),
    "lines running lengthwise": ("motif", "striped"), "angular shapes": ("motif", "geometric"),
    "ready to ship now": ("constraint", "in_stock"),
}


@pytest.fixture(scope="module")
def report():
    rep, errors = sea.build_report()
    assert errors == []
    return rep


def test_fixture_checksum_and_counts(report):
    raw = (EVALS / THR["fixture"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == THR["fixture"]["sha256"] == report["fixture_sha256"]
    assert report["counts"] == {"records": 96, "queries": 64, "synonym_queries": 16}


def test_fixture_tamper_is_refused(tmp_path):
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "embedding_synthetic.jsonl").write_bytes((EVALS / THR["fixture"]["path"]).read_bytes() + b"\n ")
    (tmp_path / "embedding_thresholds.yaml").write_text((EVALS / "embedding_thresholds.yaml").read_text(), encoding="utf-8")
    (tmp_path / "synonym_aliases.yaml").write_text((EVALS / "synonym_aliases.yaml").read_text(), encoding="utf-8")
    assert sea.build_report(tmp_path)[1] == ["fixture sha256 differs from embedding_thresholds.yaml"]


def test_alias_map_is_exactly_the_reviewed_directional_set():
    assert {a["phrase"]: (a["attr"], a["value"]) for a in ALIASES} == EXPECTED
    assert all(a["cohorts"] == ["synonym"] for a in ALIASES)
    assert yaml.safe_load((EVALS / "synonym_aliases.yaml").read_text())["status"] == "prototype_evaluation_only"


def test_alias_direction_has_no_reverse_matches():
    for a in ALIASES:
        canon = {"cohort": "synonym", "text": f"{a['value'].replace('_', ' ')} stuff"}
        assert [h["phrase"] for h in sea.alias_hits(canon, ALIASES)] == []   # canonical word never expands to its phrase
    # a phrase is matched whole: a partial phrase or reordered words do not hit
    for text in ("neck", "piece neck", "flower", "woollen", "grid design square"):
        assert sea.alias_hits({"cohort": "synonym", "text": text}, ALIASES) == []


def test_aliases_only_fire_in_synonym_cohort(report):
    for cohort in ("en", "ur", "roman_ur"):
        assert report["cohorts"][cohort]["alias_expanded"] == report["cohorts"][cohort]["lexical"]
        assert report["cohorts"][cohort]["alias_expanded"]["alias_hits"] == 0
    q = {"cohort": "en", "text": "flower pattern neck piece"}
    assert sea.alias_hits(q, ALIASES) == []
    assert len(sea.alias_hits({**q, "cohort": "synonym"}, ALIASES)) == 2


def test_synonym_before_after_coverage(report):
    syn = [q for q in report["queries"] if q["cohort"] == "synonym"]
    assert len(syn) == 16
    assert report["cohorts"]["synonym"]["lexical"]["complete_queries"] == 0
    assert report["cohorts"]["synonym"]["alias_expanded"]["complete_queries"] == 16
    for q in syn:
        assert q["alias_expanded"]["alias_unexpected"] == []
        assert q["alias_expanded"]["false_positives"] == []
        assert all(q["alias_expanded"]["gold_covered"].values())
        assert not any(q["lexical"]["gold_covered"].values())
    # every one of the 15 aliases is exercised by the synonym queries
    assert {p for q in syn for p in q["alias_expanded"]["alias_hits"]} == set(EXPECTED)


def test_missing_and_stale_never_candidates(report):
    states = {}
    for line in (EVALS / THR["fixture"]["path"]).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["kind"] == "record":
            states[r["id"]] = r["vector_state"]
    excluded = 0
    for q in report["queries"]:
        assert q["gold_available"] == q["gold_ids"] and not q["gold_missing"] and not q["gold_stale"]
        for name in ("lexical", "alias_expanded"):
            s = q[name]
            assert all(states[i] == "ok" for i in s["candidates"])
            assert all(states[i] == "missing" for i in s["excluded_missing"])
            assert all(states[i] == "stale" for i in s["excluded_stale"])
            assert not set(s["candidates"]) & set(s["excluded_missing"] + s["excluded_stale"])
            excluded += len(s["excluded_missing"]) + len(s["excluded_stale"])
    assert excluded > 0   # the exclusion path is actually exercised


def test_hard_constraints_preserved():
    recs = [{"id": "A", "vector_state": "ok", "price": 100, "stock": 0, "category": "wrap", "material": "wool",
             "motif": "plain", "color": "blue", "size": "small"},
            {"id": "B", "vector_state": "ok", "price": 100, "stock": 3, "category": "wrap", "material": "wool",
             "motif": "plain", "color": "blue", "size": "small"}]
    assert sea.candidates(recs, {("material", "wool")}, {"in_stock": True}, "ok") == ["B"]
    assert sea.candidates(recs, set(), {}, "ok") == []


def test_output_is_deterministic_and_text_is_hashed(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert sea.main(["--report", str(a)]) == 0 and sea.main(["--report", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    out = a.read_text(encoding="utf-8")
    for line in (EVALS / THR["fixture"]["path"]).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        assert r["kind"] != "query" or r["text"] not in out   # query text is never emitted (alias phrases are map data)
    assert re.search(r'"text_sha12": "[0-9a-f]{12}"', out)
    assert "NOT semantic embedding quality" in out


def test_no_network_provider_app_or_secret_use():
    code = SCRIPT.split('"""', 2)[2]   # skip the module docstring, which names what is excluded
    imports = set(re.findall(r"^\s*(?:import|from)\s+([\w.]+)", code, re.M))
    assert imports <= {"argparse", "hashlib", "importlib.util", "json", "re", "sys", "pathlib", "yaml"}
    for banned in ("httpx", "requests", "socket", "urllib", "os.environ", "getenv", "embeddings", "database", "redis",
                   "API_KEY", "https://"):
        assert banned not in code


def test_thresholds_and_gold_files_unchanged():
    # compare to the pinned base commit tree when git history is available; otherwise rely on the pinned fixture hash
    base = subprocess.run(["git", "-C", str(EVALS), "rev-parse", "--verify", "-q", "c71ef03^{commit}"],
                          capture_output=True, text=True)
    if base.returncode:
        pytest.skip("base commit unavailable")
    for rel in ("embedding_thresholds.yaml", "thresholds.yaml", "datasets/embedding_synthetic.jsonl",
                "datasets/filter_parsing.jsonl", "datasets/retrieval_constraints.jsonl", "datasets/retrieval_hybrid.jsonl"):
        diff = subprocess.run(["git", "-C", str(EVALS), "diff", "--quiet", "c71ef03", "--", rel])
        assert diff.returncode == 0, rel
