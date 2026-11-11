"""Dataset provenance (issue #139). Every dataset under evals/datasets/ must be declared in evals/provenance.yaml with where it came
from, how far it was reviewed and how it is split, bound to its sha256. Nothing is inferred from a row field.

  python evals/provenance.py        # check; exit 1 on any problem

Review status is a closed vocabulary:
  unreviewed                no human looked at the labels
  ai_reviewed_only          an AI assistant reviewed them; not human review
  owner_statement_unsigned  the repository owner states they reviewed (scope in review_scope); there is NO signed record, so
                            independence from the author and language qualification are not established
  human_reviewed_verified   a signed review record (evals/reviews/<dataset>.json, reviewer key; see attestation.py) covers this exact
                            dataset hash with a reviewer different from the author. Only this status counts as human-reviewed evidence.
A row-level `reviewed: true` is a CLAIM: it is accepted only when the dataset's declared status is owner_statement_unsigned or
human_reviewed_verified. Nothing in this file turns synthetic or unreviewed data into evidence; the release gate (attestation.py,
run_evals.py) is unchanged and still needs signed held-out attestations and a signed owner approval.
"""
import json
import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import attestation  # noqa: E402

ORIGINS = {"synthetic_generator", "synthetic_ai_authored", "synthetic_unrecorded", "human_authored", "real_scrubbed", "unknown"}
REVIEWS = {"unreviewed", "ai_reviewed_only", "owner_statement_unsigned", "human_reviewed_verified"}
SPLITS = {"unsplit", "mixed"}          # mixed: rows carry their own `heldout` field
NEEDS_SCOPE = {"owner_statement_unsigned", "human_reviewed_verified"}
UNREVIEWED = {"unreviewed", "ai_reviewed_only"}


def load(root: Path = HERE) -> dict:
    return yaml.safe_load((root / "provenance.yaml").read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("every row must be a JSON object")
    return rows


def problems(root: Path = HERE, env: dict | None = None) -> list[str]:
    """Everything wrong with the provenance declarations (empty list = consistent)."""
    env = os.environ if env is None else env
    try:
        prov = load(root)
        entries = prov["datasets"]
        if not isinstance(entries, dict) or not isinstance(prov.get("min_n"), int) or prov["min_n"] < 1:
            raise ValueError
    except Exception:    # noqa: BLE001 - missing, malformed or hostile file: one clear problem, never a traceback
        return ["provenance.yaml: missing or malformed (needs integer min_n and a datasets mapping)"]
    found: list[str] = []
    files = {p.relative_to(root).as_posix() for p in (root / "datasets").glob("*.jsonl")}
    found += [f"{f}: dataset has no provenance entry" for f in sorted(files - set(entries))]
    found += [f"{f}: provenance entry for a missing dataset" for f in sorted(set(entries) - files)]
    for rel in sorted(set(entries) & files):
        entry, path = entries[rel], root / rel
        if not isinstance(entry, dict):
            found.append(f"{rel}: entry must be a mapping")
            continue
        for key, allowed in (("origin", ORIGINS), ("review", REVIEWS), ("split", SPLITS)):
            if entry.get(key) not in allowed:
                found.append(f"{rel}: {key} must be one of {sorted(allowed)}")
        if entry.get("sha256") != attestation.sha256_file(path):
            found.append(f"{rel}: sha256 does not match the file (dataset changed; update the entry deliberately)")
        if not isinstance(entry.get("note"), str) or not entry["note"].strip():
            found.append(f"{rel}: a note saying where the data came from is required")
        review = entry.get("review")
        if review in NEEDS_SCOPE and not all(isinstance(entry.get(k), str) and entry[k].strip() for k in ("reviewer", "review_date", "review_scope")):
            found.append(f"{rel}: review {review} needs reviewer, review_date and review_scope")
        if review == "human_reviewed_verified":
            record = root / "reviews" / f"{path.stem}.json"
            payload, why = attestation._load_signed(record, env.get(attestation.REVIEWER_KEY_ENV), attestation.REVIEWER_KEY_ENV, attestation.REVIEW_FIELDS)
            if why:
                found.append(f"{rel}: declared human_reviewed_verified but {why}")
            elif payload["dataset_sha256"] != entry["sha256"] or attestation._skeleton(payload["author"]) == attestation._skeleton(payload["reviewer"]):
                found.append(f"{rel}: review record does not bind this dataset hash with an independent reviewer")
        try:
            claims = sum(1 for r in _rows(path) if r.get("reviewed") is True)
        except Exception:    # noqa: BLE001
            found.append(f"{rel}: unreadable as JSON lines")
            continue
        if claims and review in UNREVIEWED:
            found.append(f"{rel}: {claims} row(s) claim reviewed=true but the declared review status is {review}")
    return found


if __name__ == "__main__":
    issues = problems()
    for issue in issues:
        print("PROVENANCE:", issue.encode("utf-8", "backslashreplace").decode())
    print("provenance: " + ("OK" if not issues else f"{len(issues)} problem(s)"))
    sys.exit(1 if issues else 0)
