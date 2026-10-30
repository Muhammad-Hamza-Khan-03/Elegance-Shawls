"""Offline tests for the synthetic embedding gate. No test reaches a network: live paths use httpx.MockTransport."""
import hashlib
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml

EVALS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALS.parent / "apps" / "backend"))
spec = importlib.util.spec_from_file_location("run_embedding_eval", EVALS / "run_embedding_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

THR = yaml.safe_load((EVALS / "embedding_thresholds.yaml").read_text(encoding="utf-8"))
RECORDS, QUERIES, DIGEST, ERRORS = ev.load_fixture(EVALS, THR)
BY_ID = {r["id"]: r for r in RECORDS}
SECRET = "sk-TEST-SECRET-KEY"
LIVE_ENV = {"EMBEDDING_EVAL_LIVE": "1", "EMBEDDING_EVAL_ALLOWED_MODELS": "gemini/synthetic-model",
            "EMBEDDING_EVAL_GEMINI_API_KEY": SECRET}
LIVE_ARGS = ["--synthetic-only", "--live", "--no-fallback", "--provider", "gemini", "--model", "synthetic-model",
             "--dimension", "16", "--batch-size", "16", "--timeout", "20", "--max-input-chars", "256", "--repeats", "3",
             "--max-requests", "32", "--max-cost-usd", "2", "--usd-per-million-tokens", "0.1"]


def flag(args, name, value=None):
    """Copy of LIVE_ARGS with `name` removed (value None) or replaced."""
    out, i = [], 0
    while i < len(args):
        if args[i] == name:
            i += 1 if name in ("--no-fallback", "--live") else 2
            if value is not None:
                out += [name, value]
            continue
        out.append(args[i])
        i += 1
    return out


# --- an oracle "embedding model": one-hot category/material/motif, query = mean of its gold records ---------------
AXES = {v: i for i, v in enumerate(["shawl", "stole", "scarf", "wrap", "wool", "silk", "cotton", "pashmina", "floral",
                                    "paisley", "geometric", "striped", "embroidered", "plain", "checked", "tasselled"])}


def onehot(r):
    v = [0.0] * 16
    for k in ("category", "material", "motif"):
        v[AXES[r[k]]] = 1.0
    return v


def oracle_table():
    table = {r["text"]: onehot(r) for r in RECORDS}
    for q in QUERIES:
        vs = [onehot(BY_ID[i]) for i in q["relevant_ids"]]
        table[q["text"]] = [sum(c) / len(vs) for c in zip(*vs)]
    return table


def transport(table, log, fail_first=0, status=200, body=None, mangle=None):
    state = {"n": 0}

    def handler(request):
        log.append(str(request.url))
        state["n"] += 1
        if state["n"] <= fail_first or status != 200:
            return httpx.Response(status if status != 200 else 503, text=body or "upstream down")
        texts = [r["content"]["parts"][0]["text"] for r in json.loads(request.content)["requests"]]
        vecs = [table[t] for t in texts]
        return httpx.Response(200, json={"embeddings": [{"values": mangle(v) if mangle else v} for v in vecs]})
    return httpx.MockTransport(handler)


def live(tmp_path, args=None, env=None, tr=None, root=EVALS):
    rep = tmp_path / "rep.json"
    code = ev.main((args or LIVE_ARGS) + ["--report", str(rep), "--root", str(root)], env=LIVE_ENV if env is None else env, transport=tr)
    return code, (json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else None)


# --- corpus ----------------------------------------------------------------------------------------------------

def test_exact_corpus_counts_and_checksum_lock():
    assert ERRORS == []
    assert (len(RECORDS), len(QUERIES)) == (96, 64)
    assert {c: sum(q["cohort"] == c for q in QUERIES) for c in ev.COHORTS} == {c: 16 for c in ev.COHORTS}
    assert sum(bool(q["constraints"]) for q in QUERIES) >= 16
    assert [r["vector_state"] for r in RECORDS].count("missing") == 10
    assert [r["vector_state"] for r in RECORDS].count("stale") == 10
    assert DIGEST == hashlib.sha256((EVALS / "datasets/embedding_synthetic.jsonl").read_bytes()).hexdigest() == THR["fixture"]["sha256"]


def test_constraint_coverage_gold_and_same_variant_decoys():
    kinds = {t for q in QUERIES for t in q["constraint_types"]}
    assert kinds == {"price_min", "price_max", "stock", "category", "material", "color", "size", "same_variant"}
    for q in QUERIES:
        for rid in q["relevant_ids"]:
            assert BY_ID[rid]["vector_state"] == "ok" and ev.satisfies(BY_ID[rid], q["constraints"])
    for q in QUERIES:
        if "same_variant" in q["constraint_types"]:  # a product has the colour and the size, but never on one variant
            c, s = q["constraints"]["color"], q["constraints"]["size"]
            split = [p for p in {r["product"] for r in RECORDS}
                     if any(r["color"] == c for r in RECORDS if r["product"] == p) and any(r["size"] == s for r in RECORDS if r["product"] == p)
                     and not any(r["color"] == c and r["size"] == s for r in RECORDS if r["product"] == p)]
            assert split


def test_privacy_scan_synthetic_only():
    blob = (EVALS / "datasets/embedding_synthetic.jsonl").read_text(encoding="utf-8")
    assert not ev.LEAK.search(blob)
    body = "\n".join(blob.splitlines()[1:])  # the provenance line carries an ISO review date, which is not a phone number
    assert not re.search(r"https?:|[\w.]+@[\w.]+|\+?\d[\d\s-]{9,}", body)
    assert all(re.fullmatch(r"SYN-[RPQ]\d+", i) for r in RECORDS + QUERIES for i in [r["id"]] + ([r["product"]] if "product" in r else []))
    assert all(r["name"].startswith("Sample Loom ") for r in RECORDS)
    real = json.loads((EVALS / "fixtures/retrieval_catalogue.json").read_text(encoding="utf-8")) \
        + json.loads((EVALS / "fixtures/hybrid_catalogue.json").read_text(encoding="utf-8"))
    names = {p["name"].lower() for p in real if len(p["name"].split()) > 1}  # one-word names are just category words
    assert not any(n in blob.lower() for n in names)


def test_thresholds_encode_the_contract():
    t = THR
    assert t["retrieval"]["overall"] == {"recall_at_10": {"min": 0.85}, "mrr_at_10": {"min": 0.70}, "ndcg_at_10": {"min": 0.75}}
    assert t["retrieval"]["cohort"] == {"recall_at_10": {"min": 0.80}, "mrr_at_10": {"min": 0.60}, "ndcg_at_10": {"min": 0.65}}
    assert t["constraints"]["hard_violations"] == {"max": 0} and t["exclusion"]["missing_or_stale_ranked"] == {"max": 0}
    assert all(t["vectors"][k] == {"min": 1.0} for k in ("count_match", "finite", "stable_dimension"))
    assert t["fallback"]["allowed"] is False and t["reproducibility"]["top10_jaccard"] == {"min": 0.99}
    assert t["bounds"] == {"max_batch": 16, "max_input_chars": 256, "max_requests": 32, "timeout_s": 20, "max_repeats": 3,
                           "max_candidates": 4, "max_cost_usd": 2, "max_transport_retries": 1}


# --- metric math -----------------------------------------------------------------------------------------------

def test_metric_math():
    m = ev.query_metrics(["x", "g1", "y", "g2"], ["g1", "g2", "g3"])
    assert m["recall_at_10"] == pytest.approx(2 / 3)
    assert m["mrr_at_10"] == pytest.approx(1 / 2)
    dcg = 1 / 1.5849625007 * 0 + 1 / 1.5849625007 + 1 / 2.321928095  # ranks 2 and 4
    idcg = 1 + 1 / 1.5849625007 + 0.5
    assert m["ndcg_at_10"] == pytest.approx(dcg / idcg)
    assert ev.query_metrics(["g"], ["g"]) == {"recall_at_10": 1.0, "mrr_at_10": 1.0, "ndcg_at_10": 1.0}
    assert ev.query_metrics(["a"], ["g"]) == {"recall_at_10": 0.0, "mrr_at_10": 0.0, "ndcg_at_10": 0.0}
    assert ev.jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3) and ev.jaccard([], []) == 1.0
    assert ev.cosine([1, 0], [1, 1]) == pytest.approx(2 ** -0.5)


