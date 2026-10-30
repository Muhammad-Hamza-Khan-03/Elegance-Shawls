"""Bounded synthetic embedding evaluation gate (one explicit provider/model candidate per invocation).

  python evals/run_embedding_eval.py --synthetic-only --recorded [--report out.json]       # offline, no network
  EMBEDDING_EVAL_LIVE=1 python evals/run_embedding_eval.py --synthetic-only --live --no-fallback \\
      --provider gemini --model <model> --dimension 768 --batch-size 16 --timeout 20 --max-input-chars 256 \\
      --repeats 3 --max-requests 32 --max-cost-usd 2 --usd-per-million-tokens <price>

Only the fictional corpus in datasets/embedding_synthetic.jsonl is ever sent anywhere, and only when live mode is
asked for explicitly. Recorded mode embeds with a deterministic hash "fake": that proves the evaluator, the hard
constraints, missing/stale exclusion, vector validation, repeatability and the bounds, but a hash is not semantics,
so semantic_metrics is NOT_EVALUATED and release_ready stays false. This runner never sets any release flag
(run_evals.py governs those) and never touches the app, database, Redis or workers.

Reports hold aggregate metrics and synthetic case IDs only: no input text, vectors, provider responses, URLs or keys.
Exit codes: 0 gate passed, 1 a gate failed, 2 refused / unsupported / blocked / fixture missing, 3 NOT_EVALUATED.
"""
import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence

import yaml

HERE = Path(__file__).resolve().parent
K = 10
FAKE_DIM = 32
COHORTS = ("en", "ur", "roman_ur", "synonym")
# App/database settings: live mode refuses to run next to them rather than risk touching real data.
APP_ENV = ("DATABASE_URL", "REDIS_URL", "ADMIN_API_KEY", "INTERNAL_API_TOKEN", "SESSION_SIGNING_KEY")
LEAK = re.compile(r"https?://|www\.|@|\.(com|pk|org|net)\b|\d{9,}", re.I)


class Stop(Exception):
    """A candidate outcome reached mid-run. `code` is a fixed slug, never provider text."""

    def __init__(self, outcome: str, code: str):
        super().__init__(code)
        self.outcome, self.code = outcome, code


# --- fixture -----------------------------------------------------------------------------------------------------

def load_fixture(root: Path, thr: dict) -> tuple[list[dict], list[dict], str, list[str]]:
    path = root / thr["fixture"]["path"]
    if not path.is_file() or not path.read_bytes().strip():
        raise FileNotFoundError(path.name)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    records = [r for r in rows if r["kind"] == "record"]
    queries = [r for r in rows if r["kind"] == "query"]
    return records, queries, digest, check_fixture(rows, records, queries, thr)


def satisfies(record: dict, c: Mapping) -> bool:
    """Every hard constraint on this single record, so colour+size is always the same variant."""
    return (("price_min" not in c or record["price"] >= c["price_min"])
            and ("price_max" not in c or record["price"] <= c["price_max"])
            and (not c.get("in_stock") or record["stock"] > 0)
            and all(record[k] == c[k] for k in ("category", "material", "color", "size") if k in c))


