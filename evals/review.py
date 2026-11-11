"""Human-review workflow tooling (issue #139, slice 2b). It makes a real review reproducible; it cannot perform one.

  python evals/review.py export  DATASET --out packet.jsonl          # rows to review, each with a stable row id
  python evals/review.py check   DATASET --packet packet.jsonl --decisions a.jsonl     # validate one reviewer's decisions
  python evals/review.py agree   --decisions a.jsonl --decisions b.jsonl               # Cohen's kappa between two reviewers
  python evals/review.py sign    DATASET --decisions a.jsonl [--decisions b.jsonl] --author NAME --split dev|held_out
                                  # needs EVAL_REVIEWER_KEY in the environment (held by the reviewer, never committed)

Procedure and rubric: evals/review/README.md and evals/review/RUBRIC.md. A decisions file is JSON lines: first line
{"header": {"reviewer", "qualification", "date"}}, then {"id", "decision": accept|reject|correct, "corrected"?, "note"?} per packet row.

`sign` writes evals/reviews/<dataset>.json, the signed record that evals/provenance.py requires before a dataset may be declared
human_reviewed_verified. It refuses unless: the key is present; every packet row has exactly one decision per reviewer; no `reject`
is left unresolved; no reviewer is the author (after normalisation); two reviewers are different people whose agreement reaches
kappa >= MIN_KAPPA. Limits: names, qualification and date are free text from the decisions files. The signature proves the holder
of the reviewer key signed, not that the text is true, that the reviewer reads Urdu, or that they worked independently of the
author. Those rest on who holds the key. Nothing in this repository has been reviewed with this tool; there are no records.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import attestation  # noqa: E402

DECISIONS = {"accept", "reject", "correct"}
MIN_KAPPA = 0.6      # "substantial" agreement (Landis and Koch); a convention, not a law


def row_id(row: dict) -> str:
    return hashlib.sha256(attestation.canonical(row)).hexdigest()[:16]


def _dataset_rows(root: Path, dataset: str) -> list[dict]:
    path = root / dataset
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("every row must be a JSON object")
    return [r for r in rows if r.get("kind") != "meta"]       # meta rows describe the file, they are not reviewed content


def export_packet(root: Path, dataset: str) -> list[dict]:
    """[{"id", "row"}] for every reviewable row; ids are content hashes, so a changed row is a different row."""
    return [{"id": row_id(r), "row": r} for r in _dataset_rows(root, dataset)]


def decision_problems(packet: list[dict], decisions_path: Path) -> tuple[dict | None, dict[str, dict], list[str]]:
    """(header, {id: decision}, problems) for one reviewer's file. Never raises on bad input."""
    try:
        lines = [json.loads(l) for l in decisions_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        header = lines[0]["header"]
        rows = lines[1:]
        if not isinstance(header, dict) or not all(isinstance(r, dict) for r in rows):
            raise ValueError
    except Exception:    # noqa: BLE001 - any malformed file is one problem
        return None, {}, [f"{decisions_path.name}: not a valid decisions file (first line must be a header object, then one object per row)"]
    problems = [f"{decisions_path.name}: header needs a non-empty {k}" for k in ("reviewer", "qualification", "date")
                if not (isinstance(header.get(k), str) and header[k].strip())]
    wanted, seen = {p["id"] for p in packet}, {}
    for r in rows:
        rid = r.get("id")
        if rid not in wanted:
            problems.append(f"{decisions_path.name}: decision for an unknown row id {str(rid)[:20]!r}")
        elif rid in seen:
            problems.append(f"{decisions_path.name}: row {rid} decided twice")
        elif r.get("decision") not in DECISIONS:
            problems.append(f"{decisions_path.name}: row {rid} needs decision accept, reject or correct")
        elif r["decision"] == "correct" and not r.get("corrected"):
            problems.append(f"{decisions_path.name}: row {rid} is `correct` but gives no corrected value")
        else:
            seen[rid] = r
    problems += [f"{decisions_path.name}: row {m} has no valid decision" for m in sorted(wanted - set(seen))]
    return header, seen, problems


def kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters' categorical labels over the same items."""
    n = len(a)
    if n == 0 or n != len(b):
        raise ValueError("need the same non-zero number of labels from both reviewers")
    observed = sum(x == y for x, y in zip(a, b)) / n
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(first: dict[str, dict], second: dict[str, dict]) -> dict:
    ids = sorted(set(first) & set(second))
    a, b = [first[i]["decision"] for i in ids], [second[i]["decision"] for i in ids]
    return {"n": len(ids), "observed": round(sum(x == y for x, y in zip(a, b)) / len(ids), 3) if ids else 0.0, "kappa": round(kappa(a, b), 3) if ids else 0.0}


def sign_record(root: Path, dataset: str, decisions: list[Path], author: str, split: str, env: dict, today: str | None = None) -> tuple[Path | None, list[str]]:
    """Validate everything, then write evals/reviews/<dataset>.json. (path, problems); nothing is written when there are problems."""
    key = env.get(attestation.REVIEWER_KEY_ENV)
    if not key or len(key) < attestation.MIN_KEY_LENGTH:
        return None, [f"{attestation.REVIEWER_KEY_ENV} is not set (at least {attestation.MIN_KEY_LENGTH} characters): only the reviewer key holder can sign"]
    if not 1 <= len(decisions) <= 2:
        return None, ["give one decisions file, or two for an agreement check"]
    if split not in {"dev", "held_out"}:
        return None, ["split must be dev or held_out"]
    try:
        packet = export_packet(root, dataset)
    except Exception as error:    # noqa: BLE001
        return None, [f"{dataset}: cannot be read as reviewable rows ({type(error).__name__})"]
    problems, headers, parsed = [], [], []
    for path in decisions:
        header, seen, found = decision_problems(packet, path)
        problems += found
        if header is not None:
            headers.append(header)
            parsed.append(seen)
            problems += [f"{path.name}: row {r} is `reject`; resolve it (correct the data and re-review) before signing" for r, d in seen.items() if d["decision"] == "reject"]
    reviewers = [attestation._skeleton(h.get("reviewer", "")) for h in headers]
    problems += [f"reviewer {h.get('reviewer')!r} is the dataset author" for h in headers if attestation._skeleton(h.get("reviewer", "")) == attestation._skeleton(author)]
    if len(headers) == 2:
        if reviewers[0] == reviewers[1]:
            problems.append("the two decisions files are from the same reviewer")
        elif not problems:
            stats = agreement(*parsed)
            if stats["kappa"] < MIN_KAPPA:
                problems.append(f"reviewer agreement is too low (kappa {stats['kappa']} < {MIN_KAPPA}); reconcile the disagreements and re-review")
    if problems:
        return None, problems
    payload = {"suite": Path(dataset).stem, "dataset": dataset, "dataset_sha256": attestation.sha256_file(root / dataset), "split": split, "author": author,
               "reviewer": " & ".join(h["reviewer"].strip() for h in headers), "reviewed_at": today or datetime.date.today().isoformat()}
    out = root / "reviews" / f"{Path(dataset).stem}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"payload": payload, "signature": attestation.sign(payload, key)}, indent=1), encoding="utf-8")
    return out, []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("export", "check", "sign"):
        sub.add_parser(name).add_argument("dataset", help="path relative to evals/, e.g. datasets/voice_urdu.jsonl")
    sub.add_parser("agree")
    for p in sub.choices.values():
        p.add_argument("--root", type=Path, default=HERE)
        if p.prog.endswith(("check", "sign", "agree")):
            p.add_argument("--decisions", type=Path, action="append", required=True)
    sub.choices["export"].add_argument("--out", type=Path, required=True)
    sub.choices["check"].add_argument("--packet", type=Path)
    sub.choices["sign"].add_argument("--author", required=True)
    sub.choices["sign"].add_argument("--split", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "export":
        if (args.root / "datasets") in args.out.resolve().parents:
            print("refusing to write a review packet inside datasets/")
            return 2
        args.out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in export_packet(args.root, args.dataset)), encoding="utf-8")
        print(f"wrote {args.out}")
        return 0
    if args.cmd == "check":
        _, seen, problems = decision_problems(export_packet(args.root, args.dataset), args.decisions[0])
        print("\n".join(problems) or f"decisions OK ({len(seen)} rows)")
        return 1 if problems else 0
    if args.cmd == "agree":
        sets = []
        for path in args.decisions:
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()][1:]
            sets.append({r["id"]: r for r in lines})
        print(json.dumps(agreement(*sets[:2])))
        return 0
    out, problems = sign_record(args.root, args.dataset, args.decisions, args.author, args.split, os.environ)
    print("\n".join(problems) if problems else f"signed {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