def test_vector_validation_rates():
    assert ev.check_vectors([[1.0, 2.0], [0.5, 1]], 2) == {"finite": 1.0, "stable_dimension": 1.0}
    bad = ev.check_vectors([[1.0, float("nan")], [0.0, 0.0], [True, 1.0], [1.0]], 2)
    assert bad == {"finite": 0.25, "stable_dimension": 0.75}  # only the short [1.0] is finite and non-zero
    assert ev.check_vectors([[float("inf"), 1.0]], 2)["finite"] == 0.0


# --- ranking guarantees ----------------------------------------------------------------------------------------

def tiny_records():
    base = {"category": "shawl", "material": "wool", "color": "red", "size": "small", "stock": 5}
    return [{"id": "SYN-R001", "vector_state": "ok", "price": 1000, **base},
            {"id": "SYN-R002", "vector_state": "ok", "price": 9000, **base},          # perfect match, breaks price_max
            {"id": "SYN-R003", "vector_state": "stale", "price": 1000, **base},       # perfect match, stale
            {"id": "SYN-R004", "vector_state": "missing", "price": 1000, **base},
            {"id": "SYN-R005", "vector_state": "ok", "price": 1000, **{**base, "stock": 0}}]


def test_hard_constraints_are_never_overridden_by_similarity():
    recs = tiny_records()
    vecs = {"SYN-R001": [0.5, 1.0], "SYN-R002": [1.0, 0.0], "SYN-R003": [1.0, 0.0], "SYN-R004": [1.0, 0.0], "SYN-R005": [1.0, 0.0]}
    q = [1.0, 0.0]
    assert ev.rank(q, recs, vecs, {"price_max": 2000, "in_stock": True}) == ["SYN-R001"]
    assert ev.rank(q, recs, vecs, {}) == ["SYN-R002", "SYN-R005", "SYN-R001"]  # stale/missing never appear, even as exact matches
    assert ev.rank(q, recs, vecs, {"price_min": 5000}) == ["SYN-R002"]
    assert ev.rank(q, recs, vecs, {"color": "blue"}) == []