def check_fixture(rows, records, queries, thr) -> list[str]:
    fx, errors = thr["fixture"], []
    states = [r["vector_state"] for r in records]
    for name, got, want in (("records", len(records), fx["records"]), ("queries", len(queries), fx["queries"]),
                            ("missing", states.count("missing"), fx["missing_vector_records"]),
                            ("stale", states.count("stale"), fx["stale_vector_records"]),
                            ("meta rows", sum(r["kind"] == "meta" for r in rows), 1)):
        if got != want:
            errors.append(f"{name}: {got} != {want}")
    for cohort in fx["cohorts"]:
        n = sum(q["cohort"] == cohort for q in queries)
        want = fx["queries_per_cohort"]
        want = want.get(cohort) if isinstance(want, dict) else want  # v1: one scalar; v2: per-cohort mapping
        if n != want:
            errors.append(f"cohort {cohort}: {n} queries")
    if sum(bool(q["constraints"]) for q in queries) < fx["min_hard_constraint_queries"]:
        errors.append("too few hard-constraint queries")
    by_id = {r["id"]: r for r in records}
    if len(by_id) != len(records) or len({q["id"] for q in queries}) != len(queries):
        errors.append("duplicate ids")
    cap = thr["bounds"]["max_input_chars"]
    for r in records:
        if not re.fullmatch(r"SYN-R\d{3}", r["id"]) or not re.fullmatch(r"SYN-P\d{2}", r["product"]) or len(r["text"]) > cap:
            errors.append(f"{r['id']}: bad id or text length")
    for q in queries:
        if not re.fullmatch(r"SYN-Q\d{3}", q["id"]) or len(q["text"]) > cap or q["cohort"] not in fx["cohorts"]:
            errors.append(f"{q['id']}: bad id, cohort or text length")
        gold = q["relevant_ids"]
        if not 1 <= len(gold) <= K:
            errors.append(f"{q['id']}: gold set size {len(gold)}")
        for rid in gold:
            rec = by_id.get(rid)
            if rec is None or rec["vector_state"] != "ok" or not satisfies(rec, q["constraints"]):
                errors.append(f"{q['id']}: gold {rid} is missing, not scorable or breaks a constraint")
        derived = {r["id"] for r in records if r["vector_state"] == "ok" and satisfies(r, q["constraints"])
                   and all(r[k] == v for k, v in q["semantic_attrs"].items())}
        if derived != set(gold):
            errors.append(f"{q['id']}: gold differs from the records matching its attributes and constraints")
        for bound in (q["constraints"].get(k) for k in ("price_min", "price_max")):
            if bound is not None and any(r["price"] == bound for r in records):
                errors.append(f"{q['id']}: price bound equals an attained price (strict and inclusive readings would differ)")
    if LEAK.search(json.dumps(rows, ensure_ascii=False)):
        errors.append("fixture holds a URL, email or phone-like string")
    return errors


# --- metrics -----------------------------------------------------------------------------------------------------

def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def rank(qvec, records, vectors, constraints) -> list[str]:
    """Top-K ids. Hard constraints and vector currency filter candidates BEFORE similarity, so ranking cannot override them."""
    cands = [r["id"] for r in records if r["vector_state"] == "ok" and r["id"] in vectors and satisfies(r, constraints)]
    return [i for _, i in sorted((-cosine(qvec, vectors[i]), i) for i in cands)[:K]]


def query_metrics(ranked: list[str], gold: Sequence[str]) -> dict:
    g = set(gold)
    dcg = sum(1 / math.log2(i + 2) for i, rid in enumerate(ranked) if rid in g)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(g), K)))
    first = next((i + 1 for i, rid in enumerate(ranked) if rid in g), None)
    return {"recall_at_10": len(g & set(ranked)) / len(g), "mrr_at_10": 1 / first if first else 0.0, "ndcg_at_10": dcg / idcg}


def mean_metrics(items: list[dict]) -> dict:
    out = {m: sum(i[m] for i in items) / len(items) for m in ("recall_at_10", "mrr_at_10", "ndcg_at_10")}
    return {**out, "queries": len(items)}


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    return len(set(a) & set(b)) / len(set(a) | set(b)) if a or b else 1.0


def evaluate(records, queries, qvecs_by_repeat, rvecs_by_repeat) -> dict:
    """Scores repeat 0; hard-constraint, exclusion and Jaccard figures cover every repeat."""
    state = {r["id"]: r["vector_state"] for r in records}
    by_id = {r["id"]: r for r in records}
    rankings = [{q["id"]: rank(qv[q["id"]], records, rv, q["constraints"]) for q in queries}
                for qv, rv in zip(qvecs_by_repeat, rvecs_by_repeat)]
    per_q = {q["id"]: query_metrics(rankings[0][q["id"]], q["relevant_ids"]) for q in queries}
    violating = sorted({q["id"] for rk in rankings for q in queries
                        if any(not satisfies(by_id[i], q["constraints"]) for i in rk[q["id"]])})
    hard = [q for q in queries if q["constraints"]]
    would = sum(any(not satisfies(by_id[i], q["constraints"])
                    for i in rank(qvecs_by_repeat[0][q["id"]], records, rvecs_by_repeat[0], {})) for q in hard)
    jac = [jaccard(rankings[0][q["id"]], rk[q["id"]]) for rk in rankings[1:] for q in queries]
    states = list(state.values())
    return {
        "retrieval": {"overall": mean_metrics(list(per_q.values())),
                      "cohorts": {c: mean_metrics([per_q[q["id"]] for q in queries if q["cohort"] == c]) for c in COHORTS}},
        "constraints": {"queries": len(hard), "violations": len(violating), "violating_query_ids": violating,
                        "unconstrained_ranking_would_violate_queries": would},
        "exclusion": {"missing_or_stale_ranked": sum(state[i] != "ok" for rk in rankings for ids in rk.values() for i in ids)},
        "coverage": {"records": len(records), "scored": states.count("ok"), "missing": states.count("missing"),
                     "stale": states.count("stale"), "scored_fraction": states.count("ok") / len(records)},
        "reproducibility": {"repeats": len(rankings), "top10_jaccard": sum(jac) / len(jac) if jac else None},
    }


