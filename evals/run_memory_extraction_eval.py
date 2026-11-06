#!/usr/bin/env python3
"""Offline, deterministic M4-C memory extraction readiness evaluator.

It intentionally is not a model benchmark: it proves the reviewed synthetic
contract and produces no network calls, provider calls, database writes, or
release flag changes.
"""
import argparse, json, re
from pathlib import Path

SENSITIVE = re.compile(r"phone|number|نمبر|فون")
DONT = re.compile(r"do not remember|یاد نہ رکھیں|یاد نہ رکھو|yaad na rakhein|yaad na rakho")
SAVE = re.compile(r"remember|یاد رکھیں|یاد رکھو|yaad rakhein|yaad rakho")

def classify(text: str) -> str:
    if SENSITIVE.search(text.lower()): return "refuse_sensitive"
    if DONT.search(text.lower()): return "do_not_save"
    if SAVE.search(text.lower()): return "save"
    return "not_evaluated"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(Path(__file__).parent / "datasets/memory_extraction_synthetic.jsonl"))
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    results = [{"id": r["id"], "locale": r["locale"], "expected": r["expected"], "actual": classify(r["text"])} for r in rows]
    passed = sum(r["expected"] == r["actual"] for r in results)
    report = {"suite":"memory_extraction_synthetic", "mode":"offline_synthetic", "records":len(results), "passed":passed,
              "failed":len(results)-passed, "release_ready":False, "provider_calls":0, "database_writes":0,
              "by_locale": {locale: sum(r["locale"] == locale for r in results) for locale in sorted({r["locale"] for r in results})},
              "results":results}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("suite","mode","records","passed","failed","release_ready","provider_calls","database_writes")}))
    return 0 if report["failed"] == 0 else 1

if __name__ == "__main__": raise SystemExit(main())
