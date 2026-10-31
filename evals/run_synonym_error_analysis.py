"""Offline diagnostic: where do the 16 synonym queries fail LEXICALLY, and would a reviewed alias map close the gap?

  python evals/run_synonym_error_analysis.py [--report out.json]

Pure string matching over the unchanged fixture: no embeddings, providers, network, database, Redis or app modules.
Lexical = query tokens equal to a canonical motif/material/category value. Alias-expanded = the same plus the
prototype phrase->canonical map in synonym_aliases.yaml. This measures attribute coverage of the query wording,
NOT semantic embedding quality, and it changes no threshold, gold set or release flag.
Reports hold hashes and synthetic IDs only (query text is replaced by a short sha256).
Exit codes: 0 report produced, 2 fixture/alias validation failed.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ATTRS = ("motif", "material", "category")
_spec = importlib.util.spec_from_file_location("run_embedding_eval", HERE / "run_embedding_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)  # eval-only runner; its provider imports are lazy and live-mode only


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def load_aliases(path: Path = HERE / "synonym_aliases.yaml") -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("status") != "prototype_evaluation_only" or data.get("direction") != "phrase_to_canonical":
        raise ValueError("alias map must stay prototype/evaluation-only and phrase_to_canonical")
    return [{**a, "tokens": tokens(a["phrase"])} for a in data["aliases"]]


def contains(seq: list[str], sub: list[str]) -> bool:
    return any(seq[i:i + len(sub)] == sub for i in range(len(seq) - len(sub) + 1))


def alias_hits(query: dict, aliases: list[dict]) -> list[dict]:
    qt = tokens(query["text"])
    return [a for a in aliases if query["cohort"] in a["cohorts"] and contains(qt, a["tokens"])]


def recognise(query: dict, vocab: dict, aliases: list[dict] | None) -> tuple[set, list[dict]]:
    """(attr, value) pairs the query wording names: direct canonical tokens, plus alias expansions when given."""
    found = {vocab[t] for t in tokens(query["text"]) if t in vocab}
    hits = alias_hits(query, aliases) if aliases else []
    return found | {(a["attr"], a["value"]) for a in hits if a["attr"] in ATTRS}, hits


def candidates(records: list[dict], attrs: set, constraints: dict, state: str) -> list[str]:
    """Records of a vector state matching every recognised attribute and every hard constraint; none if nothing recognised."""
    if not attrs:
        return []
    return [r["id"] for r in records if r["vector_state"] == state and ev.satisfies(r, constraints)
            and all(r[a] == v for a, v in attrs)]


def stage(query, records, vocab, aliases, gold) -> dict:
    attrs, hits = recognise(query, vocab, aliases)
    cand = candidates(records, attrs, query["constraints"], "ok")
    want = set(query["semantic_attrs"].items())
    expected = want | {(k, v) for k, v in query["constraints"].items() if k in ATTRS}
    return {
        "recognised": sorted(attrs), "complete": want <= attrs, "missing_attrs": sorted(want - attrs),
        "gold_covered": {g: g in cand for g in gold},
        "recall": sum(g in cand for g in gold) / len(gold) if cand else 0.0,
        "candidates": cand, "false_positives": sorted(set(cand) - set(gold)),
        "excluded_missing": candidates(records, attrs, query["constraints"], "missing"),
        "excluded_stale": candidates(records, attrs, query["constraints"], "stale"),
        "alias_hits": sorted(a["phrase"] for a in hits),
        # an expansion naming a value that neither the gold attributes nor the query constraints agree with
        "alias_unexpected": sorted(a["phrase"] for a in hits
                                   if (a["attr"] in ATTRS and (a["attr"], a["value"]) not in expected)
                                   or (a["attr"] == "constraint" and not query["constraints"].get(a["value"]))),
    }


def analyse(records, queries, aliases) -> dict:
    vocab = {}
    for r in records:
        for a in ATTRS:
            if vocab.setdefault(r[a], (a, r[a])) != (a, r[a]):
                raise ValueError(f"vocabulary value {r[a]!r} is ambiguous")
    by_id = {r["id"]: r for r in records}
    rows = []
    for q in queries:
        gold = q["relevant_ids"]
        qt = set(tokens(q["text"]))
        overlap = sum(len(qt & set(tokens(by_id[g]["text"]))) / len(qt) for g in gold) / len(gold)
        rows.append({
            "id": q["id"], "cohort": q["cohort"], "text_sha12": hashlib.sha256(q["text"].encode()).hexdigest()[:12],
            "gold_ids": gold,
            "gold_available": [g for g in gold if by_id[g]["vector_state"] == "ok"],
            "gold_missing": [g for g in gold if by_id[g]["vector_state"] == "missing"],
            "gold_stale": [g for g in gold if by_id[g]["vector_state"] == "stale"],
            "canonical_attrs": q["semantic_attrs"], "constraint_keys": sorted(q["constraints"]),
            "lexical_overlap_with_gold": round(overlap, 4),
            "lexical": stage(q, records, vocab, None, gold), "alias_expanded": stage(q, records, vocab, aliases, gold),
        })
    cohorts = {}
    for c in ev.COHORTS:
        rs = [r for r in rows if r["cohort"] == c]
        cohorts[c] = {"queries": len(rs)} | {
            name: {"complete_queries": sum(r[name]["complete"] for r in rs),
                   "mean_recall": round(sum(r[name]["recall"] for r in rs) / len(rs), 4),
                   "false_positive_queries": sum(bool(r[name]["false_positives"]) for r in rs),
                   "false_positive_total": sum(len(r[name]["false_positives"]) for r in rs),
                   "alias_hits": sum(len(r[name]["alias_hits"]) for r in rs),
                   "alias_unexpected": sum(len(r[name]["alias_unexpected"]) for r in rs)}
            for name in ("lexical", "alias_expanded")}
    return {"queries": rows, "cohorts": cohorts}


def build_report(root: Path = HERE) -> tuple[dict, list[str]]:
    thr = yaml.safe_load((root / "embedding_thresholds.yaml").read_text(encoding="utf-8"))
    records, queries, digest, errors = ev.load_fixture(root, thr)
    if digest != thr["fixture"]["sha256"]:
        errors.append("fixture sha256 differs from embedding_thresholds.yaml")
    if errors:
        return {}, errors
    aliases = load_aliases(root / "synonym_aliases.yaml")
    return {
        "scope": "offline lexical/alias attribute-coverage diagnostic; NOT semantic embedding quality; no release flag touched",
        "alias_map": "prototype_evaluation_only", "fixture_sha256": digest,
        "counts": {"records": len(records), "queries": len(queries),
                   "synonym_queries": sum(q["cohort"] == "synonym" for q in queries)},
        **analyse(records, queries, aliases),
    }, []


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--report")
    args = p.parse_args(argv)
    try:
        report, errors = build_report()
    except (OSError, ValueError, KeyError) as e:
        report, errors = {}, [type(e).__name__]
    if errors:
        print(json.dumps({"errors": errors}), file=sys.stderr)
        return 2
    text = json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
