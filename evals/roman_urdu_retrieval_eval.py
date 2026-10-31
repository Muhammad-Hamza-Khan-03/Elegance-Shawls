"""Keyword vs local-E5 retrieval on labelled English / Roman Urdu / Urdu queries, plus a relevance-cutoff sweep.

  python evals/roman_urdu_retrieval_eval.py [--catalogue 120] [--json out.json]     (needs the E5 model: see semantic/local_e5.py)

Catalogue = scripts/seed_local.build(i) for i < N (synthetic). Relevance comes from each query's rule (category / colour on any
variant / material class). `no_answer` queries must return nothing. Synthetic, unreviewed phrasing: an engineering signal for
choosing the cutoff and finding weak cohorts, NOT production evidence.
"""
import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))
sys.path.insert(0, str(ROOT / "apps/backend/scripts"))

from semantic.local_e5 import get_embedder  # noqa: E402
from semantic.query_parser import ALIASES, FILLER, LOCAL_COLOURS, has_shopping_signal, normalize_query, parse_query  # noqa: E402
from semantic.representation import represent  # noqa: E402
import seed_local  # noqa: E402

WARM, LIGHT = {"pashmina blend", "merino wool"}, {"cotton modal", "silk blend"}
CUTOFFS = [0.10, 0.14, 0.16, 0.18, 0.20, 0.22, 0.24, 1.0]


def catalogue(n):
    rng = random.Random(7)
    out = []
    for i in range(n):
        p = seed_local.build(i, rng)
        out.append({"name": p.name, "category": p.category, "material": p.material, "sizing": p.sizing,
                    "main_description": p.main_description, "variants": [{"name": v.name, "color": v.color, "size": p.sizing} for v in p.variants]})
    return out


def relevant(rule, products):
    def ok(p):
        mat = (p["material"] or "").lower()
        return ((rule.get("category") in (None, p["category"])) and
                (rule.get("colour") is None or any((v["color"] or "").lower() == rule["colour"].lower() for v in p["variants"])) and
                (rule.get("material") is None or mat in (WARM if rule["material"] == "warm" else LIGHT)))
    return {i for i, p in enumerate(products) if ok(p)}


def keyword_hits(query, docs):
    """What the keyword path can do: parser aliases/colour words, then every remaining term must appear in the product text."""
    terms = []
    for tok in normalize_query(query).split():
        tok = LOCAL_COLOURS.get(tok, ALIASES.get(tok, tok))
        if tok not in FILLER:
            terms.append(tok)
    return [i for i, d in enumerate(docs) if terms and all(t in d for t in terms)]


def pipeline(query, products, vecs, embedder):
    """Production order: parse -> hard colour filter -> embed the residual terms -> rank. (None, d) means the parser asked a question."""
    intent = parse_query(query)
    if intent.needs_review:
        return None, None
    pool = [i for i, p in enumerate(products) if intent.colour is None or any((v["color"] or "").lower() == intent.colour for v in p["variants"])]
    if not intent.terms:
        return pool, 0.0
    qv = embedder.embed(" ".join(intent.terms))
    dist = {i: 1 - sum(a * b for a, b in zip(qv, vecs[i])) for i in pool}
    ranked = sorted(pool, key=dist.__getitem__)
    return ranked, (dist[ranked[0]] if ranked else 1.0)


def metrics(ranked, rel):
    top = ranked[:10]
    recall = len(rel & set(top)) / min(10, len(rel))
    rr = next((1 / (r + 1) for r, i in enumerate(top) if i in rel), 0.0)
    return recall, rr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogue", type=int, default=120)
    ap.add_argument("--json")
    args = ap.parse_args()
    embedder = get_embedder()
    if embedder is None:
        raise SystemExit("E5 is not configured (SEMANTIC_* env, see semantic/local_e5.py)")
    products = catalogue(args.catalogue)
    docs = [represent(p)["text"] for p in products]
    vecs = [embedder.embed_passage(p["text"] if False else d) for p, d in zip(products, docs)]
    queries = [json.loads(l) for l in (ROOT / "evals/datasets/roman_urdu_queries.jsonl").read_text(encoding="utf-8").splitlines()]
    agg = defaultdict(lambda: defaultdict(list))
    clarified = defaultdict(int)
    noans = []                                   # (has_signal, best_distance) for queries that must return nothing
    answerable = []                              # (has_signal, best_distance, recall)
    for q in queries:
        ranked, best = pipeline(q["q"], products, vecs, embedder)
        signal = has_shopping_signal(q["q"])
        if q["rule"].get("no_answer"):
            noans.append((signal, 9.0 if ranked is None else best))
            continue
        rel = relevant(q["rule"], products)
        if not rel:
            continue
        qv = embedder.embed(q["q"])
        raw = sorted(range(len(vecs)), key=lambda i: 1 - sum(a * b for a, b in zip(qv, vecs[i])))
        runs = (("raw E5", raw), ("keyword", keyword_hits(q["q"], docs)), ("pipeline", ranked or []))
        for name, order in runs:
            r, rr = metrics(order, rel)
            for cohort in (q["lang"], ("HELDOUT_V3" if q.get("heldout") == "v3" else "HELDOUT") if q.get("heldout") else "ALL"):
                agg[name][cohort].append((r, rr))
        if ranked is None:
            clarified[q["lang"]] += 1
        answerable.append((signal, best, metrics(ranked or [], rel)[0]))
    print(f"catalogue={len(products)} queries={len(queries)} (answerable scored: {len(answerable)}, no-answer: {len(noans)})\n")
    print(f"{'system':10}{'cohort':10}{'n':>4}{'recall@10':>11}{'MRR@10':>9}")
    result = {"cohorts": {}, "gate": {}, "clarified": dict(clarified)}
    for name in ("keyword", "raw E5", "pipeline"):
        for cohort in ("en", "roman_ur", "ur", "mixed", "ALL", "HELDOUT", "HELDOUT_V3"):
            rows = agg[name].get(cohort, [])
            if rows:
                r, rr = sum(x for x, _ in rows) / len(rows), sum(y for _, y in rows) / len(rows)
                print(f"{name:10}{cohort:10}{len(rows):>4}{r:>11.3f}{rr:>9.3f}")
                result["cohorts"][f"{name}/{cohort}"] = {"n": len(rows), "recall10": round(r, 3), "mrr10": round(rr, 3)}
    print(f"\nparser asked a clarifying question instead of searching: {dict(clarified) or 'none'} of answerable queries")
    sig_off = [b for s_, b, _ in answerable if not s_]
    print(f"answerable queries with no shopping word: {len(sig_off)}; no-answer queries with a shopping word: {sum(1 for s_, _ in noans if s_)}")
    print(f"\n{'gate T':>7}{'answerable recall':>19}{'no-answer false-positive':>27}   (show results if shopping word OR best distance <= T)")
    for c in CUTOFFS:
        rec = sum(r for s_, b, r in answerable if s_ or (b is not None and b <= c)) / len(answerable)
        fp = sum(1 for s_, b in noans if s_ or b <= c) / len(noans)
        print(f"{c:>7.2f}{rec:>19.3f}{fp:>27.2f}")
        result["gate"][str(c)] = {"recall": round(rec, 3), "false_positive": round(fp, 2)}
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
