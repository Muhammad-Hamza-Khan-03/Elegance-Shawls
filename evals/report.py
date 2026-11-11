"""Standard evaluation report with provenance, cohort sizes and uncertainty (issue #139). Offline and deterministic.

  python evals/report.py            # print the report
  python evals/report.py --write    # regenerate evals/reports/cohort_report.md and its .sha256
  python evals/report.py --check    # exit 1 unless the committed report and checksum equal a fresh render

Inputs are committed files only (evals/roman_urdu_results.json = the RECORDED local-E5 run, evals/provenance.yaml, the datasets). No
model is run: the recorded numbers cannot be reproduced here because the E5 weights are not in the repository; the report says so.

Intervals: recall@10 and MRR@10 are per-query values in [0, 1] averaged over a cohort, and the per-query values are not committed, so
Wilson (valid for yes/no outcomes only) is NOT applied to them. They get a Hoeffding interval, valid for any mean of [0, 1] values and
deliberately wide. `wilson()` is provided for true proportions; `bootstrap` needs the per-query values.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import circularity  # noqa: E402
import provenance  # noqa: E402

RESULTS = HERE / "roman_urdu_results.json"
DATASET = "datasets/roman_urdu_queries.jsonl"
REPORT, CHECKSUM = HERE / "reports" / "cohort_report.md", HERE / "reports" / "cohort_report.sha256"
CIRCULAR_SHARE = 0.5     # a cohort is "circular" when at least this share of its queries use only generator/production vocabulary


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a proportion of yes/no outcomes."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def hoeffding(mean: float, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """(1 - alpha) Hoeffding interval for the mean of n values in [0, 1]. Valid, conservative."""
    if n <= 0:
        return (0.0, 1.0)
    half = math.sqrt(math.log(2 / alpha) / (2 * n))
    return (max(0.0, mean - half), min(1.0, mean + half))


def _queries(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / DATASET).read_text(encoding="utf-8").splitlines() if line.strip()]


def _cohort_rows(rows: list[dict], cohort: str) -> list[dict]:
    if cohort == "HELDOUT":
        return [r for r in rows if r.get("heldout") is True]
    if cohort == "HELDOUT_V3":
        return [r for r in rows if r.get("heldout") == "v3"]
    if cohort == "ALL":
        return [r for r in rows if not r.get("heldout")]
    return [r for r in rows if r.get("lang") == cohort]


def render(root: Path = HERE) -> str:
    prov = provenance.load(root)
    min_n = prov["min_n"]
    entry = prov["datasets"][DATASET]
    results = json.loads((root / "roman_urdu_results.json").read_text(encoding="utf-8"))["cohorts"]
    rows = _queries(root)
    vocabulary = circularity.generator_vocabulary(root) | circularity.production_vocabulary(root)
    out = [
        "# Retrieval cohort report (generated; do not edit)", "",
        "> **Synthetic, unreviewed data.** Engineering signal for choosing cutoffs and finding weak cohorts, **not** evidence of real-world",
        "> accuracy and **not** release evidence. No real customer query is in the data. `release_ready` is unaffected by this report.", "",
        "## Provenance", "",
        f"- dataset `{DATASET}` sha256 `{entry['sha256']}`",
        f"- origin `{entry['origin']}`, review `{entry['review']}`, split `{entry['split']}` (rows carry a `heldout` field)",
        f"- {entry['note'].strip()}",
        f"- low-n threshold: fewer than {min_n} scored queries",
        "- results: the RECORDED local-E5 run in `evals/roman_urdu_results.json` (sha256 "
        f"`{hashlib.sha256((root / 'roman_urdu_results.json').read_bytes()).hexdigest()}`). The E5 weights are not in the repository, so these numbers are quoted, not reproduced, by this report.", "",
        "## Vocabulary circularity (computed from the dataset now)", "",
        "| cohort | dataset rows | fully in generator/production vocabulary | token coverage | verdict |", "|---|---|---|---|---|",
    ]
    verdict = {}
    for cohort in ("en", "roman_ur", "ur", "mixed", "ALL", "HELDOUT", "HELDOUT_V3"):
        stats = circularity.overlap([r["q"] for r in _cohort_rows(rows, cohort)], vocabulary)
        share = stats["fully_in_vocabulary"] / stats["n"] if stats["n"] else 0.0
        verdict[cohort] = "circular" if share >= CIRCULAR_SHARE else "partly independent of the vocabulary"
        out.append(f"| {cohort} | {stats['n']} | {stats['fully_in_vocabulary']} ({share:.0%}) | {stats['token_coverage']:.2f} | {verdict[cohort]} |")
    out += ["", "## Scores by cohort (recorded run)", "",
            "Roman Urdu (`roman_ur`), Urdu (`ur`), English (`en`) and mixed cohorts are listed separately; HELDOUT cohorts are separate again.", "",
            "| system | cohort | n | metric | estimate | 95% interval (Hoeffding) | flags |", "|---|---|---|---|---|---|---|"]
    for key in sorted(results, key=lambda k: (k.split("/")[0], ["en", "roman_ur", "ur", "mixed", "ALL", "HELDOUT", "HELDOUT_V3"].index(k.split("/")[1]))):
        system, cohort = key.split("/")
        row = results[key]
        flags = []
        if row["n"] < min_n:
            flags.append(f"LOW-N (n<{min_n})")
        if verdict.get(cohort) == "circular":
            flags.append("circular")
        if cohort.startswith("HELDOUT"):
            flags.append("held-out but synthetic, same-author phrasing")
        for metric, label in (("recall10", "recall@10"), ("mrr10", "MRR@10")):
            low, high = hoeffding(row[metric], row["n"])
            out.append(f"| {system} | {cohort} | {row['n']} | {label} | {row[metric]:.3f} | {low:.2f} to {high:.2f} | {'; '.join(flags) or '-'} |")
    synonym = sum(1 for line in (root / "datasets/embedding_synthetic_v2.jsonl").read_text(encoding="utf-8").splitlines()
                  if line.strip() and (r := json.loads(line)).get("kind") == "query" and r.get("cohort") == "synonym")
    v2 = prov["datasets"]["datasets/embedding_synthetic_v2.jsonl"]
    out += ["", "## Synonym cohort (embedding fixture v2)", "",
            f"- {synonym} scored queries, which is below the low-n threshold of {min_n}: **LOW-N, no interval is meaningful at this size.**",
            f"- review `{v2['review']}`: {v2['review_scope'].strip()}",
            "- no per-query results for this cohort are committed (the recorded run lives outside the repository, referenced by SHA-256 in `docs/qa/local-e5-evaluation-manifest.md`), so no score is reported here.", "",
            "## Not covered", "",
            "- No human-reviewed (signed) dataset exists for Urdu or Roman Urdu; no qualified independent reviewer has been identified.",
            "- No real, privacy-scrubbed customer queries exist; collection is recorded as BLOCKED in `evals/real_queries_status.md`.",
            "- Per-query values are not committed, so Wilson and bootstrap intervals are not available for recall@10 and MRR@10.", "",
            "Regenerate: `python evals/report.py --write`; verify offline: `python evals/report.py --check`.", ""]
    return "\n".join(out)


def check(root: Path = HERE) -> list[str]:
    fresh = render(root)
    issues = []
    if not (root / "reports" / "cohort_report.md").is_file() or (root / "reports" / "cohort_report.md").read_text(encoding="utf-8") != fresh:
        issues.append("reports/cohort_report.md differs from a fresh render (run: python evals/report.py --write)")
    expected = hashlib.sha256(fresh.encode("utf-8")).hexdigest()
    if not (root / "reports" / "cohort_report.sha256").is_file() or (root / "reports" / "cohort_report.sha256").read_text(encoding="utf-8").split()[0:1] != [expected]:
        issues.append("reports/cohort_report.sha256 does not match a fresh render")
    return issues


if __name__ == "__main__":
    if "--write" in sys.argv:
        text = render()
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(text, encoding="utf-8")
        CHECKSUM.write_text(f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  cohort_report.md\n", encoding="utf-8")
        print("wrote", REPORT)
    elif "--check" in sys.argv:
        found = check()
        for issue in found:
            print("REPORT:", issue)
        print("report: " + ("OK" if not found else f"{len(found)} problem(s)"))
        sys.exit(1 if found else 0)
    else:
        print(render())