def test_same_variant_needs_colour_and_size_on_one_record():
    a = {"id": "A", "price": 1, "stock": 1, "category": "shawl", "material": "wool", "color": "red", "size": "large", "vector_state": "ok"}
    b = {**a, "id": "B", "color": "blue", "size": "small"}
    c = {"color": "red", "size": "small", "same_variant": True}
    assert not ev.satisfies(a, c) and not ev.satisfies(b, c)  # each half exists in the product, never together


def test_oracle_vectors_pass_every_gate_and_exclusion_holds():
    table = oracle_table()
    rv = {r["id"]: table[r["text"]] for r in RECORDS}  # stale/missing vectors present too: they must still be ignored
    qv = {q["id"]: table[q["text"]] for q in QUERIES}
    m = ev.evaluate(RECORDS, QUERIES, [qv, qv], [rv, rv])
    m["vectors"] = {"count_match": 1.0, "finite": 1.0, "stable_dimension": 1.0}
    g = ev.check_gates(m, THR, True)
    assert g["failed"] == [] and g["semantic"] == "pass", g
    assert m["constraints"]["violations"] == 0 and m["constraints"]["unconstrained_ranking_would_violate_queries"] > 0
    assert m["exclusion"]["missing_or_stale_ranked"] == 0
    assert m["coverage"] == {"records": 96, "scored": 76, "missing": 10, "stale": 10, "scored_fraction": 76 / 96}


def test_bad_semantics_fail_quality_gates_not_constraints():
    table = oracle_table()
    texts = sorted(table)
    shuffled = {t: table[texts[(i + 37) % len(texts)]] for i, t in enumerate(texts)}
    rv = {r["id"]: shuffled[r["text"]] for r in RECORDS}
    qv = {q["id"]: shuffled[q["text"]] for q in QUERIES}
    m = ev.evaluate(RECORDS, QUERIES, [qv, qv], [rv, rv])
    m["vectors"] = {"count_match": 1.0, "finite": 1.0, "stable_dimension": 1.0}
    g = ev.check_gates(m, THR, True)
    assert g["semantic"] == "fail" and "recall_at_10[overall]" in g["failed"] and "hard_constraints" not in g["failed"]