def check_vectors(vecs, dim: int) -> dict:
    """Per-vector rates: finite and non-zero (cosine is undefined for a zero vector), and exactly `dim` long."""
    def good(v):
        return (isinstance(v, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)
                and any(v))
    n = len(vecs) or 1
    return {"finite": sum(good(v) for v in vecs) / n, "stable_dimension": sum(isinstance(v, list) and len(v) == dim for v in vecs) / n}


def gate(value, spec) -> bool:
    return value is not None and (value >= spec["min"] if "min" in spec else value <= spec["max"])


def check_gates(m: dict, thr: dict, semantic: bool) -> dict:
    """gate -> pass | fail | not_evaluated, plus the exact failing metric names."""
    g: dict = {"failed": []}

    def put(name, ok):
        g[name] = "pass" if ok else "fail"
        if not ok:
            g["failed"].append(name)
    v = m["vectors"]
    put("vector_count", gate(v["count_match"], thr["vectors"]["count_match"]))
    put("vector_finite", gate(v["finite"], thr["vectors"]["finite"]))
    put("vector_dimension", gate(v["stable_dimension"], thr["vectors"]["stable_dimension"]))
    put("hard_constraints", gate(m["constraints"]["violations"], thr["constraints"]["hard_violations"]))
    put("missing_stale_exclusion", gate(m["exclusion"]["missing_or_stale_ranked"], thr["exclusion"]["missing_or_stale_ranked"]))
    put("reproducibility", gate(m["reproducibility"]["top10_jaccard"], thr["reproducibility"]["top10_jaccard"]))
    if not semantic or m["retrieval"] is None:
        g["semantic"] = "not_evaluated"
        return g
    r = m["retrieval"]
    for metric, spec in thr["retrieval"]["overall"].items():
        put(f"{metric}[overall]", gate(r["overall"][metric], spec))
    for cohort, row in r["cohorts"].items():
        for metric, spec in thr["retrieval"]["cohort"].items():
            put(f"{metric}[{cohort}]", gate(row[metric], spec))
    g["semantic"] = "fail" if any("_at_10" in f for f in g["failed"]) else "pass"
    return g


# --- embedding ---------------------------------------------------------------------------------------------------

class Meter:
    def __init__(self):
        self.requests = self.retries = self.chars = 0
        self.latency: list[float] = []
        self.count_ok = True


def fake_vector(text: str) -> list[float]:
    """Deterministic and offline, and deliberately not semantic: identical text gives identical vectors, nothing more."""
    digest = hashlib.sha256(text.encode("utf-8")).digest() + hashlib.sha256(b"x" + text.encode("utf-8")).digest()
    return [v / 128 - 1 for v in struct.unpack("32b", digest[:32])]


class FakeResult:
    def __init__(self, vectors):
        self.vectors, self.request = vectors, {"attempts": 1}


def fake_embed(texts, **_):
    return FakeResult([fake_vector(t) for t in texts])


def embed_all(embed: Callable, segments: list[tuple[list[str], dict]], batch: int, meter: Meter, caps: dict) -> list:
    """Each segment is (texts, embed kwargs) and is batched on its own, so a query batch never mixes with passages."""
    out: list = []
    for chunk, kw in [(t[i:i + batch], kw) for t, kw in segments for i in range(0, len(t), batch)]:
        if meter.requests >= caps["max_requests"]:
            raise Stop("failed_budget_or_timeout", "request_cap")
        start = time.perf_counter()
        res = embed(chunk, **kw)
        meter.latency.append(time.perf_counter() - start)
        meter.requests += 1
        meter.chars += sum(map(len, chunk))
        meter.retries += max(0, int((res.request or {}).get("attempts", 1)) - 1)
        meter.count_ok &= len(res.vectors) == len(chunk)
        if est_cost(meter.chars, caps["usd_per_million_tokens"]) > caps["max_cost_usd"]:
            raise Stop("failed_budget_or_timeout", "cost_cap")
        out.extend(res.vectors)
    return out