def test_repeat_gate_needs_near_identical_top10():
    table = oracle_table()
    rv = {r["id"]: table[r["text"]] for r in RECORDS}
    qv = {q["id"]: table[q["text"]] for q in QUERIES}
    drifted = {k: v[::-1] for k, v in qv.items()}
    m = ev.evaluate(RECORDS, QUERIES, [qv, drifted], [rv, rv])
    m["vectors"] = {"count_match": 1.0, "finite": 1.0, "stable_dimension": 1.0}
    assert m["reproducibility"]["top10_jaccard"] < 0.99
    assert "reproducibility" in ev.check_gates(m, THR, True)["failed"]
    assert ev.check_gates({**m, "reproducibility": {"top10_jaccard": None}}, THR, True)["reproducibility"] == "fail"  # one repeat proves nothing


# --- recorded mode ---------------------------------------------------------------------------------------------

def test_recorded_is_not_evaluated_exit_3_and_offline(tmp_path, monkeypatch, capsys):
    def no_net(*a, **k):
        raise AssertionError("network used in recorded mode")
    monkeypatch.setattr(socket, "socket", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)
    rep = tmp_path / "r.json"
    assert ev.main(["--synthetic-only", "--recorded", "--report", str(rep)], env={}) == 3
    r = json.loads(rep.read_text(encoding="utf-8"))
    assert r["semantic_metrics"] == "NOT_EVALUATED" and r["release_ready"] is False and r["outcome"] == "NOT_EVALUATED"
    assert r["gates"]["failed_metrics"] == [] and r["gates"]["semantic"] == "not_evaluated"
    assert r["constraints"]["violations"] == 0 and r["exclusion"]["missing_or_stale_ranked"] == 0
    assert r["reproducibility"]["top10_jaccard"] == 1.0 and r["usage"]["requests"] <= 32
    assert r["coverage"]["missing"] == 10 and r["coverage"]["stale"] == 10 and "retrieval" not in r
    assert "release_ready=false" in capsys.readouterr().out


def test_recorded_run_imports_no_provider_http_or_app_modules():
    code = ("import sys; sys.path.insert(0, %r); import run_embedding_eval as m; "
            "rc = m.main(['--synthetic-only','--recorded'], env={}); "
            "print(rc, sorted(x for x in ('embeddings','httpx','fastapi','sqlalchemy','redis','database','configuration') if x in sys.modules))"
            % str(EVALS))
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout.split("\n")[-2]
    assert out == "3 []"


def test_semantic_readiness_never_flips_existing_release_flags():
    spec2 = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
    run_evals = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(run_evals)
    assert run_evals.main([]) == 0 and run_evals.main(["--release-ready"]) == 3
    assert "embedding" not in (EVALS / "thresholds.yaml").read_text(encoding="utf-8")


def test_recorded_rejects_live_flags_and_fixture_tampering(tmp_path, capsys):
    assert ev.main(["--synthetic-only", "--recorded", "--provider", "gemini"], env={}) == 2
    root = tmp_path / "evals"
    shutil.copytree(EVALS, root, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    ds = root / "datasets/embedding_synthetic.jsonl"
    ds.write_text(ds.read_text(encoding="utf-8").replace("Sample Loom 001", "Sample Loom 00X"), encoding="utf-8")
    assert ev.main(["--synthetic-only", "--recorded", "--root", str(root)], env={}) == 2
    assert "checksum" in capsys.readouterr().out
    ds.unlink()
    assert ev.main(["--synthetic-only", "--recorded", "--root", str(root)], env={}) == 2  # missing fixture is never a pass


# --- flags, bounds, policy -------------------------------------------------------------------------------------

def test_synthetic_only_and_mode_are_mandatory():
    for argv in (["--recorded"], ["--synthetic-only"], ["--synthetic-only", "--recorded", "--live"]):
        with pytest.raises(SystemExit) as e:
            ev.main(argv, env={})
        assert e.value.code == 2


def test_live_refusals(tmp_path):
    calls = []
    tr = transport(oracle_table(), calls)
    assert live(tmp_path, env={**LIVE_ENV, "EMBEDDING_EVAL_LIVE": "0"}, tr=tr)[0] == 2
    assert live(tmp_path, env={k: v for k, v in LIVE_ENV.items() if k != "EMBEDDING_EVAL_LIVE"}, tr=tr)[0] == 2
    assert live(tmp_path, flag(LIVE_ARGS, "--no-fallback"), tr=tr)[0] == 2
    for name in ("--provider", "--model", "--dimension", "--batch-size", "--timeout", "--max-input-chars", "--repeats",
                 "--max-requests", "--max-cost-usd", "--usd-per-million-tokens"):
        assert live(tmp_path, flag(LIVE_ARGS, name), tr=tr)[0] == 2, name
    for name, bad in (("--batch-size", "17"), ("--timeout", "21"), ("--max-input-chars", "257"), ("--repeats", "4"),
                      ("--repeats", "1"), ("--max-requests", "33"), ("--max-cost-usd", "2.5"), ("--batch-size", "0")):
        assert live(tmp_path, flag(LIVE_ARGS, name, bad), tr=tr)[0] == 2, (name, bad)
    assert live(tmp_path, flag(LIVE_ARGS, "--max-input-chars", "100"), tr=tr)[0] == 2  # shorter than the longest fixture text
    for var in ev.APP_ENV:
        assert live(tmp_path, env={**LIVE_ENV, var: "x"}, tr=tr)[0] == 2, var
    assert calls == []  # every refusal happened before any provider call


def test_blocked_and_unsupported_candidates_make_no_calls(tmp_path):
    calls = []
    tr = transport(oracle_table(), calls)
    no_allow = {k: v for k, v in LIVE_ENV.items() if k != "EMBEDDING_EVAL_ALLOWED_MODELS"}
    for env in (no_allow, {**LIVE_ENV, "EMBEDDING_EVAL_ALLOWED_MODELS": "gemini/other-model"},
                {k: v for k, v in LIVE_ENV.items() if k != "EMBEDDING_EVAL_GEMINI_API_KEY"}):
        code, r = live(tmp_path, env=env, tr=tr)
        assert code == 2 and r["outcome"] == "blocked_by_policy"
    env = {**LIVE_ENV, "EMBEDDING_EVAL_ALLOWED_MODELS": "groq/some-model", "EMBEDDING_EVAL_GROQ_API_KEY": SECRET}
    code, r = live(tmp_path, flag(flag(LIVE_ARGS, "--provider", "groq"), "--model", "some-model"), env=env, tr=tr)
    assert code == 2 and r["outcome"] == "unsupported"
    assert calls == []


# --- live path (mock transport only) ---------------------------------------------------------------------------

def test_live_pass_is_bounded_single_candidate_and_does_not_set_release(tmp_path, capsys):
    calls = []
    code, r = live(tmp_path, tr=transport(oracle_table(), calls))
    assert code == 0 and r["outcome"] == "passed", r
    assert r["candidate"] == {"provider": "gemini", "model": "synthetic-model"}
    assert r["release_ready"] is False and r["release_flags_changed"] is False and r["fallback"] == {"allowed": False, "used": False}
    assert r["usage"]["requests"] == len(calls) == 27 and r["usage"]["texts_per_repeat"] == 140  # 76 current records + 64 queries
    assert all("generativelanguage.googleapis.com" in u and "synthetic-model:batchEmbedContents" in u for u in calls)
    assert r["semantic_metrics"]["overall"]["recall_at_10"] >= 0.85
    assert r["gates"]["failed_metrics"] == [] and r["reproducibility"]["repeats"] == 3
    assert r["usage"]["estimated_cost_usd"] <= 2


def test_report_and_output_are_redacted(tmp_path, capsys):
    code, r = live(tmp_path, tr=transport(oracle_table(), []))
    out = capsys.readouterr()
    blob = json.dumps(r, ensure_ascii=False) + out.out + out.err
    assert SECRET not in blob and "http" not in blob and "googleapis" not in blob
    assert not any(rec["text"] in blob for rec in RECORDS) and not any(q["text"] in blob for q in QUERIES)
    assert not any(isinstance(v, list) and v and isinstance(v[0], float) for v in r.values())
    assert set(r["constraints"]) == {"queries", "violations", "violating_query_ids", "unconstrained_ranking_would_violate_queries"}


def test_one_transport_retry_is_counted_and_a_second_failure_stops(tmp_path):
    calls = []
    code, r = live(tmp_path, tr=transport(oracle_table(), calls, fail_first=1))
    assert code == 0 and r["usage"]["transport_retries"] == 1
    calls.clear()
    code, r = live(tmp_path, tr=transport(oracle_table(), calls, status=500, body=f"boom {SECRET} http://x.example secret-body"))
    assert code == 1 and r["outcome"] == "failed_budget_or_timeout" and len(calls) == 2  # original + exactly one retry
    assert "secret-body" not in json.dumps(r) and SECRET not in json.dumps(r) and r["errors"] == ["provider_request_failed"]


def test_non_retryable_status_is_not_retried(tmp_path):
    calls = []
    code, r = live(tmp_path, tr=transport(oracle_table(), calls, status=401))
    assert code == 1 and r["outcome"] == "failed_budget_or_timeout" and len(calls) == 1


def test_malformed_vectors_fail_validation(tmp_path):
    code, r = live(tmp_path, tr=transport(oracle_table(), [], mangle=lambda v: v[:-1]))
    assert code == 1 and r["outcome"] == "failed_validation" and r["errors"] == ["malformed_response"]
    code, r = live(tmp_path, tr=transport(oracle_table(), [], mangle=lambda v: [0.0] * 16))
    assert code == 1 and r["outcome"] == "failed_validation" and "vector_finite" in r["gates"]["failed_metrics"]


def test_poor_semantics_is_failed_quality(tmp_path):
    table = oracle_table()
    texts = sorted(table)
    shuffled = {t: table[texts[(i + 37) % len(texts)]] for i, t in enumerate(texts)}
    code, r = live(tmp_path, tr=transport(shuffled, []))
    assert code == 1 and r["outcome"] == "failed_quality" and r["constraints"]["violations"] == 0


def test_cost_cap_stops_before_any_call(tmp_path):
    calls = []
    code, r = live(tmp_path, flag(LIVE_ARGS, "--usd-per-million-tokens", "100000"), tr=transport(oracle_table(), calls))
    assert code == 1 and r["outcome"] == "failed_budget_or_timeout" and r["errors"] == ["preflight_cap"] and calls == []


def test_request_cap_stops_before_any_call(tmp_path):
    calls = []
    code, r = live(tmp_path, flag(LIVE_ARGS, "--max-requests", "26"), tr=transport(oracle_table(), calls))
    assert code == 1 and r["errors"] == ["preflight_cap"] and calls == []


def test_runner_has_no_discovery_fallback_or_app_imports():
    src = (EVALS / "run_embedding_eval.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+(fastapi|sqlalchemy|redis|database|configuration|search|workers|main)\b", src, re.M)
    assert "list_models" not in src and "models.list" not in src and "fallback_provider" not in src
    assert THR["bounds"]["max_candidates"] >= 1 and src.count("build_provider(") == 1  # one candidate per invocation


# --- QA fixes: price comparators and corpus provenance -----------------------------------------------------------

def strict_gold(q):
    """Gold recomputed with the natural-language reading: above/greater/zyada is >, less than/kam is <."""
    c = q["constraints"]
    return {r["id"] for r in RECORDS if r["vector_state"] == "ok" and all(r[k] == v for k, v in q["semantic_attrs"].items())
            and ev.satisfies(r, {k: v for k, v in c.items() if not k.startswith("price")})
            and ("price_min" not in c or r["price"] > c["price_min"]) and ("price_max" not in c or r["price"] < c["price_max"])}


def test_price_queries_have_no_equality_boundary_mismatch():
    ids = ["SYN-Q049", "SYN-Q050", "SYN-Q057", "SYN-Q058"]
    by_q = {q["id"]: q for q in QUERIES}
    for qid in ids:
        q = by_q[qid]
        bound = q["constraints"].get("price_min", q["constraints"].get("price_max"))
        assert str(bound) in q["text"]                         # the words quote the encoded bound
        assert not any(r["price"] == bound for r in RECORDS)   # nothing sits on the boundary, in any vector state
        assert strict_gold(q) == set(q["relevant_ids"])        # strict wording and the inclusive evaluator agree
    for q in QUERIES:  # every price-constrained query in the corpus, not only those four
        if {"price_min", "price_max"} & set(q["constraints"]):
            assert q["id"] in ids and strict_gold(q) == set(q["relevant_ids"])


def test_every_gold_set_matches_its_metadata():
    for q in QUERIES:
        derived = {r["id"] for r in RECORDS if r["vector_state"] == "ok" and ev.satisfies(r, q["constraints"])
                   and all(r[k] == v for k, v in q["semantic_attrs"].items())}
        assert derived == set(q["relevant_ids"]), q["id"]


def test_boundary_and_gold_consistency_are_enforced_by_the_evaluator():
    rows = [json.loads(line) for line in (EVALS / "datasets/embedding_synthetic.jsonl").read_text(encoding="utf-8").splitlines()]
    recs = [r for r in rows if r["kind"] == "record"]
    qs = [r for r in rows if r["kind"] == "query"]
    q = next(r for r in qs if r["id"] == "SYN-Q049")
    q["constraints"] = {"price_min": recs[0]["price"]}  # lands exactly on an attained price
    assert any("SYN-Q049" in e and "attained price" in e for e in ev.check_fixture(rows, recs, qs, THR))
    q["constraints"], q["relevant_ids"] = {}, q["relevant_ids"][:1]  # gold now misses matching records
    assert any("SYN-Q049" in e and "gold differs" in e for e in ev.check_fixture(rows, recs, qs, THR))


def test_queries_per_cohort_accepts_scalar_or_mapping_and_ignores_excluded_queries():
    rows = [json.loads(line) for line in (EVALS / "datasets/embedding_synthetic.jsonl").read_text(encoding="utf-8").splitlines()]
    recs = [r for r in rows if r["kind"] == "record"]
    qs = [r for r in rows if r["kind"] == "query"]
    rows.append({**qs[0], "id": "SYN-Q900", "kind": "excluded_query"})  # never counted: only kind=query rows are
    thr = json.loads(json.dumps(THR))
    assert ev.check_fixture(rows, recs, qs, thr) == []
    thr["fixture"]["queries_per_cohort"] = {c: 16 for c in thr["fixture"]["cohorts"]}
    assert ev.check_fixture(rows, recs, qs, thr) == []
    thr["fixture"]["queries_per_cohort"]["synonym"] = 5
    assert ev.check_fixture(rows, recs, qs, thr) == ["cohort synonym: 16 queries"]


def test_provenance_record_and_review_doc_make_no_false_claims():
    rows = [json.loads(line) for line in (EVALS / "datasets/embedding_synthetic.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = [r for r in rows if r["kind"] == "meta"]
    assert len(meta) == 1 and len(RECORDS) == 96 and len(QUERIES) == 64
    rev = meta[0]["provenance"]["review"]
    assert rev["date"] == "2026-10-30" and "AI assistant" in rev["reviewer_role"]
    assert "96 records" in rev["scope"] and "64 query gold sets" in rev["scope"]
    assert rev["external_signoff"].startswith("none") and "native-speaker" in rev["external_signoff"]
    doc = (EVALS.parent / "docs/qa/embedding-provider-evaluation-template.md").read_text(encoding="utf-8")
    assert THR["fixture"]["sha256"] in doc  # the reviewed checksum is the pinned one
    assert "No external human, native-speaker or domain-expert review" in doc


# --- local e5 (model loader mocked: no download, no network) -----------------------------------------------------

LOCAL_ENV = {"EMBEDDING_EVAL_LIVE": "1"}
LOCAL_ARGS = ["--synthetic-only", "--live", "--no-fallback", "--provider", "local_e5", "--model", "intfloat/multilingual-e5-base",
              "--batch-size", "16", "--timeout", "20", "--max-input-chars", "256", "--repeats", "2", "--max-requests", "32"]


class LocalFake:
    def __init__(self):
        self.seen = []

    def encode(self, texts, **kw):
        self.seen.append(list(texts))
        return [[(b - 128) / 128 for b in hashlib.sha256(t.encode()).digest()] * 24 for t in texts]  # 32 * 24 = 768 dims


@pytest.fixture
def local_model(monkeypatch):
    from embeddings.providers import local_e5
    m = LocalFake()
    monkeypatch.setattr(local_e5, "_load_model", lambda ref, cache: m)
    return m


@pytest.fixture
def mdir(tmp_path):
    d = tmp_path / "e5"
    d.mkdir()
    (d / "config.json").write_text("{}")
    from embeddings.providers.local_e5 import model_tree_digest
    return d, model_tree_digest(d)


def test_local_e5_is_local_only_prefixed_and_reported_without_raw_data(tmp_path, local_model, mdir, capsys):
    d, rev = mdir
    code, r = live(tmp_path, LOCAL_ARGS + ["--local-model-path", str(d), "--local-model-revision", rev], env=LOCAL_ENV)
    assert code == 1 and r["outcome"] == "failed_quality"  # a hash is not semantic; the evaluator must still run end to end
    assert r["candidate"] == {"provider": "local_e5", "model": "intfloat/multilingual-e5-base", "model_revision": rev,
                              "timeout_enforcement": "thread_abandoned_fail_closed_no_hard_kill"}
    assert r["vectors"]["dimension"] == 768
    assert r["release_ready"] is False and r["release_flags_changed"] is False and r["fallback"] == {"allowed": False, "used": False}
    batches = local_model.seen
    assert {t.split(": ")[0] for b in batches for t in b} == {"passage", "query"}
    assert all(len({t.split(": ")[0] for t in b}) == 1 for b in batches)  # a batch never mixes queries and passages
    assert sum(t.startswith("query: ") for b in batches for t in b) == 2 * len(QUERIES)
    blob = json.dumps(r, ensure_ascii=False) + capsys.readouterr().out
    assert not any(q["text"] in blob for q in QUERIES) and str(d) not in blob


def test_local_e5_refusals_and_typed_blocks(tmp_path, local_model, mdir):
    d, rev = mdir
    ok = LOCAL_ARGS + ["--local-model-path", str(d), "--local-model-revision", rev]
    assert live(tmp_path, ok, env={**LOCAL_ENV, "EMBEDDING_EVAL_GEMINI_API_KEY": SECRET})[0] == 2  # credential present
    assert live(tmp_path, flag(ok, "--no-fallback"), env=LOCAL_ENV)[0] == 2
    assert live(tmp_path, ok, env={**LOCAL_ENV, "DATABASE_URL": "x"})[0] == 2
    assert live(tmp_path, LIVE_ARGS + ["--local-model-path", "/m"])[0] == 2  # local flags with a remote provider
    assert live(tmp_path, LIVE_ARGS + ["--local-model-revision", rev])[0] == 2
    assert ev.main(["--synthetic-only", "--recorded", "--local-model-path", "/m"], env={}) == 2
    assert ev.main(["--synthetic-only", "--recorded", "--local-model-revision", rev], env={}) == 2
    code, r = live(tmp_path, flag(ok, "--model", "intfloat/multilingual-e5-small"), env=LOCAL_ENV)
    assert code == 2 and r["outcome"] == "blocked_by_policy" and local_model.seen == []
    for args, env, err in ((LOCAL_ARGS, {}, "missing_local_model"),  # nothing given: no discovery by model name
                           (LOCAL_ARGS + ["--local-model-path", str(tmp_path / "absent")], {}, "missing_local_model"),
                           (LOCAL_ARGS + ["--local-model-path", str(d)], {}, "unpinned_model"),
                           (LOCAL_ARGS + ["--local-model-path", str(d), "--local-model-revision", "0" * 64], {}, "model_revision_mismatch"),
                           (LOCAL_ARGS, {"EMBEDDING_EVAL_LOCAL_MODEL_PATH": str(d), "EMBEDDING_EVAL_LOCAL_MODEL_REVISION": "0" * 64},
                            "model_revision_mismatch")):
        code, r = live(tmp_path, args, env={**LOCAL_ENV, **env})
        assert code == 2 and r["outcome"] == "blocked_by_policy" and r["errors"] == [err], err
    assert local_model.seen == []
    code, r = live(tmp_path, LOCAL_ARGS, env={**LOCAL_ENV, "EMBEDDING_EVAL_LOCAL_MODEL_PATH": str(d),
                                              "EMBEDDING_EVAL_LOCAL_MODEL_REVISION": rev})
    assert code == 1 and r["candidate"]["model_revision"] == rev  # env fallbacks work