def est_cost(chars: int, price_per_million: float) -> float:
    return math.ceil(chars / 4) * price_per_million / 1e6  # shortcut: chars/4 token estimate, not billed usage


def run(records, queries, embed, thr, *, repeats, batch, dim, caps, include_stale, semantic, split_kinds=False) -> dict:
    """Embed the scorable records and every query `repeats` times, then validate, rank and gate. Raises Stop."""
    embedded = [r for r in records if r["vector_state"] == "ok" or (include_stale and r["vector_state"] == "stale")]
    texts = [r["text"] for r in embedded] + [q["text"] for q in queries]
    # Local e5 needs `passage: ` vs `query: ` prefixes, so those two are embedded (and batched) separately; others get one list.
    segments = ([([r["text"] for r in embedded], {"kind": "passage"}), ([q["text"] for q in queries], {"kind": "query"})]
                if split_kinds else [(texts, {})])
    per_repeat = sum(-(-len(t) // batch) for t, _ in segments)
    if per_repeat * repeats > caps["max_requests"] or est_cost(sum(map(len, texts)) * repeats, caps["usd_per_million_tokens"]) > caps["max_cost_usd"]:
        raise Stop("failed_budget_or_timeout", "preflight_cap")
    meter, rv_all, qv_all, vec_rates = Meter(), [], [], []
    for _ in range(repeats):
        vecs = embed_all(embed, segments, batch, meter, caps)
        vec_rates.append(check_vectors(vecs, dim))
        if len(vecs) != len(texts) or vec_rates[-1]["finite"] < 1 or vec_rates[-1]["stable_dimension"] < 1:
            break
        rv_all.append({r["id"]: v for r, v in zip(embedded, vecs)})
        qv_all.append({q["id"]: v for q, v in zip(queries, vecs[len(embedded):])})
    m = {"vectors": {"count_match": 1.0 if meter.count_ok else 0.0, "finite": min(v["finite"] for v in vec_rates),
                     "stable_dimension": min(v["stable_dimension"] for v in vec_rates), "dimension": dim}}
    if len(rv_all) == repeats and meter.count_ok:
        m.update(evaluate(records, queries, qv_all, rv_all))
    else:  # invalid vectors: nothing is ranked, so every dependent gate is unmet
        m.update({"retrieval": None, "constraints": {"queries": 0, "violations": None}, "exclusion": {"missing_or_stale_ranked": None},
                  "reproducibility": {"repeats": repeats, "top10_jaccard": None}})
    lat = meter.latency
    m["usage"] = {"requests": meter.requests, "transport_retries": meter.retries, "texts_per_repeat": len(texts),
                  "estimated_tokens": math.ceil(meter.chars / 4), "estimated_cost_usd": round(est_cost(meter.chars, caps["usd_per_million_tokens"]), 6),
                  "latency_ms": {"total": round(sum(lat) * 1000, 3), "mean_per_request": round(sum(lat) / len(lat) * 1000, 3) if lat else 0,
                                 "max": round(max(lat) * 1000, 3) if lat else 0}}
    m["gates"] = check_gates(m, thr, semantic)
    return m


# --- CLI ---------------------------------------------------------------------------------------------------------

def refuse(msg: str) -> int:
    print(f"refused: {msg}")
    return 2


def emit(report: dict, path: Path | None) -> None:
    if path:
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, transport=None) -> int:
    env = os.environ if env is None else env
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--synthetic-only", action="store_true")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--recorded", action="store_true")
    mode.add_argument("--live", action="store_true")
    p.add_argument("--root", type=Path, default=HERE)
    p.add_argument("--thresholds", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--no-fallback", action="store_true")
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--dimension", type=int)
    p.add_argument("--batch-size", type=int)
    p.add_argument("--timeout", type=float)
    p.add_argument("--max-input-chars", type=int)
    p.add_argument("--repeats", type=int)
    p.add_argument("--max-requests", type=int)
    p.add_argument("--max-cost-usd", type=float)
    p.add_argument("--usd-per-million-tokens", type=float)
    p.add_argument("--local-model-path", default=env.get("EMBEDDING_EVAL_LOCAL_MODEL_PATH"))  # local_e5 only; offline model dir
    p.add_argument("--local-cache-dir", default=env.get("EMBEDDING_EVAL_LOCAL_CACHE_DIR"))
    p.add_argument("--local-model-revision", default=env.get("EMBEDDING_EVAL_LOCAL_MODEL_REVISION"))  # tree digest of the model dir
    a = p.parse_args(argv)
    if not a.synthetic_only:
        p.error("--synthetic-only is required: only the fictional corpus may be evaluated")
    live_flags = {k: getattr(a, k) for k in ("provider", "model", "dimension", "batch_size", "timeout", "max_input_chars",
                                             "repeats", "max_requests", "max_cost_usd", "usd_per_million_tokens")}
    local = a.live and a.provider == "local_e5"
    if local:  # local-only: free and fixed-size, so these have safe defaults; everything else stays explicit
        for k, v in (("dimension", 768), ("usd_per_million_tokens", 0.0)):
            setattr(a, k, v if getattr(a, k) is None else getattr(a, k))
        live_flags.update({k: getattr(a, k) for k in ("dimension", "usd_per_million_tokens")})
    thr = yaml.safe_load((a.thresholds or a.root / "embedding_thresholds.yaml").read_text(encoding="utf-8"))
    b = thr["bounds"]
    if local and a.max_cost_usd is None:
        a.max_cost_usd = live_flags["max_cost_usd"] = b["max_cost_usd"]
    base = {"gate": "embedding_synthetic", "mode": "live" if a.live else "recorded", "release_ready": False,
            "release_flags_changed": False, "fallback": {"allowed": False, "used": False}, "candidate": None}

    if a.recorded:
        if any(v is not None for v in live_flags.values()) or a.local_model_path or a.local_cache_dir or a.local_model_revision:
            return refuse("recorded mode takes no provider, model or live caps")
        repeats, batch, dim, include_stale, embed = 2, b["max_batch"], FAKE_DIM, True, fake_embed
        caps = {"max_requests": b["max_requests"], "max_cost_usd": b["max_cost_usd"], "usd_per_million_tokens": 0.0}
    else:
        if env.get("EMBEDDING_EVAL_LIVE") != "1":
            return refuse("live mode needs EMBEDDING_EVAL_LIVE=1")
        if missing := [k for k, v in live_flags.items() if v is None]:
            return refuse("live mode needs explicit " + ", ".join("--" + k.replace("_", "-") for k in missing))
        if not a.no_fallback:
            return refuse("live mode needs --no-fallback")
        if present := [k for k in APP_ENV if env.get(k)]:
            return refuse("app/database configuration is set (" + ", ".join(present) + "); run live with a clean environment")
        if local and (keys := [k for k, v in env.items() if v and re.fullmatch(r"EMBEDDING_EVAL_[A-Z0-9]+_API_KEY", k)]):
            return refuse("local_e5 is local-only; unset provider credentials (" + ", ".join(sorted(keys)) + ")")
        if (a.local_model_path or a.local_cache_dir or a.local_model_revision) and not local:
            return refuse("--local-model-path, --local-cache-dir and --local-model-revision are only for --provider local_e5")
        for name, val, hi, lo in (("batch-size", a.batch_size, b["max_batch"], 1), ("timeout", a.timeout, b["timeout_s"], 0.001),
                                  ("max-input-chars", a.max_input_chars, b["max_input_chars"], 1), ("repeats", a.repeats, b["max_repeats"], 2),
                                  ("max-requests", a.max_requests, b["max_requests"], 1), ("max-cost-usd", a.max_cost_usd, b["max_cost_usd"], 0.0001),
                                  ("dimension", a.dimension, 1 << 16, 1), ("usd-per-million-tokens", a.usd_per_million_tokens, 1e6, 0)):
            if not lo <= val <= hi:
                return refuse(f"--{name} must be within {lo}..{hi}")
        repeats, batch, dim, include_stale = a.repeats, a.batch_size, a.dimension, False
        caps = {"max_requests": a.max_requests, "max_cost_usd": a.max_cost_usd, "usd_per_million_tokens": a.usd_per_million_tokens}

    try:
        records, queries, digest, errors = load_fixture(a.root, thr)
    except FileNotFoundError:
        print("embedding_synthetic  NOT_EVALUATED  fixture missing or empty")
        return 2
    if digest != thr["fixture"]["sha256"]:
        return refuse("fixture checksum does not match the locked sha256")
    base["fixture"] = {"sha256": digest, "records": len(records), "queries": len(queries),
                       "hard_constraint_queries": sum(bool(q["constraints"]) for q in queries)}
    if errors:
        print("fixture invalid:", *errors, sep="\n    - ")
        return 1
    if a.live and max(len(r["text"]) for r in records + queries) > a.max_input_chars:
        return refuse("--max-input-chars is below the longest fixture text")

    outcome, codes, transport_errs, eval_errs = None, [], (), ()
    if a.live:
        sys.path.insert(0, str(HERE.parent / "apps" / "backend"))  # explicit provider interface only; no app settings
        from embeddings.config import EvalConfig, load_eval_config
        from embeddings.provider import (ConfigError, EmbeddingEvalError, EmbeddingLimits, ProviderRequestError,
                                         UnsupportedProviderError)
        from embeddings.providers import build_provider
        transport_errs, eval_errs = ProviderRequestError, EmbeddingEvalError
        base["candidate"] = {"provider": a.provider, "model": a.model}
        try:
            if local:  # pinned model, no credential, no allowlist: the provider rejects any other model name
                cfg = EvalConfig("local_e5", a.model, "")
            else:
                cfg = load_eval_config(a.provider, a.model, env)
            limits = EmbeddingLimits(max_batch=batch, max_chars=a.max_input_chars, timeout_s=a.timeout,
                                     max_retries=b["max_transport_retries"])
            provider = build_provider(cfg, dim, limits, {"model_path": a.local_model_path, "cache_dir": a.local_cache_dir, "revision": a.local_model_revision} if local else transport)
        except UnsupportedProviderError as e:
            outcome, codes = "unsupported", [e.code]
        except ConfigError as e:
            outcome, codes = "blocked_by_policy", [e.code]
        embed = provider.embed if outcome is None else None
        if local and outcome is None:  # provenance and the honest timeout mode, recorded with the candidate
            from embeddings.providers.local_e5 import TIMEOUT_ENFORCEMENT
            base["candidate"] |= {"model_revision": provider.revision, "timeout_enforcement": TIMEOUT_ENFORCEMENT}
    if outcome is None:
        try:
            m = run(records, queries, embed, thr, repeats=repeats, batch=batch, dim=dim, caps=caps,
                    include_stale=include_stale, semantic=a.live, split_kinds=local)
        except Stop as e:
            outcome, codes, m = e.outcome, [e.code], None
        except transport_errs as e:
            outcome, codes, m = "failed_budget_or_timeout", [e.code], None  # transport/status failure after the single retry
        except eval_errs as e:
            outcome, codes, m = "failed_validation", [e.code], None
        except Exception as e:  # type name only: messages could carry provider text
            outcome, codes, m = "failed_validation", [type(e).__name__], None
    else:
        m = None

    report = {**base, "errors": codes}
    if m is not None:
        failed = m["gates"]["failed"]
        report.update({k: m[k] for k in m if k != "gates"})
        report["gates"] = {k: v for k, v in m["gates"].items() if k != "failed"} | {"failed_metrics": failed}
        validity = {"vector_count", "vector_finite", "vector_dimension", "missing_stale_exclusion"}
        if a.live:
            outcome = ("failed_validation" if validity & set(failed) else "failed_quality" if failed else "passed")
            report["semantic_metrics"] = report.pop("retrieval") if report.get("retrieval") else "NOT_EVALUATED"
        else:
            outcome = "NOT_EVALUATED"
            report.pop("retrieval", None)
            report["semantic_metrics"] = "NOT_EVALUATED"
    else:
        report["semantic_metrics"] = "NOT_EVALUATED"
    report["outcome"] = outcome
    emit(report, a.report)
    gates = report.get("gates", {})
    print(f"embedding_synthetic  mode={base['mode']}  outcome={outcome}  semantic_metrics="
          f"{'NOT_EVALUATED' if report['semantic_metrics'] == 'NOT_EVALUATED' else 'evaluated'}  release_ready=false")
    for name in gates.get("failed_metrics", []) + codes:
        print("    -", name)
    if a.live:
        return {"passed": 0, "unsupported": 2, "blocked_by_policy": 2}.get(outcome, 1)
    return 1 if gates.get("failed_metrics") or codes else 3


if __name__ == "__main__":
    sys.exit(main())
